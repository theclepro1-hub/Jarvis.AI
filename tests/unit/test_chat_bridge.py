from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.ai.ai_service import AIReplyResult
from core.models.action_models import ExecutionResult, ExecutionStep
from ui.bridge.chat_bridge import ChatBridge


class _State:
    status = "Готов"


class _History:
    def __init__(self) -> None:
        self.saved: list[list[dict[str, object]]] = []
        self.current: list[dict[str, object]] = []

    def load(self) -> list[dict[str, object]]:
        return list(self.current)

    def save(self, messages: list[dict[str, object]]) -> None:
        self.current = list(messages)
        self.saved.append(list(messages))

    def clear(self) -> None:
        self.current = []


class _Actions:
    def quick_actions(self) -> list[dict[str, str]]:
        return []

    def app_catalog(self) -> list[dict[str, str]]:
        return []


class _Router:
    def __init__(self, route) -> None:  # noqa: ANN001
        self.route = route
        self.received: list[tuple[str, str]] = []

    def handle(self, text: str, *, source: str = "ui"):  # noqa: ANN201
        self.received.append((text, source))
        return self.route


class _Ai:
    def __init__(self) -> None:
        self.received: list[str] = []

    def generate_reply(self, _text: str, _history: list[dict[str, object]]) -> str:
        self.received.append(_text)
        return f"AI fallback: {_text}"


class _AiWithResult(_Ai):
    def generate_reply_result(self, text: str, _history: list[dict[str, object]], *, status_callback=None) -> AIReplyResult:  # noqa: ANN001
        if status_callback is not None:
            status_callback("Быстрый режим: Groq…")
        self.received.append(text)
        return AIReplyResult(
            text=f"AI fallback: {text}",
            mode="fast",
            provider="groq",
            provider_label="Groq",
            model="openai/gpt-oss-20b",
            elapsed_ms=145,
        )


class _AiWithMarkdownResult(_Ai):
    def generate_reply_result(self, text: str, _history: list[dict[str, object]], *, status_callback=None) -> AIReplyResult:  # noqa: ANN001
        _ = status_callback
        self.received.append(text)
        return AIReplyResult(
            text="**Сводка**\n| A | B |\n|---|---|\n| 1 | 2 |\n\n- Первый\n- Второй\n- Третий\n- Четвертый\n- Пятый\n- Шестой",
            mode="fast",
            provider="groq",
            provider_label="Groq",
            model="openai/gpt-oss-20b",
            elapsed_ms=145,
        )


class _Voice:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.spoken: list[str] = []

    def voice_response_enabled(self) -> bool:
        return self.enabled

    def speak(self, text: str, force: bool = False) -> str:
        _ = force
        self.spoken.append(text)
        return "ok"


class _WakeBridge:
    def __init__(self) -> None:
        self.cleared = 0

    def clearWakeHint(self) -> None:
        self.cleared += 1


class _Services:
    def __init__(self, route) -> None:  # noqa: ANN001
        self.chat_history = _History()
        self.actions = _Actions()
        self.command_router = _Router(route)
        self.ai = _Ai()
        self.voice = _Voice()
        self.settings = SimpleNamespace(get=lambda *_args, **_kwargs: True)
def _bridge_for(route) -> tuple[ChatBridge, _Services]:  # noqa: ANN001
    services = _Services(route)
    bridge = ChatBridge(_State(), services, app_bridge=None)
    return bridge, services


def _route_with_steps(steps: list[ExecutionStep], assistant_lines: list[str] | None = None):  # noqa: ANN201
    result = ExecutionResult(
        kind="local",
        commands=["пользовательская команда"],
        steps=steps,
        assistant_lines=assistant_lines or [],
        queue_items=["пользовательская команда"],
    )
    return SimpleNamespace(
        kind="local",
        commands=result.commands,
        assistant_lines=result.assistant_lines,
        queue_items=result.queue_items,
        execution_result=result,
    )


def test_local_execution_result_with_one_simple_action_renders_as_plain_text() -> None:
    route = _route_with_steps(
        [
            ExecutionStep(
                id="open:youtube",
                kind="open_url",
                title="Открываю YouTube",
                status="done",
            )
        ],
        ["Открываю YouTube"],
    )
    bridge, _services = _bridge_for(route)

    bridge.sendMessage("открой ютуб")

    assert bridge.messages[-1]["type"] == "text"
    assert bridge.messages[-1]["text"] == "Открываю YouTube"


def test_mixed_execution_result_uses_plan_title_instead_of_first_step_title() -> None:
    route = _route_with_steps(
        [
            ExecutionStep("music", "open_items", "Открываю Яндекс Музыка", status="done"),
            ExecutionStep("volume", "volume_up", "Прибавляю громкость", status="failed"),
            ExecutionStep("search", "search_web", "Ищу в интернете: чизбургер", status="done"),
        ],
        ["Открываю Яндекс Музыка"],
    )
    bridge, _services = _bridge_for(route)

    bridge.sendMessage("открой музыку прибавь и найди чизбургер")

    assert bridge.messages[-1]["type"] == "execution"
    assert bridge.messages[-1]["title"] == "Выполняю 3 действия"
    assert [step["status"] for step in bridge.messages[-1]["steps"]] == ["готово", "ошибка", "готово"]


def test_wake_noise_does_not_enter_chat_history_but_reminders_do() -> None:
    bridge, _services = _bridge_for(
        SimpleNamespace(kind="ai", commands=[], assistant_lines=[], queue_items=[], execution_result=None)
    )
    before = len(bridge.messages)

    bridge.appendAssistantNote("Слово активации найдено. Подхватываю команду...")
    bridge.appendAssistantNote("Не расслышал команду после слова активации.")

    assert len(bridge.messages) == before

    bridge.appendAssistantNote("Напоминание: чай")

    assert bridge.messages[-1]["text"] == "Напоминание: чай"


def test_generic_cloud_stt_noise_does_not_enter_chat_history() -> None:
    bridge, _services = _bridge_for(
        SimpleNamespace(kind="ai", commands=[], assistant_lines=[], queue_items=[], execution_result=None)
    )
    before = len(bridge.messages)

    bridge.appendAssistantNote("Нужен ключ для облачного распознавания речи.")
    bridge.appendAssistantNote("Нужна локальная модель или ключ для облачного распознавания речи.")

    assert len(bridge.messages) == before


def test_chat_bridge_clears_wake_hint_on_assistant_note() -> None:
    route = SimpleNamespace(kind="ai", commands=["чай"], assistant_lines=[], queue_items=["чай"], execution_result=None)
    wake_bridge = _WakeBridge()
    bridge, _services = _bridge_for(route)
    bridge.app_bridge = SimpleNamespace(voice_bridge=wake_bridge)

    bridge.appendAssistantNote("Напоминание: чай")

    assert wake_bridge.cleared >= 1


def test_clear_history_keeps_only_fresh_welcome_message() -> None:
    route = _route_with_steps(
        [ExecutionStep("open:youtube", "open_url", "Открываю YouTube", status="done")],
        ["Открываю YouTube"],
    )
    bridge, services = _bridge_for(route)

    bridge.sendMessage("открой ютуб")
    assert len(bridge.messages) > 1

    bridge.clearHistory()

    assert len(bridge.messages) == 1
    assert bridge.messages[0]["role"] == "assistant"
    assert "JARVIS Unity" in bridge.messages[0]["text"]
    assert services.chat_history.current == []


def test_voice_response_speaks_assistant_local_result(monkeypatch) -> None:
    monkeypatch.setattr("ui.bridge.chat_bridge.threading.Thread", lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)))
    route = _route_with_steps(
        [ExecutionStep("open:youtube", "open_url", "Открываю YouTube", status="done")],
        ["Открываю YouTube"],
    )
    bridge, services = _bridge_for(route)
    services.voice.enabled = True

    bridge.sendMessage("открой ютуб")

    assert services.voice.spoken == ["Открываю YouTube"]


def test_chat_bridge_routes_plain_conversation_to_ai_without_local_not_understood(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["как дела?"], assistant_lines=[], queue_items=["как дела?"], execution_result=None)
    bridge, services = _bridge_for(route)

    bridge.sendMessage("как дела?")

    assert services.ai.received == ["как дела?"]
    assert bridge.messages[-1]["role"] == "assistant"
    assert bridge.messages[-1]["text"] == "AI fallback: как дела?"


def test_chat_bridge_uses_cleaned_ai_text_after_wake_like_prefix(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["как дела"], assistant_lines=[], queue_items=["как дела"], execution_result=None)
    bridge, services = _bridge_for(route)

    bridge.sendMessage("гарви с как дела")

    assert services.ai.received == ["как дела"]
    assert bridge.messages[-1]["text"] == "AI fallback: как дела"


def test_chat_bridge_does_not_log_passive_wake_privacy_block() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=[],
        assistant_lines=[],
        queue_items=[],
        execution_result=None,
        suppress_user_message=True,
    )
    bridge, services = _bridge_for(route)

    bridge.submitTranscribedText("обсуждаем проект и критику", source="wake")

    assert services.command_router.received == [("обсуждаем проект и критику", "wake")]
    assert len(bridge.messages) == 1
    assert bridge.messages[0]["role"] == "assistant"


def test_chat_bridge_logs_wake_text_when_router_allows_ai_dialog(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["обсуждаем проект и критику"], assistant_lines=[], queue_items=["обсуждаем проект и критику"], execution_result=None)
    bridge, services = _bridge_for(route)

    bridge.submitTranscribedText("обсуждаем проект и критику", source="wake")

    assert services.command_router.received == [("обсуждаем проект и критику", "wake")]
    assert bridge.messages[1]["role"] == "user"
    assert bridge.messages[1]["text"] == "обсуждаем проект и критику"
    assert bridge.messages[-1]["role"] == "assistant"
    assert bridge.messages[-1]["text"] == "AI fallback: обсуждаем проект и критику"


def test_chat_bridge_ignores_late_ai_reply_after_clear_history(monkeypatch) -> None:
    captured: list[tuple[object, tuple[object, ...]]] = []

    class _Thread:
        def __init__(self, target, args, daemon) -> None:  # noqa: ANN001, D401
            _ = daemon
            captured.append((target, args))

        def start(self) -> None:
            return None

    monkeypatch.setattr("ui.bridge.chat_bridge.threading.Thread", _Thread)
    route = SimpleNamespace(kind="ai", commands=["one"], assistant_lines=[], queue_items=["one"], execution_result=None)
    bridge, services = _bridge_for(route)

    bridge.sendMessage("one")
    assert len(captured) == 1

    bridge.clearHistory()
    target, args = captured[0]
    target(*args)

    assert len(bridge.messages) == 1
    assert bridge.messages[0]["role"] == "assistant"
    assert "JARVIS Unity" in bridge.messages[0]["text"]
    assert services.ai.received == ["one"]


def test_chat_bridge_snapshots_ai_history_per_submission(monkeypatch) -> None:
    captured: list[tuple[object, tuple[object, ...]]] = []

    class _Thread:
        def __init__(self, target, args, daemon) -> None:  # noqa: ANN001, D401
            _ = daemon
            captured.append((target, args))

        def start(self) -> None:
            return None

    monkeypatch.setattr("ui.bridge.chat_bridge.threading.Thread", _Thread)
    route = SimpleNamespace(kind="ai", commands=["one"], assistant_lines=[], queue_items=["one"], execution_result=None)
    bridge, _services = _bridge_for(route)

    bridge.sendMessage("one")
    bridge.sendMessage("two")

    assert len(captured) == 2
    first_history = captured[0][1][2]
    second_history = captured[1][1][2]
    assert len(first_history) == 1
    assert first_history[0]["role"] == "assistant"
    assert len(second_history) == 2
    assert [item["role"] for item in second_history] == ["assistant", "user"]
    assert second_history[-1]["text"] == "one"


def test_chat_bridge_exposes_last_response_hint_from_ai_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["как дела"], assistant_lines=[], queue_items=["как дела"], execution_result=None)
    bridge, services = _bridge_for(route)
    services.ai = _AiWithResult()

    bridge.sendMessage("как дела")

    assert services.ai.received == ["как дела"]
    assert bridge.lastResponseHint == "Быстрый: Groq · 0.1 с"
    assert bridge.thinkingLabel == ""


@pytest.mark.parametrize(
    ("assistant_mode", "expected_stage"),
    [
        ("fast", "Быстрый режим"),
        ("standard", "Стандартный режим"),
        ("smart", "Умный режим"),
        ("private", "Приватный режим"),
    ],
)
def test_chat_bridge_reports_assistant_modes_honestly_in_stage_labels(assistant_mode: str, expected_stage: str) -> None:
    route = SimpleNamespace(kind="ai", commands=["как дела"], assistant_lines=[], queue_items=["как дела"], execution_result=None)
    bridge, services = _bridge_for(route)
    services.settings = SimpleNamespace(get=lambda key, default=None: {"assistant_mode": assistant_mode}.get(key, default))

    assert bridge._initial_ai_stage_label(None) == f"{expected_stage}: готовлю ответ…"


def test_chat_bridge_keeps_smart_mode_out_of_auto_hint() -> None:
    route = SimpleNamespace(kind="ai", commands=["как пройти FNAF 4"], assistant_lines=[], queue_items=["как пройти FNAF 4"], execution_result=None)
    bridge, _services = _bridge_for(route)
    result = AIReplyResult(
        text="умный ответ",
        mode="smart",
        provider="gemini",
        provider_label="Gemini",
        model="gemini-3-flash-preview",
        elapsed_ms=220,
    )

    assert bridge._format_ai_response_hint(result) == "Умный: Gemini · 0.2 с"


def test_chat_bridge_sanitizes_ai_markdown_before_appending(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["что-то"], assistant_lines=[], queue_items=["что-то"], execution_result=None)
    bridge, services = _bridge_for(route)
    services.ai = _AiWithMarkdownResult()

    bridge.sendMessage("что-то")

    assert services.ai.received == ["что-то"]
    assert bridge.messages[-1]["role"] == "assistant"
    assert bridge.messages[-1]["text"].startswith("Сводка")
    assert "|" not in bridge.messages[-1]["text"]
    assert "**" not in bridge.messages[-1]["text"]


def test_chat_bridge_keeps_short_followup_for_ai_when_router_marks_it_as_ai(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["раз больше"], assistant_lines=[], queue_items=["раз больше"], execution_result=None)
    bridge, services = _bridge_for(route)

    bridge.sendMessage("раз больше")

    assert services.ai.received == ["раз больше"]
    assert bridge.messages[-1]["role"] == "assistant"
    assert bridge.messages[-1]["text"] == "AI fallback: раз больше"


def test_chat_bridge_clears_wake_hint_when_execution_result_is_appended() -> None:
    route = _route_with_steps(
        [ExecutionStep("open:youtube", "open_url", "Открываю YouTube", status="done")],
        ["Открываю YouTube"],
    )
    wake_bridge = _WakeBridge()
    bridge, _services = _bridge_for(route)
    bridge.app_bridge = SimpleNamespace(voice_bridge=wake_bridge)

    bridge.appendExecutionResult(
        "Выполняю 1 действие",
        [{"title": "YouTube", "status": "готово"}],
    )

    assert wake_bridge.cleared >= 1


def test_chat_bridge_ignores_empty_local_noise_route() -> None:
    route = SimpleNamespace(kind="local", commands=[], assistant_lines=[], queue_items=[], execution_result=None)
    bridge, _services = _bridge_for(route)
    before = len(bridge.messages)

    bridge.sendMessage("джарвис")

    assert len(bridge.messages) == before + 1
    assert bridge.messages[-1]["role"] == "user"


def test_chat_bridge_dedupes_inflight_same_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: None),
    )
    route = SimpleNamespace(kind="ai", commands=["hello"], assistant_lines=[], queue_items=["hello"], execution_result=None)
    bridge, _services = _bridge_for(route)
    before = len(bridge.messages)

    bridge.sendMessage("hello")
    bridge.sendMessage("hello")

    assert len(bridge.messages) == before + 1
    assert bridge.thinking is True
    assert "Уже отправлено" in bridge.state.status


def test_chat_bridge_clears_thinking_label_after_ai_reply(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    route = SimpleNamespace(kind="ai", commands=["how are you"], assistant_lines=[], queue_items=["how are you"], execution_result=None)
    bridge, _services = _bridge_for(route)

    bridge.sendMessage("how are you")

    assert bridge.thinking is False
    assert bridge.thinkingLabel == ""
    assert bridge.messages[-1]["role"] == "assistant"


def test_chat_bridge_emits_message_appended_for_user_and_assistant() -> None:
    route = SimpleNamespace(kind="ai", commands=["hello"], assistant_lines=[], queue_items=["hello"], execution_result=None)
    bridge, _services = _bridge_for(route)
    roles: list[str] = []
    bridge.messageAppended.connect(roles.append)

    bridge._append_message("user", "привет")  # noqa: SLF001 - signal wiring regression coverage.
    bridge._append_message("assistant", "привет!")  # noqa: SLF001 - signal wiring regression coverage.

    assert roles == ["user", "assistant"]


def test_chat_bridge_allows_different_messages_while_ai_is_pending(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: None),
    )
    route = SimpleNamespace(kind="ai", commands=["first"], assistant_lines=[], queue_items=["first"], execution_result=None)
    bridge, _services = _bridge_for(route)
    before = len(bridge.messages)

    bridge.sendMessage("first")
    bridge.sendMessage("second")

    assert len(bridge.messages) == before + 2
    assert [message["text"] for message in bridge.messages[-2:]] == ["first", "second"]


def test_chat_bridge_keeps_thinking_true_until_last_pending_reply_finishes(monkeypatch) -> None:
    monkeypatch.setattr(
        "ui.bridge.chat_bridge.threading.Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: None),
    )
    route = SimpleNamespace(kind="ai", commands=["first"], assistant_lines=[], queue_items=["first"], execution_result=None)
    bridge, _services = _bridge_for(route)

    bridge.sendMessage("first")
    bridge.sendMessage("second")

    first_signature = bridge._message_signature("first")  # noqa: SLF001
    second_signature = bridge._message_signature("second")  # noqa: SLF001

    bridge._append_assistant_message("reply-one", first_signature)  # noqa: SLF001

    assert bridge.thinking is True
    assert bridge.thinkingLabel != ""

    bridge._append_assistant_message("reply-two", second_signature)  # noqa: SLF001

    assert bridge.thinking is False
    assert bridge.thinkingLabel == ""


def test_chat_bridge_normalizes_legacy_local_ai_mode_in_stage_and_hint() -> None:
    route = SimpleNamespace(kind="ai", commands=[], assistant_lines=[], queue_items=[], execution_result=None)
    bridge, services = _bridge_for(route)
    services.settings = SimpleNamespace(
        get=lambda key, default=None: {"ai_mode": "local", "ai_provider": "auto"}.get(key, default)
    )

    assert bridge._initial_ai_stage_label(None) == "Стандартный режим: готовлю ответ…"

    hint = bridge._format_ai_response_hint(
        SimpleNamespace(mode="local", provider_label="Groq", elapsed_ms=150, fallback_used=False)
    )

    assert hint == "Авто: Groq · 0.1 с"

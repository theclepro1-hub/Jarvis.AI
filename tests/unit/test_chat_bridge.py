from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QGuiApplication

from core.models.action_models import ExecutionResult, ExecutionStep
from ui.bridge.chat_bridge import ChatBridge


class _State:
    status = "Готов"


class _History:
    def __init__(self) -> None:
        self.saved: list[list[dict[str, object]]] = []

    def load(self) -> list[dict[str, object]]:
        return []

    def save(self, messages: list[dict[str, object]]) -> None:
        self.saved.append(list(messages))


class _Actions:
    def quick_actions(self) -> list[dict[str, str]]:
        return []

    def app_catalog(self) -> list[dict[str, str]]:
        return []


class _Router:
    def __init__(self, route) -> None:  # noqa: ANN001
        self.route = route
        self.received: list[str] = []

    def handle(self, text: str):  # noqa: ANN201
        self.received.append(text)
        return self.route


class _Ai:
    def generate_reply(self, _text: str, _history: list[dict[str, object]]) -> str:
        return "AI fallback"


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


class _Services:
    def __init__(self, route) -> None:  # noqa: ANN001
        self.chat_history = _History()
        self.actions = _Actions()
        self.command_router = _Router(route)
        self.ai = _Ai()
        self.voice = _Voice()


def _ensure_app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


def _bridge_for(route) -> tuple[ChatBridge, _Services]:  # noqa: ANN001
    _ensure_app()
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


def test_local_execution_result_always_renders_as_execution_card() -> None:
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

    assert bridge.messages[-1]["type"] == "execution"
    assert bridge.messages[-1]["title"] == "Открываю YouTube"
    assert bridge.messages[-1]["steps"][0]["status"] == "готово"


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
    assert services.chat_history.saved[-1] == bridge.messages


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

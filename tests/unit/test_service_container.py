from __future__ import annotations

from types import SimpleNamespace

from core.services.service_container import ServiceContainer


class _Router:
    def __init__(self, route) -> None:  # noqa: ANN001
        self.route = route
        self.calls: list[tuple[str, str, str]] = []

    def handle(self, text: str, *, source: str = "ui", telegram_chat_id: str = ""):  # noqa: ANN201
        self.calls.append((text, source, telegram_chat_id))
        return self.route


class _Ai:
    def __init__(self) -> None:
        self.received: list[tuple[str, list[dict[str, str]]]] = []

    def generate_reply(self, text: str, history: list[dict[str, str]]) -> str:
        self.received.append((text, history))
        return f"AI:{text}"


def test_handle_external_command_routes_plain_conversation_to_ai() -> None:
    route = SimpleNamespace(
        kind="ai",
        commands=["как дела?"],
        assistant_lines=[],
        queue_items=["как дела?"],
        execution_result=None,
    )
    runtime = SimpleNamespace(command_router=_Router(route), ai=_Ai())

    reply = ServiceContainer.handle_external_command(runtime, "как дела?", telegram_chat_id="777")

    assert reply == "AI:как дела?"
    assert runtime.command_router.calls == [("как дела?", "telegram", "777")]
    assert runtime.ai.received == [("как дела?", [])]


def test_handle_external_command_returns_local_reply_without_ai_when_router_has_answer() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=["открой ютуб"],
        assistant_lines=["Открываю YouTube"],
        queue_items=["открой ютуб"],
        execution_result=object(),
    )
    runtime = SimpleNamespace(command_router=_Router(route), ai=_Ai())

    reply = ServiceContainer.handle_external_command(runtime, "открой ютуб", telegram_chat_id="777")

    assert reply == "Открываю YouTube"
    assert runtime.ai.received == []


def test_handle_external_command_ignores_empty_local_noise_without_ai() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=[],
        assistant_lines=[],
        queue_items=[],
        execution_result=None,
    )
    runtime = SimpleNamespace(command_router=_Router(route), ai=_Ai())

    reply = ServiceContainer.handle_external_command(runtime, "джарвис", telegram_chat_id="777")

    assert reply == ""
    assert runtime.ai.received == []

from __future__ import annotations

import time
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from core.services.service_container import ServiceContainer
from ui.bridge.settings_bridge import SettingsBridge


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
        commands=["how are you"],
        assistant_lines=[],
        queue_items=["how are you"],
        execution_result=None,
    )
    runtime = SimpleNamespace(command_router=_Router(route), ai=_Ai())

    reply = ServiceContainer.handle_external_command(runtime, "how are you", telegram_chat_id="777")

    assert reply == "AI:how are you"
    assert runtime.command_router.calls == [("how are you", "telegram", "777")]
    assert runtime.ai.received == [("how are you", [])]


def test_handle_external_command_returns_local_reply_without_ai_when_router_has_answer() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=["open youtube"],
        assistant_lines=["Opening YouTube"],
        queue_items=["open youtube"],
        execution_result=object(),
    )
    runtime = SimpleNamespace(command_router=_Router(route), ai=_Ai())

    reply = ServiceContainer.handle_external_command(runtime, "open youtube", telegram_chat_id="777")

    assert reply == "Opening YouTube"
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

    reply = ServiceContainer.handle_external_command(runtime, "jarvis", telegram_chat_id="777")

    assert reply == ""
    assert runtime.ai.received == []


class _FakeSettings:
    def __init__(self) -> None:
        self._registration = {}

    def get(self, _key: str, default=None):  # noqa: ANN001, ANN201
        return default

    def get_registration(self) -> dict[str, object]:
        return dict(self._registration)


class _FakeTelegram:
    def __init__(self, *, success: bool, delay_seconds: float = 0.2) -> None:
        self.success = success
        self.delay_seconds = delay_seconds
        self.calls = 0
        self._last_error = "timeout"

    def send_test_message(self, text: str = "") -> bool:  # noqa: ARG002
        self.calls += 1
        time.sleep(self.delay_seconds)
        return self.success

    def last_error(self) -> str:
        return self._last_error

    def status_snapshot(self):  # noqa: ANN201
        return SimpleNamespace(
            configured=True,
            connected=False,
            last_command="",
            last_reply="",
            last_error=self._last_error,
            last_poll_at_utc=None,
        )

    def is_configured(self) -> bool:
        return True


class _FakeUpdates:
    def __init__(self, *, delay_seconds: float = 0.2, ok: bool = True) -> None:
        self.delay_seconds = delay_seconds
        self.ok = ok
        self.calls = 0
        self.apply_calls = 0

    def check_now(self):  # noqa: ANN201
        self.calls += 1
        time.sleep(self.delay_seconds)
        return SimpleNamespace(ok=self.ok)

    def apply_update(self):  # noqa: ANN201
        self.apply_calls += 1
        time.sleep(self.delay_seconds)
        return SimpleNamespace(ok=self.ok, started=self.ok)

    def summary(self) -> str:
        return "ok"


def _wait_until(predicate, timeout_seconds: float = 2.0) -> None:  # noqa: ANN001
    app = QCoreApplication.instance() or QCoreApplication([])
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition timeout")


def test_settings_bridge_send_telegram_test_is_single_flight() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    telegram = _FakeTelegram(success=False, delay_seconds=0.2)
    services = SimpleNamespace(
        settings=_FakeSettings(),
        telegram=telegram,
        updates=_FakeUpdates(delay_seconds=0.01, ok=True),
    )
    bridge = SettingsBridge(SimpleNamespace(), services, SimpleNamespace(navigate=lambda _screen: None))

    assert bridge.sendTelegramTest() is True
    assert bridge.sendTelegramTest() is False
    assert bridge.telegramTestBusy is True

    _wait_until(lambda: bridge.telegramTestBusy is False)
    app.processEvents()

    assert telegram.calls == 1
    assert "Telegram не ответил" in bridge.connectionFeedback


def test_settings_bridge_check_for_updates_is_single_flight() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    updates = _FakeUpdates(delay_seconds=0.2, ok=True)
    services = SimpleNamespace(
        settings=_FakeSettings(),
        telegram=_FakeTelegram(success=True, delay_seconds=0.01),
        updates=updates,
    )
    bridge = SettingsBridge(SimpleNamespace(), services, SimpleNamespace(navigate=lambda _screen: None))

    assert bridge.checkForUpdates() is True
    assert bridge.checkForUpdates() is False
    assert bridge.updateCheckBusy is True

    _wait_until(lambda: bridge.updateCheckBusy is False)
    app.processEvents()

    assert updates.calls == 1


def test_settings_bridge_apply_update_is_single_flight() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    updates = _FakeUpdates(delay_seconds=0.2, ok=True)
    services = SimpleNamespace(
        settings=_FakeSettings(),
        telegram=_FakeTelegram(success=True, delay_seconds=0.01),
        updates=updates,
    )
    bridge = SettingsBridge(SimpleNamespace(), services, SimpleNamespace(navigate=lambda _screen: None))

    assert bridge.applyUpdate() is True
    assert bridge.applyUpdate() is False
    assert bridge.updateCheckBusy is True

    _wait_until(lambda: bridge.updateCheckBusy is False)
    app.processEvents()

    assert updates.apply_calls == 1

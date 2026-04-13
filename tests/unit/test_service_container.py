from __future__ import annotations

import time
import threading
from types import SimpleNamespace

import pytest

from core.services.service_container import ServiceContainer


def _load_qt_dependencies():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    from ui.bridge.settings_bridge import SettingsBridge

    return QCoreApplication, SettingsBridge


class _Router:
    def __init__(self, route) -> None:  # noqa: ANN001
        self.route = route
        self.calls: list[tuple[str, str, str]] = []
        self.preview_calls: list[tuple[str, str, str]] = []

    def handle(self, text: str, *, source: str = "ui", telegram_chat_id: str = ""):  # noqa: ANN201
        self.calls.append((text, source, telegram_chat_id))
        return self.route

    def preview(self, text: str, *, source: str = "ui", telegram_chat_id: str = ""):  # noqa: ANN201
        self.preview_calls.append((text, source, telegram_chat_id))
        return self.route


class _Ai:
    def __init__(self) -> None:
        self.received: list[tuple[str, list[dict[str, str]]]] = []

    def generate_reply(self, text: str, history: list[dict[str, str]]) -> str:
        self.received.append((text, history))
        return "AI"

    def generate_reply_result(self, text: str, history: list[dict[str, str]], *, status_callback=None):  # noqa: ANN001, ANN201
        self.received.append((text, history))
        if status_callback is not None:
            status_callback("telegram_ai")
        return SimpleNamespace(text="AI")


def _build_runtime(route) -> ServiceContainer:  # noqa: ANN001
    runtime = ServiceContainer.__new__(ServiceContainer)
    runtime._command_router = _Router(route)
    runtime._ai = _Ai()
    runtime._telegram_history_lock = threading.RLock()
    runtime._telegram_history_by_chat_id = {}
    runtime._telegram_history_limit = 12
    return runtime


def test_handle_external_command_routes_plain_conversation_to_ai() -> None:
    route = SimpleNamespace(
        kind="ai",
        commands=["how are you"],
        assistant_lines=[],
        queue_items=["how are you"],
        execution_result=None,
    )
    runtime = _build_runtime(route)

    reply = ServiceContainer.handle_external_command(runtime, "how are you", telegram_chat_id="777")

    assert reply == "AI"
    assert runtime._command_router.calls == [("how are you", "telegram", "777")]
    assert len(runtime._ai.received) == 1
    assert runtime._ai.received[0][1] == []
    assert runtime._ai.received[0][0] == "how are you"


def test_handle_external_command_uses_short_telegram_history_per_chat() -> None:
    route = SimpleNamespace(
        kind="ai",
        commands=[],
        assistant_lines=[],
        queue_items=[],
        execution_result=None,
    )
    runtime = _build_runtime(route)

    first = ServiceContainer.handle_external_command(runtime, "hello", telegram_chat_id="777")
    second = ServiceContainer.handle_external_command(runtime, "what next", telegram_chat_id="777")

    assert first == "AI"
    assert second == "AI"
    assert runtime._ai.received[0][1] == []
    assert runtime._ai.received[1][1] == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "AI"},
    ]


def test_handle_external_command_keeps_telegram_history_isolated_by_chat_id() -> None:
    route = SimpleNamespace(
        kind="ai",
        commands=[],
        assistant_lines=[],
        queue_items=[],
        execution_result=None,
    )
    runtime = _build_runtime(route)

    first = ServiceContainer.handle_external_command(runtime, "hello", telegram_chat_id="777")
    second = ServiceContainer.handle_external_command(runtime, "hello there", telegram_chat_id="888")
    third = ServiceContainer.handle_external_command(runtime, "what next", telegram_chat_id="777")

    assert first == "AI"
    assert second == "AI"
    assert third == "AI"
    assert runtime._ai.received[1][1] == []
    assert runtime._ai.received[2][1] == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "AI"},
    ]


def test_handle_external_command_returns_local_reply_without_ai_when_router_has_answer() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=["open youtube"],
        assistant_lines=["Opening YouTube"],
        queue_items=["open youtube"],
        execution_result=object(),
    )
    runtime = _build_runtime(route)

    reply = ServiceContainer.handle_external_command(runtime, "open youtube", telegram_chat_id="777")

    assert reply == "Opening YouTube"
    assert runtime._ai.received == []


def test_service_container_classifies_local_route_as_fast_lane() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=["open youtube"],
        assistant_lines=[],
        queue_items=["open youtube"],
        execution_result=None,
    )
    runtime = ServiceContainer.__new__(ServiceContainer)
    runtime._command_router = SimpleNamespace(
        preview=lambda text, *, source="ui", telegram_chat_id="": route,  # noqa: ARG005
    )

    assert ServiceContainer.classify_external_command(runtime, "open youtube", telegram_chat_id="777") == "fast"


def test_service_container_classifies_ai_route_as_ai_lane() -> None:
    route = SimpleNamespace(kind="ai")
    runtime = _build_runtime(route)

    assert ServiceContainer.classify_external_command(runtime, "как дела", telegram_chat_id="777") == "ai"
    assert runtime.command_router.preview_calls == [("как дела", "telegram", "777")]


def test_handle_external_command_ignores_empty_local_noise_without_ai() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=[],
        assistant_lines=[],
        queue_items=[],
        execution_result=None,
    )
    runtime = _build_runtime(route)

    reply = ServiceContainer.handle_external_command(runtime, "jarvis", telegram_chat_id="777")

    assert reply == ""
    assert runtime._ai.received == []


def test_handle_external_command_keeps_local_route_out_of_ai_even_without_assistant_lines() -> None:
    route = SimpleNamespace(
        kind="local",
        commands=["next track"],
        assistant_lines=[],
        queue_items=["next track"],
        execution_result=SimpleNamespace(
            steps=[
                SimpleNamespace(title="Следующий трек"),
                SimpleNamespace(title="Команда отправлена"),
            ]
        ),
    )
    runtime = _build_runtime(route)

    reply = ServiceContainer.handle_external_command(runtime, "next track", telegram_chat_id="777")

    assert reply == "Следующий трек\nКоманда отправлена"
    assert runtime._ai.received == []


def test_service_container_defers_heavy_services_until_accessed(monkeypatch) -> None:
    container = ServiceContainer.__new__(ServiceContainer)
    container.settings_store = object()
    container.chat_history = object()
    container.settings = _FakeSettings()
    container.startup = SimpleNamespace(is_enabled=lambda: False)
    container.registration = SimpleNamespace()
    container._reminders = None
    container._telegram = None
    container._voice = None
    container._wake = None
    container._updates = None
    container._ai = None
    container._actions = None
    container._batch_router = None
    container._pc_control = None
    container._command_router = None

    created: list[str] = []

    class TrackedAi:
        def __init__(self, *_args, **_kwargs) -> None:
            created.append("ai")

    class TrackedActions:
        def __init__(self, *_args, **_kwargs) -> None:
            created.append("actions")

    class TrackedBatchRouter:
        def __init__(self, *_args, **_kwargs) -> None:
            created.append("batch_router")

    class TrackedPcControl:
        def __init__(self, *_args, **_kwargs) -> None:
            created.append("pc_control")

    class TrackedCommandRouter:
        def __init__(self, *_args, **_kwargs) -> None:
            created.append("command_router")
            self.assistant_lines = []
            self.kind = "ai"
            self.commands = ["hello"]

        def handle(self, *_args, **_kwargs):  # noqa: ANN001
            return SimpleNamespace(kind="ai", assistant_lines=[], commands=["hello"])

    monkeypatch.setattr("core.services.service_container.AIService", TrackedAi)
    monkeypatch.setattr("core.services.service_container.ActionRegistry", TrackedActions)
    monkeypatch.setattr("core.services.service_container.BatchRouter", TrackedBatchRouter)
    monkeypatch.setattr("core.services.service_container.PcControlService", TrackedPcControl)
    monkeypatch.setattr("core.services.service_container.CommandRouter", TrackedCommandRouter)

    assert created == []
    _ = container.ai
    _ = container.actions
    _ = container.batch_router
    _ = container.pc_control
    _ = container.command_router

    assert created == ["ai", "actions", "batch_router", "pc_control", "command_router"]


def test_service_container_telegram_transport_uses_safe_timeout_fallback() -> None:
    class Settings(_FakeSettings):
        def __init__(self) -> None:
            super().__init__()
            self._registration = {"telegram_bot_token": "bot_token"}
            self._settings = {"network": {"timeout_seconds": "broken"}}

    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = Settings()

    transport = ServiceContainer._create_telegram_transport(container)

    assert transport is not None
    assert transport.timeout_seconds == 12.0
    assert transport.poll_timeout_seconds == 10.0


def test_service_container_telegram_transport_passes_proxy_settings_through(monkeypatch) -> None:
    class Settings(_FakeSettings):
        def __init__(self) -> None:
            super().__init__()
            self._registration = {"telegram_bot_token": "bot_token"}
            self._settings = {
                "network": {
                    "timeout_seconds": "7.5",
                    "proxy_mode": "manual",
                    "proxy_url": "http://127.0.0.1:8080",
                }
            }

        def get(self, key: str, default=None):  # noqa: ANN001, ANN201
            if key == "network":
                return self._settings["network"]
            return super().get(key, default)

    class FakeTransport:
        def __init__(self, token, *, timeout_seconds, poll_timeout_seconds, proxy_mode, proxy_url) -> None:  # noqa: ANN001
            self.token = token
            self.timeout_seconds = timeout_seconds
            self.poll_timeout_seconds = poll_timeout_seconds
            self.proxy_mode = proxy_mode
            self.proxy_url = proxy_url

    monkeypatch.setattr("core.services.service_container.HttpTelegramTransport", FakeTransport)

    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = Settings()

    transport = ServiceContainer._create_telegram_transport(container)

    assert transport is not None
    assert transport.token == "bot_token"
    assert transport.timeout_seconds == 7.5
    assert transport.poll_timeout_seconds == 6.5
    assert transport.proxy_mode == "manual"
    assert transport.proxy_url == "http://127.0.0.1:8080"


def test_service_container_does_not_write_startup_flag_when_unchanged(monkeypatch) -> None:
    class FakeSettingsService:
        def __init__(self, store) -> None:  # noqa: ANN001
            self.store = store
            self.values = {"startup_enabled": True}
            self.set_calls: list[tuple[str, object]] = []

        def get(self, key: str, default=None):  # noqa: ANN001, ANN201
            return self.values.get(key, default)

        def set(self, key: str, value) -> None:  # noqa: ANN001
            self.values[key] = value
            self.set_calls.append((key, value))

        def get_registration(self) -> dict[str, object]:
            return {}

    class FakeStartupManager:
        def is_enabled(self) -> bool:
            return True

    class FakeRegistrationService:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

    monkeypatch.setattr("core.services.service_container.SettingsStore", lambda: object())
    monkeypatch.setattr("core.services.service_container.ChatHistoryStore", lambda: object())
    monkeypatch.setattr("core.services.service_container.SettingsService", FakeSettingsService)
    monkeypatch.setattr("core.services.service_container.StartupManager", FakeStartupManager)
    monkeypatch.setattr("core.services.service_container.RegistrationService", FakeRegistrationService)

    container = ServiceContainer()

    assert container.settings.set_calls == []


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
    QCoreApplication, _ = _load_qt_dependencies()
    app = QCoreApplication.instance() or QCoreApplication([])
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition timeout")


def test_settings_bridge_send_telegram_test_is_single_flight() -> None:
    QCoreApplication, SettingsBridge = _load_qt_dependencies()
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
    assert "timeout" not in bridge.connectionFeedback.lower()


def test_settings_bridge_check_for_updates_is_single_flight() -> None:
    QCoreApplication, SettingsBridge = _load_qt_dependencies()
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
    QCoreApplication, SettingsBridge = _load_qt_dependencies()
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

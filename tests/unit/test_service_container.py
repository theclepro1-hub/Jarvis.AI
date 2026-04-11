from __future__ import annotations

import time
import threading
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


def test_service_container_defers_heavy_services_until_accessed(monkeypatch) -> None:
    container = ServiceContainer.__new__(ServiceContainer)
    container.settings_store = object()
    container.chat_history = object()
    container.settings = _FakeSettings()
    container.startup = SimpleNamespace(is_enabled=lambda: False)
    container.registration = SimpleNamespace()
    container._lazy_lock = threading.RLock()
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


def test_service_container_ai_is_singleton_under_concurrent_access(monkeypatch) -> None:
    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = _FakeSettings()
    container._lazy_lock = threading.RLock()
    container._ai = None

    created: list[str] = []
    created_lock = threading.Lock()

    class TrackedAi:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("ai")
            time.sleep(0.05)

    monkeypatch.setattr("core.services.service_container.AIService", TrackedAi)

    results = _run_concurrent_access(lambda: container.ai)

    assert len(created) == 1
    assert len({id(result) for result in results}) == 1


def test_service_container_wake_is_singleton_under_concurrent_access(monkeypatch) -> None:
    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = _FakeSettings()
    container._lazy_lock = threading.RLock()
    container._voice = None
    container._wake = None

    created: list[str] = []
    created_lock = threading.Lock()

    class TrackedVoice:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("voice")
            time.sleep(0.05)

    class TrackedWake:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("wake")
            time.sleep(0.05)

    monkeypatch.setattr("core.services.service_container.VoiceService", TrackedVoice)
    monkeypatch.setattr("core.services.service_container.WakeService", TrackedWake)

    results = _run_concurrent_access(lambda: container.wake)

    assert created.count("voice") == 1
    assert created.count("wake") == 1
    assert len({id(result) for result in results}) == 1


def test_service_container_reminders_is_singleton_under_concurrent_access(monkeypatch) -> None:
    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = _FakeSettings()
    container._lazy_lock = threading.RLock()
    container._reminders = None

    created: list[str] = []
    created_lock = threading.Lock()

    class TrackedReminders:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("reminders")
            time.sleep(0.05)

    monkeypatch.setattr("core.services.service_container.ReminderService", TrackedReminders)

    results = _run_concurrent_access(lambda: container.reminders)

    assert created.count("reminders") == 1
    assert len({id(result) for result in results}) == 1


def test_service_container_command_router_is_singleton_under_concurrent_access(monkeypatch) -> None:
    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = _FakeSettings()
    container._lazy_lock = threading.RLock()
    container._reminders = None
    container._voice = None
    container._wake = None
    container._updates = None
    container._ai = None
    container._actions = None
    container._batch_router = None
    container._pc_control = None
    container._command_router = None

    created: list[str] = []
    created_lock = threading.Lock()

    class TrackedActions:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("actions")
            time.sleep(0.05)

    class TrackedBatchRouter:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("batch_router")
            time.sleep(0.05)

    class TrackedAi:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("ai")
            time.sleep(0.05)

    class TrackedPcControl:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("pc_control")
            time.sleep(0.05)

    class TrackedReminders:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("reminders")
            time.sleep(0.05)

    class TrackedCommandRouter:
        def __init__(self, *_args, **_kwargs) -> None:
            with created_lock:
                created.append("command_router")
            time.sleep(0.05)

    monkeypatch.setattr("core.services.service_container.ActionRegistry", TrackedActions)
    monkeypatch.setattr("core.services.service_container.BatchRouter", TrackedBatchRouter)
    monkeypatch.setattr("core.services.service_container.AIService", TrackedAi)
    monkeypatch.setattr("core.services.service_container.PcControlService", TrackedPcControl)
    monkeypatch.setattr("core.services.service_container.ReminderService", TrackedReminders)
    monkeypatch.setattr("core.services.service_container.CommandRouter", TrackedCommandRouter)

    results = _run_concurrent_access(lambda: container.command_router)

    assert created.count("actions") == 1
    assert created.count("batch_router") == 1
    assert created.count("ai") == 1
    assert created.count("pc_control") == 1
    assert created.count("command_router") == 1
    assert len({id(result) for result in results}) == 1


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
    assert transport.proxy_mode == "system"
    assert transport.proxy_url == ""


def test_service_container_telegram_transport_uses_proxy_settings() -> None:
    class Settings(_FakeSettings):
        def __init__(self) -> None:
            super().__init__()
            self._registration = {"telegram_bot_token": "bot_token"}
            self._settings = {
                "network": {
                    "timeout_seconds": 18.5,
                    "proxy_mode": "manual",
                    "proxy_url": "http://127.0.0.1:8888",
                }
            }

        def get(self, key: str, default=None):  # noqa: ANN001, ANN201
            if key == "network":
                return self._settings["network"]
            return default

    container = ServiceContainer.__new__(ServiceContainer)
    container.settings = Settings()

    transport = ServiceContainer._create_telegram_transport(container)

    assert transport is not None
    assert transport.timeout_seconds == 18.5
    assert transport.proxy_mode == "manual"
    assert transport.proxy_url == "http://127.0.0.1:8888"


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
    app = QCoreApplication.instance() or QCoreApplication([])
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition timeout")


def _run_concurrent_access(accessor, worker_count: int = 12):  # noqa: ANN001
    barrier = threading.Barrier(worker_count)
    results: list[object] = []
    errors: list[BaseException] = []
    results_lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait()
            value = accessor()
            with results_lock:
                results.append(value)
        except BaseException as exc:  # noqa: BLE001
            with results_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3.0)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    return results


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
    assert "timeout" not in bridge.connectionFeedback.lower()


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

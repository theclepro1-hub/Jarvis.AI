from __future__ import annotations

import json
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from core.actions.action_registry import ActionRegistry
from core.settings.settings_service import SettingsService
from core.settings.settings_store import DEFAULT_SETTINGS, SettingsStore
from ui.bridge.settings_bridge import SettingsBridge


class InMemoryStore:
    def __init__(self) -> None:
        self.payload = json.loads(json.dumps(DEFAULT_SETTINGS))

    def load(self):
        return json.loads(json.dumps(self.payload))

    def save(self, payload):
        self.payload = json.loads(json.dumps(payload))


class FakeTelegram:
    def __init__(self) -> None:
        self.refreshes = 0
        self.paused = 0

    def is_configured(self) -> bool:
        return True

    def refresh_configuration(self) -> bool:
        self.refreshes += 1
        return True

    def pause_for_reset(self) -> None:
        self.paused += 1


class FakeChatBridge:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clearHistory(self) -> None:
        self.clear_calls += 1


class FakeChatHistory:
    def __init__(self) -> None:
        self.cleared = 0

    def clear(self) -> None:
        self.cleared += 1


def _ensure_app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def test_settings_service_tracks_history_and_pinned_commands() -> None:
    service = SettingsService(InMemoryStore())

    assert service.save_history_enabled() is True
    assert service.get_pinned_commands() == []

    service.set_save_history_enabled(False)
    assert service.save_history_enabled() is False

    assert service.pin_command("youtube") == ["youtube"]
    assert service.pin_command("youtube") == ["youtube"]
    assert service.unpin_command("youtube") == []


def test_settings_bridge_can_clear_chat_and_wipe_runtime_state(monkeypatch, tmp_path) -> None:
    _ensure_app()
    runtime_dir = tmp_path / "JarvisAi_Unity"
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(runtime_dir))

    store = SettingsStore()
    service = SettingsService(store)
    service.set("pinned_commands", ["youtube", "steam"])
    service.set("save_history_enabled", False)

    chat_bridge = FakeChatBridge()
    telegram = FakeTelegram()
    actions = ActionRegistry(service)
    prepare_calls = []
    services = SimpleNamespace(
        settings=service,
        telegram=telegram,
        chat_history=FakeChatHistory(),
        actions=actions,
        prepare_for_data_reset=lambda: prepare_calls.append("prepared"),
    )
    bridge = SettingsBridge(
        state=SimpleNamespace(),
        services=services,
        app_bridge=SimpleNamespace(restartRegistration=lambda: None),
        chat_bridge=chat_bridge,
    )

    bridge.clearChatHistory()
    assert chat_bridge.clear_calls == 1

    result = bridge.deleteAllData()

    assert prepare_calls == ["prepared"]
    assert result["restart_required"] is True
    assert result["registration_required"] is True
    assert service.get_pinned_commands() == []
    assert service.save_history_enabled() is True
    assert chat_bridge.clear_calls >= 2
    assert services.chat_history.cleared >= 1


def test_settings_bridge_delete_all_data_failure_does_not_fake_success() -> None:
    _ensure_app()
    service = SettingsService(InMemoryStore())
    actions = ActionRegistry(service)
    chat_bridge = FakeChatBridge()
    telegram = FakeTelegram()
    restart_calls = []

    service.clear_runtime_data = lambda: (_ for _ in ()).throw(PermissionError("busy"))  # type: ignore[method-assign]
    services = SimpleNamespace(
        settings=service,
        telegram=telegram,
        chat_history=FakeChatHistory(),
        actions=actions,
        prepare_for_data_reset=lambda: None,
    )
    bridge = SettingsBridge(
        state=SimpleNamespace(),
        services=services,
        app_bridge=SimpleNamespace(restartRegistration=lambda: restart_calls.append("restart")),
        chat_bridge=chat_bridge,
    )

    result = bridge.deleteAllData()

    assert result["ok"] is False
    assert restart_calls == []
    assert "Не удалось удалить все данные" in bridge.connectionFeedback


def test_settings_bridge_pins_and_unpins_commands() -> None:
    _ensure_app()
    service = SettingsService(InMemoryStore())
    actions = ActionRegistry(service)
    services = SimpleNamespace(settings=service, telegram=FakeTelegram(), actions=actions)
    bridge = SettingsBridge(state=SimpleNamespace(), services=services, app_bridge=SimpleNamespace(), chat_bridge=None)

    bridge.pinCommand("youtube")
    assert "youtube" in service.get_pinned_commands()
    bridge.togglePinnedCommand("youtube")
    assert "youtube" not in service.get_pinned_commands()

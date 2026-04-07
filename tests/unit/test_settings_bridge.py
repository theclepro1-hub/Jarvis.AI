from __future__ import annotations

import json
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from core.settings.settings_service import SettingsService
from core.settings.settings_store import DEFAULT_SETTINGS
from ui.bridge.settings_bridge import SettingsBridge


class InMemoryStore:
    def __init__(self) -> None:
        self.payload = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.saved: list[dict[str, object]] = []

    def load(self):
        return json.loads(json.dumps(self.payload))

    def save(self, payload):
        self.payload = json.loads(json.dumps(payload))
        self.saved.append(json.loads(json.dumps(payload)))


class FakeTelegram:
    def __init__(self) -> None:
        self.refreshes = 0

    def is_configured(self) -> bool:
        return True

    def refresh_configuration(self) -> bool:
        self.refreshes += 1
        return True


def _ensure_app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def test_settings_bridge_saves_connection_fields_and_refreshes_telegram() -> None:
    _ensure_app()
    store = InMemoryStore()
    settings = SettingsService(store)
    telegram = FakeTelegram()
    services = SimpleNamespace(settings=settings, telegram=telegram)
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.saveConnections("fake_groq_new", "bot_new", "987654321") is True

    registration = settings.get_registration()
    assert registration["groq_api_key"] == "fake_groq_new"
    assert registration["telegram_bot_token"] == "bot_new"
    assert registration["telegram_user_id"] == "987654321"
    assert registration["skipped"] is False
    assert telegram.refreshes == 1
    assert bridge.connectionFeedback == "Подключения сохранены."
    assert bridge.connections["groqApiKeySet"] is True
    assert bridge.connections["telegramBotTokenMasked"] == "••••••••"


def test_settings_bridge_mask_placeholder_keeps_existing_secrets() -> None:
    _ensure_app()
    store = InMemoryStore()
    settings = SettingsService(store)
    settings.save_registration(
        {
            "groq_api_key": "fake_groq_existing",
            "telegram_bot_token": "bot_existing",
            "telegram_user_id": "1",
        },
        skipped=False,
    )
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.saveConnections("••••••••", "••••••••", "2") is True

    registration = settings.get_registration()
    assert registration["groq_api_key"] == "fake_groq_existing"
    assert registration["telegram_bot_token"] == "bot_existing"
    assert registration["telegram_user_id"] == "2"

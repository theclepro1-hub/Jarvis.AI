from __future__ import annotations

import json
from types import SimpleNamespace

from core.settings.settings_service import SettingsService
from core.settings.settings_store import DEFAULT_SETTINGS
from core.version import DEFAULT_VERSION
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


class _ExplodingUpdatesServices:
    def __init__(self, settings) -> None:  # noqa: ANN001
        self.settings = settings
        self.telegram = FakeTelegram()
        self._updates = None

    @property
    def updates(self):  # noqa: ANN201
        raise AssertionError("updates service must stay lazy until user explicitly opens update flow")


def test_settings_bridge_saves_connection_fields_and_refreshes_telegram() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    telegram = FakeTelegram()
    services = SimpleNamespace(settings=settings, telegram=telegram)
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.saveConnections(
        "fake_groq_new",
        "cerebras_new",
        "gemini_new",
        "openrouter_new",
        "bot_new",
        "987654321",
    ) is True

    registration = settings.get_registration()
    assert registration["groq_api_key"] == "fake_groq_new"
    assert registration["cerebras_api_key"] == "cerebras_new"
    assert registration["gemini_api_key"] == "gemini_new"
    assert registration["openrouter_api_key"] == "openrouter_new"
    assert registration["telegram_bot_token"] == "bot_new"
    assert registration["telegram_user_id"] == "987654321"
    assert registration["skipped"] is False
    assert telegram.refreshes == 1
    assert bridge.connectionFeedback == "Подключения сохранены."
    assert bridge.connections["groqApiKeySet"] is True
    assert bridge.connections["cerebrasApiKeySet"] is True
    assert bridge.connections["geminiApiKeySet"] is True
    assert bridge.connections["openrouterApiKeySet"] is True
    assert bridge.connections["telegramBotTokenMasked"] == "••••••••"


def test_settings_bridge_mask_placeholder_keeps_existing_secrets() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    settings.save_registration(
        {
            "groq_api_key": "fake_groq_existing",
            "cerebras_api_key": "cerebras_existing",
            "gemini_api_key": "gemini_existing",
            "openrouter_api_key": "openrouter_existing",
            "telegram_bot_token": "bot_existing",
            "telegram_user_id": "1",
        },
        skipped=False,
    )
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.saveConnections(
        "••••••••",
        "••••••••",
        "••••••••",
        "••••••••",
        "••••••••",
        "2",
    ) is True

    registration = settings.get_registration()
    assert registration["groq_api_key"] == "fake_groq_existing"
    assert registration["cerebras_api_key"] == "cerebras_existing"
    assert registration["gemini_api_key"] == "gemini_existing"
    assert registration["openrouter_api_key"] == "openrouter_existing"
    assert registration["telegram_bot_token"] == "bot_existing"
    assert registration["telegram_user_id"] == "2"


def test_settings_bridge_update_properties_do_not_force_lazy_update_service() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    services = _ExplodingUpdatesServices(settings)
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.updateSummary == f"Версия {DEFAULT_VERSION} · канал стабильный"
    assert bridge.updateStatus["current_version"] == DEFAULT_VERSION
    assert bridge.updateStatus["status_code"] == "idle"


def test_settings_bridge_normalizes_legacy_local_ai_mode_and_profile() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    settings.set("ai_mode", "local")
    settings.set("ai_provider", "auto")
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.aiMode == "auto"
    assert bridge.aiProfile == "auto"
    assert bridge.aiProfiles == [
        "auto",
        "groq_fast",
        "cerebras_fast",
        "gemini_quality",
        "openrouter_free",
    ]

    bridge.aiMode = "local"
    assert settings.get("ai_mode") == "auto"

    bridge.aiProfile = "local"
    assert settings.get("ai_mode") == "auto"
    assert settings.get("ai_provider") == "auto"


def test_settings_bridge_exposes_assistant_status_and_advanced_options() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    bridge.assistantMode = "private"
    bridge.localLlmBackend = "ollama"
    bridge.textBackendOverride = "local_llama"
    bridge.sttBackendOverride = "local_vosk"

    status = bridge.assistantStatus

    assert bridge.localLlmBackend == "ollama"
    assert bridge.textBackendOverride == "local_llama"
    assert bridge.sttBackendOverride == "local_vosk"
    assert status["mode"] == "private"
    assert status["wake"] == "local"
    assert "outside" in status
    assert "local" in status
    assert bridge.localLlmBackendOptions == [
        {"key": "llama_cpp", "title": "llama.cpp"},
        {"key": "ollama", "title": "Ollama"},
    ]


def test_settings_bridge_private_mode_rejects_cloud_overrides() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    bridge.assistantMode = "private"
    bridge.textBackendOverride = "gemini"
    bridge.sttBackendOverride = "groq_whisper"

    assert bridge.textBackendOverride == "local_llama"
    assert bridge.sttBackendOverride == "auto"

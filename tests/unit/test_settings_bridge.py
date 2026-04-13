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
        "fake_cerebras_new",
        "fake_gemini_new",
        "fake_openrouter_new",
        "bot_new",
        "987654321",
    ) is True

    registration = settings.get_registration()
    assert registration["groq_api_key"] == "fake_groq_new"
    assert registration["cerebras_api_key"] == "fake_cerebras_new"
    assert registration["gemini_api_key"] == "fake_gemini_new"
    assert registration["openrouter_api_key"] == "fake_openrouter_new"
    assert registration["telegram_bot_token"] == "bot_new"
    assert registration["telegram_user_id"] == "987654321"
    assert registration["skipped"] is False
    assert telegram.refreshes == 1
    assert bridge.connectionFeedback == "Подключения сохранены."
    assert bridge.cerebrasApiKey == "fake_cerebras_new"
    assert bridge.geminiApiKey == "fake_gemini_new"
    assert bridge.openrouterApiKey == "fake_openrouter_new"
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
    assert registration["cerebras_api_key"] == ""
    assert registration["gemini_api_key"] == ""
    assert registration["openrouter_api_key"] == ""
    assert registration["telegram_bot_token"] == "bot_existing"
    assert registration["telegram_user_id"] == "2"


def test_settings_bridge_saves_advanced_connection_fields() -> None:
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

    assert bridge.saveAdvancedConnections(
        "fake_gemini_new",
        "fake_cerebras_new",
        "fake_openrouter_new",
        "ollama",
        "llama3.2:1b",
    ) is True

    registration = settings.get_registration()
    assert registration["groq_api_key"] == "fake_groq_existing"
    assert registration["cerebras_api_key"] == "fake_cerebras_new"
    assert registration["gemini_api_key"] == "fake_gemini_new"
    assert registration["openrouter_api_key"] == "fake_openrouter_new"
    assert registration["telegram_bot_token"] == "bot_existing"
    assert registration["telegram_user_id"] == "1"
    assert settings.get("local_llm_backend") == "ollama"
    assert settings.get("local_llm_model") == "llama3.2:1b"
    assert bridge.connectionFeedback == "Дополнительные подключения сохранены."


def test_settings_bridge_exposes_assistant_mode_and_local_llm_copy(monkeypatch) -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    settings.set("assistant_mode", "private")
    settings.set("local_llm_backend", "ollama")
    settings.set("local_llm_model", "llama3.2:1b")
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    monkeypatch.setattr(
        bridge,
        "_local_llm_diagnostics",
        lambda: SimpleNamespace(
            ready=True,
            backend="ollama",
            model_path="llama3.2:1b",
            detail="Ollama-модель готова.",
            user_status="Локальная модель готова.",
            action_label="Открыть Ollama",
            action_url="https://docs.ollama.com/",
        ),
    )
    bridge._local_llm_diagnostics_requested = True

    assert bridge.assistantMode == "private"
    assert [item["key"] for item in bridge.assistantModeOptions] == [
        "fast",
        "standard",
        "smart",
        "private",
    ]
    assert bridge.assistantModeSummary == "Только локальная работа."
    assert bridge.assistantUserStatus == "Локально готово"
    assert bridge.localLlmBackend == "ollama"
    assert bridge.localLlmModel == "llama3.2:1b"
    assert bridge.localReadiness == "Локальная модель готова."


def test_settings_bridge_does_not_probe_local_model_until_requested(monkeypatch) -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    calls = {"count": 0}

    class FakeLocalLLMService:
        def __init__(self, _settings) -> None:  # noqa: ANN001
            pass

        def diagnostics(self):  # noqa: ANN201
            calls["count"] += 1
            return SimpleNamespace(
                ready=True,
                backend="ollama",
                model_path="llama3.2:1b",
                detail="Ollama-модель готова.",
                user_status="Локальная модель готова.",
                action_label="Открыть Ollama",
                action_url="https://docs.ollama.com/",
            )

    monkeypatch.setattr("ui.bridge.settings_bridge.LocalLLMService", FakeLocalLLMService)
    bridge._worker_pool = SimpleNamespace(submit=lambda fn: fn())

    assert bridge.assistantUserStatus == "Работает через облако"
    assert bridge.localReadiness == ""
    assert calls["count"] == 0

    bridge.requestLocalDiagnostics()

    assert calls["count"] == 1
    assert bridge.assistantUserStatus == "Локально готово"
    assert bridge.localReadiness == "Локальная модель готова."


def test_settings_bridge_update_properties_do_not_force_lazy_update_service() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    services = _ExplodingUpdatesServices(settings)
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.updateSummary == f"Версия {DEFAULT_VERSION} · канал стабильный"
    assert bridge.updateStatus["current_version"] == DEFAULT_VERSION
    assert bridge.updateStatus["status_code"] == "idle"


def test_settings_bridge_prewarm_refreshes_update_snapshot_without_local_probe(monkeypatch) -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    calls = {"update": 0, "local": 0}
    monkeypatch.setattr(bridge, "_refresh_update_snapshot", lambda: calls.__setitem__("update", calls["update"] + 1))
    monkeypatch.setattr(bridge, "_refresh_local_llm_diagnostics", lambda: calls.__setitem__("local", calls["local"] + 1))

    bridge.prewarm()

    assert calls["update"] == 1
    assert calls["local"] == 0


def test_settings_bridge_normalizes_legacy_local_ai_mode_and_profile() -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    settings.set("ai_mode", "local")
    settings.set("ai_provider", "auto")
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    assert bridge.assistantMode == "standard"
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


def test_settings_bridge_can_prepare_local_runtime(monkeypatch) -> None:
    store = InMemoryStore()
    settings = SettingsService(store)
    settings.set("assistant_mode", "private")
    services = SimpleNamespace(settings=settings, telegram=FakeTelegram())
    bridge = SettingsBridge(state=None, services=services, app_bridge=None)

    class FakeRuntime:
        def ensure_ready(self, _requested_model: str):  # noqa: ANN001, ANN201
            settings.bulk_update({"local_llm_backend": "ollama", "local_llm_model": "llama3.2:1b"})
            return SimpleNamespace(
                ok=True,
                ready=True,
                status_code="portable_ready",
                message="Локальная модель llama3.2:1b скачана и готова.",
            )

    monkeypatch.setattr(bridge, "_local_runtime_service", lambda: FakeRuntime())
    monkeypatch.setattr(
        bridge,
        "_load_local_llm_diagnostics",
        lambda: SimpleNamespace(
            ready=True,
            backend="ollama",
            model_path="llama3.2:1b",
            detail="Ollama-модель готова.",
            user_status="Локальная модель готова.",
            action_label="Открыть Ollama",
            action_url="https://docs.ollama.com/",
        ),
    )
    bridge._worker_pool = SimpleNamespace(submit=lambda fn: fn())

    assert bridge.installLocalRuntime() is True
    assert bridge.localRuntimeBusy is False
    assert bridge.localLlmReady is True
    assert bridge.localRuntimeStatus == "Локальный режим готов."
    assert bridge.localRuntimeActionVisible is False
    assert bridge.localLlmBackend == "ollama"
    assert bridge.localLlmModel == "llama3.2:1b"

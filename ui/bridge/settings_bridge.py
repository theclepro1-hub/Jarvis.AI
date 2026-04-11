from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Property, Signal, Slot

from core.ai.ai_service import SUPPORTED_AI_MODES, SUPPORTED_AI_PROFILES
from core.policy.assistant_mode import (
    AssistantReadiness,
    infer_assistant_mode_from_legacy,
    local_llama_ready,
    resolve_assistant_mode,
    resolve_assistant_policy,
)
from core.version import DEFAULT_VERSION


_SETTINGS_WRITE_LOCK = threading.RLock()
ASSISTANT_MODE_SET = frozenset({"fast", "standard", "smart", "private"})
DEFAULT_LOCAL_LLM_BACKEND = "llama_cpp"
SUPPORTED_TEXT_BACKEND_OVERRIDES = frozenset(
    {"auto", "groq", "cerebras", "gemini", "openrouter", "local_llama"}
)
SUPPORTED_STT_BACKEND_OVERRIDES = frozenset(
    {"auto", "groq_whisper", "local_faster_whisper", "local_vosk"}
)


class SettingsBridge(QObject):
    themeModeChanged = Signal()
    startupEnabledChanged = Signal()
    minimizeToTrayEnabledChanged = Signal()
    startMinimizedEnabledChanged = Signal()
    saveHistoryEnabledChanged = Signal()
    assistantModeChanged = Signal()
    assistantStatusChanged = Signal()
    aiModeChanged = Signal()
    aiProviderChanged = Signal()
    aiProfileChanged = Signal()
    aiModelChanged = Signal()
    localLlmModelChanged = Signal()
    localLlmBackendChanged = Signal()
    textBackendOverrideChanged = Signal()
    sttBackendOverrideChanged = Signal()
    connectionsChanged = Signal()
    connectionFeedbackChanged = Signal()
    updateSummaryChanged = Signal()
    telegramStatusChanged = Signal()
    pinnedCommandsChanged = Signal()
    dataSafetyChanged = Signal()
    telegramTestBusyChanged = Signal()
    updateCheckBusyChanged = Signal()
    _telegramTestFinished = Signal(bool, str)
    _updateCheckFinished = Signal(bool)

    def __init__(self, state, services, app_bridge, chat_bridge=None) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self.app_bridge = app_bridge
        self.chat_bridge = chat_bridge
        self._connection_feedback = ""
        self._telegram_test_busy = False
        self._update_check_busy = False
        self._operation_lock = threading.Lock()
        self._worker_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="settings-bridge")
        self._telegramTestFinished.connect(self._on_telegram_test_finished)
        self._updateCheckFinished.connect(self._on_update_check_finished)
        voice_bridge = getattr(self.app_bridge, "voice_bridge", None)
        if voice_bridge is not None:
            for signal_name in ("modeChanged", "assistantModeChanged", "statusChanged", "assistantStatusChanged", "summaryChanged"):
                signal = getattr(voice_bridge, signal_name, None)
                if signal is not None:
                    signal.connect(self._on_voice_projection_changed)

    def _updates_service_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_updates"):
            return getattr(self.services, "_updates")
        if hasattr(self.services, "__dict__") and "updates" in vars(self.services):
            return vars(self.services).get("updates")
        return None

    def _telegram_service_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_telegram"):
            return getattr(self.services, "_telegram")
        if hasattr(self.services, "__dict__") and "telegram" in vars(self.services):
            return vars(self.services).get("telegram")
        return None

    def _actions_service_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_actions"):
            return getattr(self.services, "_actions")
        if hasattr(self.services, "__dict__") and "actions" in vars(self.services):
            return vars(self.services).get("actions")
        return None

    def _ai_service_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_ai"):
            return getattr(self.services, "_ai")
        if hasattr(self.services, "__dict__") and "ai" in vars(self.services):
            return vars(self.services).get("ai")
        return None

    def _voice_service_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_voice"):
            return getattr(self.services, "_voice")
        if hasattr(self.services, "__dict__") and "voice" in vars(self.services):
            return vars(self.services).get("voice")
        return None

    def _normalize_ai_mode(self, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode in SUPPORTED_AI_MODES:
            return mode
        return "auto"

    def _normalize_assistant_mode(self, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode in ASSISTANT_MODE_SET:
            return mode
        return "standard"

    def _assistant_mode_from_settings(self) -> str:
        return self._normalize_assistant_mode(resolve_assistant_mode(self.services.settings))

    def _assistant_readiness(self) -> AssistantReadiness:
        voice = self._voice_service_if_ready()
        stt_service = getattr(voice, "stt_service", None) if voice is not None else None
        local_faster_whisper_ready = False
        local_vosk_ready = False
        if stt_service is not None:
            local_faster_whisper_ready = bool(getattr(stt_service, "_local_faster_whisper_ready", lambda: False)())
            local_vosk_ready = bool(getattr(stt_service, "_local_vosk_available", lambda: False)())
        return AssistantReadiness(
            local_llama_ready=local_llama_ready(self.services.settings),
            local_faster_whisper_ready=local_faster_whisper_ready,
            local_vosk_ready=local_vosk_ready,
        )

    def _assistant_policy(self):  # noqa: ANN202
        return resolve_assistant_policy(self.services.settings, readiness=self._assistant_readiness())

    def _assistant_mode_options(self) -> list[dict[str, str]]:
        return [
            {"key": "fast", "title": "Быстрый", "note": "Максимум скорости."},
            {"key": "standard", "title": "Стандартный", "note": "Лучший баланс на каждый день."},
            {"key": "smart", "title": "Умный", "note": "Приоритет качества ответа."},
            {"key": "private", "title": "Приватный", "note": "Только локальная работа."},
        ]

    def _format_route(self, route: tuple[str, ...]) -> str:
        if not route:
            return "disabled"
        return " -> ".join(route)

    def _privacy_text(self, guarantee: str) -> str:
        mapping = {
            "cloud_first": "Облако в приоритете",
            "local_first_with_fallback": "Сначала локально, потом облако",
            "quality_first": "Качество в приоритете",
            "no_cloud_ever": "Только локально",
        }
        return mapping.get(str(guarantee or "").strip(), "Смешанный режим")

    def _local_readiness_text(self) -> str:
        from core.ai.local_llm_service import LocalLLMService

        status = LocalLLMService(self.services.settings).status()
        if status.ready:
            return "Локальная модель готова."
        if status.backend == "ollama":
            if not status.model_path:
                return "Укажите модель Ollama, чтобы включить локальный режим."
            if "not installed" in status.detail.casefold():
                return "Модель Ollama ещё не скачана на этот компьютер."
            return "Ollama сейчас недоступен."
        if not status.model_path:
            return "Добавьте .gguf-модель, чтобы включить приватный режим."
        if "not found" in status.detail.casefold():
            return "Файл .gguf не найден."
        if "llama_cpp is not installed" in status.detail:
            return "Нужен пакет llama-cpp-python и .gguf-модель."
        return "Локальная модель пока не готова."

    def _outside_text(self, policy) -> str:  # noqa: ANN202
        if policy.mode == "private":
            return "Ничего не уходит наружу."
        if policy.mode == "standard":
            if policy.text_cloud_allowed and policy.stt_cloud_allowed:
                return "При нехватке локальных моделей часть обработки может временно идти через облако."
            if policy.text_cloud_allowed:
                return "Текст может временно уходить в облако."
            if policy.stt_cloud_allowed:
                return "Распознавание речи может временно уходить в облако после wake."
            return "Облачный fallback отключён."
        if policy.mode == "fast":
            return "Приоритет у быстрых облачных маршрутов."
        if policy.mode == "smart":
            return "Приоритет у качества ответа."
        return "Режим автоматически подбирает маршрут."

    def _local_text(self, policy) -> str:  # noqa: ANN202
        if policy.mode == "private":
            return "Wake word, STT и текст работают локально."
        return "Wake word всегда локальный. Остальное подбирается автоматически."

    def _assistant_user_status_text(self, policy) -> str:  # noqa: ANN202
        has_ai_key, _ = self._assistant_registration_state()
        issues = set(policy.readiness_issues)
        if policy.mode == "private":
            return "Нужна локальная модель" if issues else "Готово: всё локально"
        if policy.mode == "standard":
            if "local_llama_missing" in issues:
                return "Сейчас работает через облако" if has_ai_key else "Нужен ключ AI"
            return "Готово"
        if policy.mode in {"fast", "smart"} and not has_ai_key:
            return "Нужен ключ AI"
        return "Готово"

    def _assistant_status_snapshot(self) -> dict[str, object]:
        policy = self._assistant_policy()
        privacy = self._privacy_text(policy.privacy_guarantee)
        readiness = self._local_readiness_text()
        user_status = self._assistant_user_status_text(policy)
        mode_label = {
            "fast": "Быстрый",
            "standard": "Стандартный",
            "smart": "Умный",
            "private": "Приватный",
        }.get(policy.mode, "Режим")
        return {
            "mode": policy.mode,
            "wake": "Локально",
            "text": "Автоматически",
            "stt": "Автоматически",
            "privacy": privacy,
            "readiness": readiness,
            "outside": self._outside_text(policy),
            "local": self._local_text(policy),
            "summary": f"Режим: {mode_label}. {user_status}",
            "userStatus": user_status,
            "cloudAllowed": bool(policy.text_cloud_allowed or policy.stt_cloud_allowed),
            "textCloudAllowed": bool(policy.text_cloud_allowed),
            "sttCloudAllowed": bool(policy.stt_cloud_allowed),
        }

    def _sync_assistant_mode_from_legacy(self, *, ai_mode: str | None = None, ai_provider: str | None = None) -> None:
        payload = {
            "ai_mode": ai_mode if ai_mode is not None else self.services.settings.get("ai_mode", "auto"),
            "ai_provider": ai_provider if ai_provider is not None else self.services.settings.get("ai_provider", "auto"),
            "voice_mode": self.services.settings.get("voice_mode", "standard"),
        }
        self.services.settings.set("assistant_mode", infer_assistant_mode_from_legacy(payload))

    def _refresh_voice_mode_projection(self) -> None:
        voice_bridge = getattr(self.app_bridge, "voice_bridge", None)
        if voice_bridge is None:
            return
        for signal_name in ("modeChanged", "assistantModeChanged", "summaryChanged", "statusChanged", "assistantStatusChanged"):
            signal = getattr(voice_bridge, signal_name, None)
            if signal is not None:
                signal.emit()

    @Slot()
    def _on_voice_projection_changed(self) -> None:
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()

    def _assistant_registration_state(self) -> tuple[bool, bool]:
        registration = self._registration()
        has_ai_key = any(
            str(registration.get(field, "")).strip()
            for field in (
                "groq_api_key",
                "cerebras_api_key",
                "gemini_api_key",
                "openrouter_api_key",
            )
        )
        telegram_ready = bool(
            str(registration.get("telegram_bot_token", "")).strip()
            and str(registration.get("telegram_user_id", "")).strip()
        )
        return has_ai_key, telegram_ready

    def _default_update_summary(self) -> str:
        return f"Версия {DEFAULT_VERSION} · канал стабильный"

    def _default_update_status(self) -> dict[str, object]:
        return {
            "current_version": DEFAULT_VERSION,
            "latest_version": "",
            "release_url": "",
            "update_available": False,
            "last_error": "",
            "last_checked_at_utc": "",
            "assets": [],
            "apply_supported": False,
            "can_apply": False,
            "apply_hint": "",
            "preferred_installer_asset": "",
            "last_downloaded_installer": "",
            "last_apply_message": "",
            "apply_in_progress": False,
            "check_in_progress": False,
            "installer_running": False,
            "active_installer_pid": 0,
            "status_code": "idle",
            "status_message": self._default_update_summary(),
            "manual_download_required": False,
            "apply_mode": "manual",
            "installer_launch_arguments": [],
        }

    @Property(str, notify=themeModeChanged)
    def themeMode(self) -> str:
        return self.services.settings.get("theme_mode", "midnight")

    @themeMode.setter
    def themeMode(self, value: str) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("theme_mode", value)
        self.themeModeChanged.emit()

    @Property(bool, notify=startupEnabledChanged)
    def startupEnabled(self) -> bool:
        return self.services.settings.get("startup_enabled", False)

    @startupEnabled.setter
    def startupEnabled(self, value: bool) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.startup.set_enabled(value, minimized=self.startMinimizedEnabled)
            self.services.settings.set("startup_enabled", self.services.startup.is_enabled())
        self.startupEnabledChanged.emit()

    @Property(bool, notify=minimizeToTrayEnabledChanged)
    def minimizeToTrayEnabled(self) -> bool:
        return self.services.settings.get("minimize_to_tray_enabled", False)

    @minimizeToTrayEnabled.setter
    def minimizeToTrayEnabled(self, value: bool) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("minimize_to_tray_enabled", value)
        self.minimizeToTrayEnabledChanged.emit()

    @Property(bool, notify=startMinimizedEnabledChanged)
    def startMinimizedEnabled(self) -> bool:
        return self.services.settings.get("start_minimized_enabled", False)

    @startMinimizedEnabled.setter
    def startMinimizedEnabled(self, value: bool) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("start_minimized_enabled", value)
            if self.startupEnabled:
                self.services.startup.set_enabled(True, minimized=value)
        self.startMinimizedEnabledChanged.emit()

    @Property(bool, notify=saveHistoryEnabledChanged)
    def saveHistoryEnabled(self) -> bool:
        return bool(self.services.settings.save_history_enabled())

    @saveHistoryEnabled.setter
    def saveHistoryEnabled(self, value: bool) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set_save_history_enabled(bool(value))
        self.saveHistoryEnabledChanged.emit()
        self.assistantModeChanged.emit()
        self.connectionsChanged.emit()
        self.dataSafetyChanged.emit()

    @Property(str, notify=aiModeChanged)
    def aiMode(self) -> str:
        return self._normalize_ai_mode(self.services.settings.get("ai_mode", "auto"))

    @aiMode.setter
    def aiMode(self, value: str) -> None:
        value = self._normalize_ai_mode(value)
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("ai_mode", value)
            self._sync_assistant_mode_from_legacy(ai_mode=value)
        self.aiModeChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()
        self.aiProfileChanged.emit()

    @Property(str, notify=aiProviderChanged)
    def aiProvider(self) -> str:
        return self.services.settings.get("ai_provider", "auto")

    @aiProvider.setter
    def aiProvider(self, value: str) -> None:
        if value not in {"auto", "groq", "cerebras", "gemini", "openrouter"}:
            value = "auto"
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("ai_provider", value)
            self._sync_assistant_mode_from_legacy(ai_provider=value)
        self.aiProviderChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()
        self.aiProfileChanged.emit()

    @Property(str, notify=aiProfileChanged)
    def aiProfile(self) -> str:
        mode = self.aiMode
        provider = self.aiProvider
        if provider == "groq" and mode == "fast":
            return "groq_fast"
        if provider == "gemini" and mode == "quality":
            return "gemini_quality"
        if provider == "cerebras" and mode == "fast":
            return "cerebras_fast"
        if provider == "openrouter":
            return "openrouter_free"
        return "auto"

    @Property("QVariantList", notify=aiProfileChanged)
    def aiProfiles(self) -> list[str]:
        ai_service = self._ai_service_if_ready()
        if ai_service is not None and hasattr(ai_service, "available_profiles"):
            return list(ai_service.available_profiles())
        return list(SUPPORTED_AI_PROFILES)

    @aiProfile.setter
    def aiProfile(self, value: str) -> None:
        profile_map = {
            "auto": ("auto", "auto"),
            "groq_fast": ("fast", "groq"),
            "gemini_quality": ("quality", "gemini"),
            "cerebras_fast": ("fast", "cerebras"),
            "openrouter_free": ("auto", "openrouter"),
        }
        mode, provider = profile_map.get(value, profile_map["auto"])
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("ai_mode", mode)
            self.services.settings.set("ai_provider", provider)
            self._sync_assistant_mode_from_legacy(ai_mode=mode, ai_provider=provider)
        self.aiModeChanged.emit()
        self.aiProviderChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()
        self.aiProfileChanged.emit()

    @Property(str, notify=aiModelChanged)
    def aiModel(self) -> str:
        return self.services.settings.get("ai_model", "openai/gpt-oss-20b")

    @aiModel.setter
    def aiModel(self, value: str) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("ai_model", value)
        self.aiModelChanged.emit()

    @Property(str, notify=localLlmModelChanged)
    def localLlmModel(self) -> str:
        return str(self.services.settings.get("local_llm_model", "") or "").strip()

    @localLlmModel.setter
    def localLlmModel(self, value: str) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("local_llm_model", str(value or "").strip())
        self.localLlmModelChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()

    @Property(str, notify=assistantModeChanged)
    def assistantMode(self) -> str:
        return self._assistant_mode_from_settings()

    @assistantMode.setter
    def assistantMode(self, value: str) -> None:
        self.setAssistantMode(value)

    @Property(str, notify=assistantModeChanged)
    def assistantModeSummary(self) -> str:
        return self._assistant_policy().display_summary

    @Property(str, notify=assistantModeChanged)
    def assistantModeDetails(self) -> str:
        mode = self.assistantMode
        for item in self._assistant_mode_options():
            if item.get("key") == mode:
                return str(item.get("note", "")).strip()
        return ""

    @Property(str, notify=assistantStatusChanged)
    def assistantUserStatus(self) -> str:
        return str(self._assistant_status_snapshot().get("userStatus", "Готово"))

    @Property("QVariantMap", notify=assistantStatusChanged)
    def assistantStatus(self) -> dict[str, object]:
        return self._assistant_status_snapshot()

    @Property(str, notify=connectionsChanged)
    def assistantReadiness(self) -> str:
        has_ai_key, telegram_ready = self._assistant_registration_state()
        if has_ai_key and telegram_ready:
            return "Подключения готовы"
        if has_ai_key:
            return "Нужен Telegram"
        if telegram_ready:
            return "Нужен AI key"
        return "Нужны AI key и Telegram"

    @Property("QVariantList", notify=assistantModeChanged)
    def assistantModeOptions(self) -> list[dict[str, str]]:
        return self._assistant_mode_options()

    @Property("QVariantList", notify=assistantStatusChanged)
    def localLlmBackendOptions(self) -> list[dict[str, str]]:
        return [
            {"key": "llama_cpp", "title": "llama.cpp"},
            {"key": "ollama", "title": "Ollama"},
        ]

    @Property("QVariantList", notify=assistantStatusChanged)
    def textBackendOverrideOptions(self) -> list[dict[str, str]]:
        return [
            {"key": "auto", "title": "Авто"},
            {"key": "local_llama", "title": "Local Llama"},
            {"key": "groq", "title": "Groq"},
            {"key": "gemini", "title": "Gemini"},
            {"key": "cerebras", "title": "Cerebras"},
            {"key": "openrouter", "title": "OpenRouter"},
        ]

    @Property("QVariantList", notify=assistantStatusChanged)
    def sttBackendOverrideOptions(self) -> list[dict[str, str]]:
        return [
            {"key": "auto", "title": "Авто"},
            {"key": "local_faster_whisper", "title": "local faster-whisper"},
            {"key": "local_vosk", "title": "local Vosk"},
            {"key": "groq_whisper", "title": "Groq Whisper"},
        ]

    @Property(str, notify=assistantModeChanged)
    def effectiveTextRoute(self) -> str:
        return self._format_route(self._assistant_policy().text_route)

    @Property(str, notify=assistantModeChanged)
    def effectiveSttRoute(self) -> str:
        return self._format_route(self._assistant_policy().stt_route)

    @Property(str, notify=assistantModeChanged)
    def privacyGuarantee(self) -> str:
        return self._privacy_text(self._assistant_policy().privacy_guarantee)

    @Property(str, notify=assistantModeChanged)
    def localReadiness(self) -> str:
        return self._local_readiness_text()

    @Property(str, notify=assistantStatusChanged)
    def localLlmBackend(self) -> str:
        backend = str(self.services.settings.get("local_llm_backend", DEFAULT_LOCAL_LLM_BACKEND) or "").strip().casefold()
        if backend not in {"llama_cpp", "ollama"}:
            return DEFAULT_LOCAL_LLM_BACKEND
        return backend

    @localLlmBackend.setter
    def localLlmBackend(self, value: str) -> None:
        backend = str(value or "").strip().casefold()
        if backend not in {"llama_cpp", "ollama"}:
            backend = DEFAULT_LOCAL_LLM_BACKEND
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("local_llm_backend", backend)
        self.localLlmBackendChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()

    @Property(str, notify=assistantStatusChanged)
    def textBackendOverride(self) -> str:
        value = str(self.services.settings.get("text_backend_override", "auto") or "").strip().casefold()
        return value if value in SUPPORTED_TEXT_BACKEND_OVERRIDES else "auto"

    @textBackendOverride.setter
    def textBackendOverride(self, value: str) -> None:
        override = str(value or "").strip().casefold()
        if override not in SUPPORTED_TEXT_BACKEND_OVERRIDES:
            override = "auto"
        if self.assistantMode == "private" and override not in {"auto", "local_llama"}:
            override = "local_llama"
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("text_backend_override", override)
        self.textBackendOverrideChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()

    @Property(str, notify=assistantStatusChanged)
    def sttBackendOverride(self) -> str:
        value = str(self.services.settings.get("stt_backend_override", "auto") or "").strip().casefold()
        return value if value in SUPPORTED_STT_BACKEND_OVERRIDES else "auto"

    @sttBackendOverride.setter
    def sttBackendOverride(self, value: str) -> None:
        override = str(value or "").strip().casefold()
        if override not in SUPPORTED_STT_BACKEND_OVERRIDES:
            override = "auto"
        if self.assistantMode == "private" and override == "groq_whisper":
            override = "auto"
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("stt_backend_override", override)
        self.sttBackendOverrideChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()

    @Property(str, notify=connectionsChanged)
    def groqApiKey(self) -> str:
        return str(self._registration().get("groq_api_key", "")).strip()

    @Property(str, notify=connectionsChanged)
    def groqApiKeyMasked(self) -> str:
        return self._mask_secret(self.groqApiKey)

    @Property(bool, notify=connectionsChanged)
    def groqApiKeySet(self) -> bool:
        return bool(self.groqApiKey)

    @Property(str, notify=connectionsChanged)
    def cerebrasApiKey(self) -> str:
        return str(self._registration().get("cerebras_api_key", "")).strip()

    @Property(str, notify=connectionsChanged)
    def cerebrasApiKeyMasked(self) -> str:
        return self._mask_secret(self.cerebrasApiKey)

    @Property(bool, notify=connectionsChanged)
    def cerebrasApiKeySet(self) -> bool:
        return bool(self.cerebrasApiKey)

    @Property(str, notify=connectionsChanged)
    def geminiApiKey(self) -> str:
        return str(self._registration().get("gemini_api_key", "")).strip()

    @Property(str, notify=connectionsChanged)
    def geminiApiKeyMasked(self) -> str:
        return self._mask_secret(self.geminiApiKey)

    @Property(bool, notify=connectionsChanged)
    def geminiApiKeySet(self) -> bool:
        return bool(self.geminiApiKey)

    @Property(str, notify=connectionsChanged)
    def openrouterApiKey(self) -> str:
        return str(self._registration().get("openrouter_api_key", "")).strip()

    @Property(str, notify=connectionsChanged)
    def openrouterApiKeyMasked(self) -> str:
        return self._mask_secret(self.openrouterApiKey)

    @Property(bool, notify=connectionsChanged)
    def openrouterApiKeySet(self) -> bool:
        return bool(self.openrouterApiKey)

    @Property(str, notify=connectionsChanged)
    def telegramBotToken(self) -> str:
        return str(self._registration().get("telegram_bot_token", "")).strip()

    @Property(str, notify=connectionsChanged)
    def telegramBotTokenMasked(self) -> str:
        return self._mask_secret(self.telegramBotToken)

    @Property(bool, notify=connectionsChanged)
    def telegramBotTokenSet(self) -> bool:
        return bool(self.telegramBotToken)

    @Property(str, notify=connectionsChanged)
    def telegramUserId(self) -> str:
        return str(self._registration().get("telegram_user_id", "")).strip()

    @Property(bool, notify=connectionsChanged)
    def telegramConfigured(self) -> bool:
        telegram = self._telegram_service_if_ready()
        if telegram is not None and hasattr(telegram, "is_configured"):
            return bool(telegram.is_configured())
        return bool(self.telegramBotToken and self.telegramUserId)

    @Property("QVariantMap", notify=telegramStatusChanged)
    def telegramStatus(self) -> dict[str, object]:
        telegram = self._telegram_service_if_ready()
        if telegram is not None and hasattr(telegram, "status_snapshot"):
            snapshot = telegram.status_snapshot()
            last_poll = getattr(snapshot, "last_poll_at_utc", None)
            return {
                "configured": bool(getattr(snapshot, "configured", False)),
                "connected": bool(getattr(snapshot, "connected", False)),
                "lastCommand": str(getattr(snapshot, "last_command", "")),
                "lastReply": str(getattr(snapshot, "last_reply", "")),
                "lastError": str(getattr(snapshot, "last_error", "")),
                "lastPollAt": last_poll.isoformat() if last_poll is not None else "",
            }
        return {
            "configured": self.telegramConfigured,
            "connected": False,
            "lastCommand": "",
            "lastReply": "",
            "lastError": "telegram service unavailable",
            "lastPollAt": "",
            "lastUpdateId": 0,
            "lastChatId": "",
        }

    @Property("QVariantMap", notify=connectionsChanged)
    def connections(self) -> dict[str, object]:
        registration = self._registration()
        return {
            "groqApiKey": self.groqApiKey,
            "groqApiKeyMasked": self.groqApiKeyMasked,
            "groqApiKeySet": self.groqApiKeySet,
            "cerebrasApiKey": self.cerebrasApiKey,
            "cerebrasApiKeyMasked": self.cerebrasApiKeyMasked,
            "cerebrasApiKeySet": self.cerebrasApiKeySet,
            "geminiApiKey": self.geminiApiKey,
            "geminiApiKeyMasked": self.geminiApiKeyMasked,
            "geminiApiKeySet": self.geminiApiKeySet,
            "openrouterApiKey": self.openrouterApiKey,
            "openrouterApiKeyMasked": self.openrouterApiKeyMasked,
            "openrouterApiKeySet": self.openrouterApiKeySet,
            "telegramBotToken": self.telegramBotToken,
            "telegramBotTokenMasked": self.telegramBotTokenMasked,
            "telegramBotTokenSet": self.telegramBotTokenSet,
            "telegramUserId": self.telegramUserId,
            "telegramConfigured": self.telegramConfigured,
            "saveHistoryEnabled": self.saveHistoryEnabled,
            "skipped": bool(registration.get("skipped", False)),
            "groq_api_key": self.groqApiKey,
            "cerebras_api_key": self.cerebrasApiKey,
            "gemini_api_key": self.geminiApiKey,
            "openrouter_api_key": self.openrouterApiKey,
            "telegram_bot_token": self.telegramBotToken,
            "telegram_user_id": self.telegramUserId,
        }

    @Slot(str)
    def setAssistantMode(self, value: str) -> None:
        mode = self._normalize_assistant_mode(value)
        ai_mode = "auto"
        voice_mode = "standard"
        privacy_mode = "balance"
        save_history_enabled = True
        allow_text_cloud_fallback = True
        allow_stt_cloud_fallback = True
        if mode == "fast":
            ai_mode = "fast"
            voice_mode = "fast"
        elif mode == "smart":
            ai_mode = "quality"
            voice_mode = "smart"
        elif mode == "private":
            ai_mode = "local"
            voice_mode = "private"
            privacy_mode = "private"
            save_history_enabled = False
            allow_text_cloud_fallback = False
            allow_stt_cloud_fallback = False

        with _SETTINGS_WRITE_LOCK:
            self.services.settings.bulk_update(
                {
                    "assistant_mode": mode,
                    "ai_mode": ai_mode,
                    "ai_provider": "auto",
                    "voice_mode": voice_mode,
                    "privacy_mode": privacy_mode,
                    "save_history_enabled": save_history_enabled,
                    "allow_text_cloud_fallback": allow_text_cloud_fallback,
                    "allow_stt_cloud_fallback": allow_stt_cloud_fallback,
                }
            )
        self.aiModeChanged.emit()
        self.aiProviderChanged.emit()
        self.aiProfileChanged.emit()
        self.saveHistoryEnabledChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantStatusChanged.emit()
        self.connectionsChanged.emit()
        self.dataSafetyChanged.emit()
        self._refresh_voice_mode_projection()

    @Property("QVariantList", notify=pinnedCommandsChanged)
    def pinnedCommands(self) -> list[dict[str, str]]:
        actions = self._actions_service_if_ready()
        if actions is None or not hasattr(actions, "pinned_commands"):
            return []
        return list(actions.pinned_commands())

    @Property(str, notify=connectionFeedbackChanged)
    def connectionFeedback(self) -> str:
        return self._connection_feedback

    @Property(bool, notify=telegramTestBusyChanged)
    def telegramTestBusy(self) -> bool:
        return self._telegram_test_busy

    @Property(bool, notify=updateCheckBusyChanged)
    def updateCheckBusy(self) -> bool:
        return self._update_check_busy

    @Property(str, notify=updateSummaryChanged)
    def updateSummary(self) -> str:
        updates = self._updates_service_if_ready()
        if updates is not None and hasattr(updates, "summary"):
            return str(updates.summary())
        return self._default_update_summary()

    @Property("QVariantMap", notify=updateSummaryChanged)
    def updateStatus(self) -> dict[str, object]:
        updates = self._updates_service_if_ready()
        if updates is not None and hasattr(updates, "status_snapshot"):
            return dict(updates.status_snapshot())
        return self._default_update_status()

    @Slot(str, str, str, result=bool)
    @Slot(str, str, str, str, str, str, result=bool)
    def saveConnections(
        self,
        groq_api_key: str,
        arg2: str,
        arg3: str,
        arg4: str = "",
        arg5: str = "",
        arg6: str = "",
    ) -> bool:
        if arg4 or arg5 or arg6:
            cerebras_api_key = arg2
            gemini_api_key = arg3
            openrouter_api_key = arg4
            telegram_bot_token = arg5
            telegram_user_id = arg6
        else:
            cerebras_api_key = ""
            gemini_api_key = ""
            openrouter_api_key = ""
            telegram_bot_token = arg2
            telegram_user_id = arg3
        registration = self._registration()
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.save_registration(
                {
                    "groq_api_key": self._resolve_secret_input(groq_api_key, str(registration.get("groq_api_key", ""))),
                    "cerebras_api_key": self._resolve_secret_input(
                        cerebras_api_key,
                        str(registration.get("cerebras_api_key", "")),
                    ),
                    "gemini_api_key": self._resolve_secret_input(
                        gemini_api_key,
                        str(registration.get("gemini_api_key", "")),
                    ),
                    "openrouter_api_key": self._resolve_secret_input(
                        openrouter_api_key,
                        str(registration.get("openrouter_api_key", "")),
                    ),
                    "telegram_bot_token": self._resolve_secret_input(
                        telegram_bot_token,
                        str(registration.get("telegram_bot_token", "")),
                    ),
                    "telegram_user_id": str(telegram_user_id or "").strip(),
                },
                skipped=False,
            )
        self._refresh_telegram_transport()
        self._connection_feedback = "Подключения сохранены."
        self.connectionsChanged.emit()
        self.connectionFeedbackChanged.emit()
        self.telegramStatusChanged.emit()
        return True

    @Slot()
    def clearTelegramConnection(self) -> None:
        registration = self._registration()
        payload = {
            "groq_api_key": str(registration.get("groq_api_key", "")).strip(),
            "cerebras_api_key": str(registration.get("cerebras_api_key", "")).strip(),
            "gemini_api_key": str(registration.get("gemini_api_key", "")).strip(),
            "openrouter_api_key": str(registration.get("openrouter_api_key", "")).strip(),
            "telegram_user_id": "",
            "telegram_bot_token": "",
        }
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.save_registration(payload, skipped=False)
        self._refresh_telegram_transport()
        self._connection_feedback = "Telegram отключён."
        self.connectionsChanged.emit()
        self.connectionFeedbackChanged.emit()
        self.telegramStatusChanged.emit()

    @Slot(result=bool)
    def sendTelegramTest(self) -> bool:
        telegram = getattr(self.services, "telegram", None)
        if telegram is None or not hasattr(telegram, "send_test_message"):
            self._connection_feedback = "Telegram-сервис недоступен."
            self.connectionFeedbackChanged.emit()
            self.telegramStatusChanged.emit()
            return False
        with self._operation_lock:
            if self._telegram_test_busy:
                self._connection_feedback = "Тест Telegram уже выполняется."
                self.connectionFeedbackChanged.emit()
                return False
            self._telegram_test_busy = True
        self.telegramTestBusyChanged.emit()

        def worker() -> None:
            ok = False
            feedback = ""
            try:
                ok = bool(telegram.send_test_message(text="JARVIS Unity на связи. Тест Telegram прошёл."))
            except Exception:  # noqa: BLE001
                ok = False
            if not feedback:
                if ok:
                    feedback = "Тестовое сообщение отправлено в Telegram."
                else:
                    feedback = "Telegram не ответил. Проверьте токен, Telegram ID и сеть."
            self._telegramTestFinished.emit(ok, feedback)

        try:
            self._worker_pool.submit(worker)
        except RuntimeError:
            with self._operation_lock:
                self._telegram_test_busy = False
            self.telegramTestBusyChanged.emit()
            self._connection_feedback = "Не удалось запустить тест Telegram."
            self.connectionFeedbackChanged.emit()
            self.telegramStatusChanged.emit()
            return False
        return True

    @Slot(result=bool)
    def checkForUpdates(self) -> bool:
        updates = getattr(self.services, "updates", None)
        if updates is None or not hasattr(updates, "check_now"):
            self.updateSummaryChanged.emit()
            return False
        with self._operation_lock:
            if self._update_check_busy:
                return False
            self._update_check_busy = True
        self.updateCheckBusyChanged.emit()

        def worker() -> None:
            ok = False
            try:
                result = updates.check_now()
                ok = bool(getattr(result, "ok", False))
            except Exception:  # noqa: BLE001
                ok = False
            self._updateCheckFinished.emit(ok)

        try:
            self._worker_pool.submit(worker)
        except RuntimeError:
            with self._operation_lock:
                self._update_check_busy = False
            self.updateCheckBusyChanged.emit()
            self.updateSummaryChanged.emit()
            return False
        return True

    @Slot(result=bool)
    def applyUpdate(self) -> bool:
        updates = getattr(self.services, "updates", None)
        if updates is None or not hasattr(updates, "apply_update"):
            self.updateSummaryChanged.emit()
            return False
        with self._operation_lock:
            if self._update_check_busy:
                return False
            self._update_check_busy = True
        self.updateCheckBusyChanged.emit()

        def worker() -> None:
            ok = False
            try:
                result = updates.apply_update()
                ok = bool(getattr(result, "ok", False))
            except Exception:  # noqa: BLE001
                ok = False
            self._updateCheckFinished.emit(ok)

        try:
            self._worker_pool.submit(worker)
        except RuntimeError:
            with self._operation_lock:
                self._update_check_busy = False
            self.updateCheckBusyChanged.emit()
            self.updateSummaryChanged.emit()
            return False
        return True

    @Slot(bool)
    def setSaveHistoryEnabled(self, value: bool) -> None:
        self.saveHistoryEnabled = value
        self.connectionsChanged.emit()
        self.dataSafetyChanged.emit()

    @Slot()
    def clearChatHistory(self) -> None:
        if hasattr(self.services, "chat_history"):
            self.services.chat_history.clear()
        if self.chat_bridge is not None and hasattr(self.chat_bridge, "clearHistory"):
            self.chat_bridge.clearHistory()
        self.dataSafetyChanged.emit()

    @Slot()
    def deleteAllData(self) -> dict[str, object]:
        with _SETTINGS_WRITE_LOCK:
            result = self.services.settings.clear_runtime_data()
            self.services.settings.reload()
        if hasattr(self.services, "actions"):
            self.services.actions.catalog = self.services.actions._merged_catalog()
        if hasattr(self.services, "chat_history"):
            self.services.chat_history.clear()
        if self.chat_bridge is not None and hasattr(self.chat_bridge, "clearHistory"):
            self.chat_bridge.clearHistory()
        self._refresh_telegram_transport()
        if self.app_bridge is not None and hasattr(self.app_bridge, "restartRegistration"):
            self.app_bridge.restartRegistration()
        self._connection_feedback = "Все данные удалены. Нужна повторная регистрация."
        self.themeModeChanged.emit()
        self.startupEnabledChanged.emit()
        self.minimizeToTrayEnabledChanged.emit()
        self.startMinimizedEnabledChanged.emit()
        self.saveHistoryEnabledChanged.emit()
        self.aiModeChanged.emit()
        self.aiProviderChanged.emit()
        self.aiProfileChanged.emit()
        self.aiModelChanged.emit()
        self.localLlmModelChanged.emit()
        self.assistantModeChanged.emit()
        self.connectionsChanged.emit()
        self.connectionFeedbackChanged.emit()
        self.telegramStatusChanged.emit()
        self.dataSafetyChanged.emit()
        self.pinnedCommandsChanged.emit()
        return result

    @Slot(str)
    def pinCommand(self, command_id: str) -> None:
        actions = getattr(self.services, "actions", None)
        if actions is None or not hasattr(actions, "pin_command"):
            return
        with _SETTINGS_WRITE_LOCK:
            actions.pin_command(command_id)
        if self.chat_bridge is not None and hasattr(self.chat_bridge, "refreshCatalog"):
            self.chat_bridge.refreshCatalog()
        self.pinnedCommandsChanged.emit()
        self.connectionsChanged.emit()

    @Slot(str)
    def unpinCommand(self, command_id: str) -> None:
        actions = getattr(self.services, "actions", None)
        if actions is None or not hasattr(actions, "unpin_command"):
            return
        with _SETTINGS_WRITE_LOCK:
            actions.unpin_command(command_id)
        if self.chat_bridge is not None and hasattr(self.chat_bridge, "refreshCatalog"):
            self.chat_bridge.refreshCatalog()
        self.pinnedCommandsChanged.emit()
        self.connectionsChanged.emit()

    @Slot(str)
    def togglePinnedCommand(self, command_id: str) -> None:
        pinned_ids = [item.get("id", "") for item in self.pinnedCommands]
        if str(command_id).strip() in pinned_ids:
            self.unpinCommand(command_id)
            return
        self.pinCommand(command_id)

    @Slot(str)
    def openScreen(self, screen: str) -> None:
        self.app_bridge.navigate(screen)

    def _registration(self) -> dict[str, object]:
        return dict(self.services.settings.get_registration())

    def _refresh_telegram_transport(self) -> None:
        if hasattr(self.services, "refresh_telegram_transport"):
            self.services.refresh_telegram_transport()
            return
        telegram = getattr(self.services, "telegram", None)
        if telegram is not None and hasattr(telegram, "refresh_configuration"):
            telegram.refresh_configuration()

    def _resolve_secret_input(self, value: str, current: str) -> str:
        clean = str(value or "").strip()
        if clean and (clean == self._mask_secret(current) or set(clean) <= {"•", "*"}):
            return str(current or "").strip()
        return clean

    def _mask_secret(self, value: str) -> str:
        return "••••••••" if str(value or "").strip() else ""

    @Slot(bool, str)
    def _on_telegram_test_finished(self, _ok: bool, feedback: str) -> None:
        with self._operation_lock:
            self._telegram_test_busy = False
        self._connection_feedback = str(feedback or "").strip()
        self.telegramTestBusyChanged.emit()
        self.connectionFeedbackChanged.emit()
        self.telegramStatusChanged.emit()

    @Slot(bool)
    def _on_update_check_finished(self, _ok: bool) -> None:
        with self._operation_lock:
            self._update_check_busy = False
        self.updateCheckBusyChanged.emit()
        self.updateSummaryChanged.emit()

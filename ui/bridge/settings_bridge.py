from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
import os

from PySide6.QtCore import QObject, Property, Signal, Slot

from core.ai.ai_service import SUPPORTED_AI_MODES, SUPPORTED_AI_PROFILES
from core.ai.local_llm_service import LocalLLMDiagnostics, LocalLLMService
from core.ai.local_runtime_service import LocalRuntimeService
from core.policy.assistant_mode import ASSISTANT_MODES, STT_OVERRIDES, TEXT_OVERRIDES, resolve_assistant_mode
from core.version import DEFAULT_VERSION


_SETTINGS_WRITE_LOCK = threading.RLock()


class SettingsBridge(QObject):
    themeModeChanged = Signal()
    startupEnabledChanged = Signal()
    minimizeToTrayEnabledChanged = Signal()
    startMinimizedEnabledChanged = Signal()
    saveHistoryEnabledChanged = Signal()
    assistantModeChanged = Signal()
    assistantModeOptionsChanged = Signal()
    assistantModeSummaryChanged = Signal()
    assistantUserStatusChanged = Signal()
    localLlmBackendChanged = Signal()
    localLlmBackendOptionsChanged = Signal()
    localLlmModelChanged = Signal()
    localReadinessChanged = Signal()
    localRuntimeBusyChanged = Signal()
    textBackendOverrideChanged = Signal()
    textBackendOverrideOptionsChanged = Signal()
    sttBackendOverrideChanged = Signal()
    sttBackendOverrideOptionsChanged = Signal()
    aiModeChanged = Signal()
    aiProviderChanged = Signal()
    aiProfileChanged = Signal()
    aiModelChanged = Signal()
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
    _localRuntimeFinished = Signal(bool, str, str)

    def __init__(self, state, services, app_bridge, chat_bridge=None) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self.app_bridge = app_bridge
        self.chat_bridge = chat_bridge
        self._connection_feedback = ""
        self._telegram_test_busy = False
        self._update_check_busy = False
        self._local_runtime_busy = False
        self._local_runtime_status_code = ""
        self._local_runtime_feedback = ""
        self._local_llm_diagnostics_cache: LocalLLMDiagnostics | None = None
        self._local_llm_diagnostics_requested = False
        self._local_llm_diagnostics_loaded = False
        self._local_llm_refresh_lock = threading.Lock()
        self._local_llm_refresh_inflight = False
        self._shutting_down = False
        self._update_summary_cache: str | None = None
        self._update_status_cache: dict[str, object] | None = None
        self._operation_lock = threading.Lock()
        self._worker_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="settings-bridge")
        self._telegramTestFinished.connect(self._on_telegram_test_finished)
        self._updateCheckFinished.connect(self._on_update_check_finished)
        self._localRuntimeFinished.connect(self._on_local_runtime_finished)

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

    def _local_runtime_service(self) -> LocalRuntimeService:
        service = getattr(self.services, "local_runtime", None)
        if service is not None and hasattr(service, "ensure_ready"):
            return service
        return LocalRuntimeService(self.services.settings)

    def _local_llm_probe_requested(self) -> bool:
        return (
            self._local_llm_diagnostics_requested
            or self._local_runtime_busy
            or bool(self._local_runtime_status_code)
            or bool(self._local_runtime_feedback)
        )

    def _local_llm_diagnostics(self) -> LocalLLMDiagnostics:
        if self._local_llm_diagnostics_cache is not None:
            if self._local_llm_probe_requested() and not self._local_llm_diagnostics_loaded:
                self._schedule_local_llm_refresh()
            return self._local_llm_diagnostics_cache
        self._local_llm_diagnostics_cache = self._placeholder_local_llm_diagnostics()
        self._local_llm_diagnostics_loaded = False
        if self._local_llm_probe_requested():
            self._schedule_local_llm_refresh()
        return self._local_llm_diagnostics_cache

    def _placeholder_local_llm_diagnostics(self) -> LocalLLMDiagnostics:
        backend = self._normalize_local_backend(self.services.settings.get("local_llm_backend", "auto"))
        model = str(self.services.settings.get("local_llm_model", "")).strip()
        if backend == "ollama":
            return LocalLLMDiagnostics(
                ready=False,
                backend="ollama",
                model_path=model,
                detail="Проверяю Ollama...",
                user_status="Проверяю локальную модель...",
                action_label="Открыть Ollama",
                action_url="https://docs.ollama.com/",
            )
        if backend == "llama_cpp":
            return LocalLLMDiagnostics(
                ready=False,
                backend="llama_cpp",
                model_path=model,
                detail="Проверяю локальную модель...",
                user_status="Проверяю локальную модель...",
                action_label="Открыть llama.cpp",
                action_url="https://github.com/abetlen/llama-cpp-python",
            )
        return LocalLLMDiagnostics(
            ready=False,
            backend="auto",
            model_path=model,
            detail="Проверяю локальный пакет...",
            user_status="Проверяю локальную модель...",
            action_label="",
            action_url="",
        )

    def _load_local_llm_diagnostics(self) -> LocalLLMDiagnostics:
        try:
            return LocalLLMService(self.services.settings).diagnostics()
        except Exception:  # noqa: BLE001
            return LocalLLMDiagnostics(
                ready=False,
                backend="auto",
                model_path="",
                detail="Локальный пакет недоступен.",
                user_status="Локальная модель не готова.",
                action_label="",
                action_url="",
            )

    def _refresh_local_llm_diagnostics(self) -> LocalLLMDiagnostics:
        self._local_llm_diagnostics_cache = self._placeholder_local_llm_diagnostics()
        self._local_llm_diagnostics_loaded = False
        if self._local_llm_probe_requested():
            self._schedule_local_llm_refresh()
        return self._local_llm_diagnostics_cache

    def _schedule_local_llm_refresh(self) -> None:
        if self._shutting_down or not self._local_llm_probe_requested():
            return
        with self._local_llm_refresh_lock:
            if self._local_llm_refresh_inflight:
                return
            self._local_llm_refresh_inflight = True

        def worker() -> None:
            try:
                diagnostics = self._load_local_llm_diagnostics()
            finally:
                with self._local_llm_refresh_lock:
                    self._local_llm_refresh_inflight = False
            if self._shutting_down:
                return
            self._local_llm_diagnostics_cache = diagnostics
            self._local_llm_diagnostics_loaded = True
            self.localReadinessChanged.emit()
            self.assistantUserStatusChanged.emit()
            self.assistantModeSummaryChanged.emit()

        try:
            self._worker_pool.submit(worker)
        except RuntimeError:
            with self._local_llm_refresh_lock:
                self._local_llm_refresh_inflight = False

    def _refresh_update_snapshot(self) -> None:
        updates = self._updates_service_if_ready()
        if updates is not None and hasattr(updates, "summary") and hasattr(updates, "status_snapshot"):
            self._update_summary_cache = str(updates.summary())
            self._update_status_cache = dict(updates.status_snapshot())
            return
        self._update_summary_cache = self._default_update_summary()
        self._update_status_cache = self._default_update_status()

    def _normalize_ai_mode(self, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode in SUPPORTED_AI_MODES:
            return mode
        return "auto"

    def _normalize_assistant_mode(self, value: str) -> str:
        mode = str(value or "").strip().lower()
        if mode in ASSISTANT_MODES:
            return mode
        return resolve_assistant_mode(self.services.settings)

    def _normalize_local_backend(self, value: str) -> str:
        backend = str(value or "").strip().lower()
        if backend in {"auto", "ollama", "llama_cpp"}:
            return backend
        return "auto"

    def _normalize_override(self, value: str, allowed: set[str]) -> str:
        override = str(value or "").strip().lower()
        if override in allowed:
            return override
        return "auto"

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
        self.connectionsChanged.emit()
        self.dataSafetyChanged.emit()

    @Property(str, notify=assistantModeChanged)
    def assistantMode(self) -> str:
        return self._normalize_assistant_mode(self.services.settings.get("assistant_mode", "standard"))

    @assistantMode.setter
    def assistantMode(self, value: str) -> None:
        mode = self._normalize_assistant_mode(value)
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("assistant_mode", mode)
        self.assistantModeChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()
        self.localReadinessChanged.emit()

    @Property("QVariantList", notify=assistantModeOptionsChanged)
    def assistantModeOptions(self) -> list[dict[str, str]]:
        return [
            {"key": "fast", "title": "Быстрый"},
            {"key": "standard", "title": "Стандартный"},
            {"key": "smart", "title": "Умный"},
            {"key": "private", "title": "Приватный"},
        ]

    @Property(str, notify=assistantModeSummaryChanged)
    def assistantModeSummary(self) -> str:
        mode = self.assistantMode
        if mode == "fast":
            return "Самый быстрый путь ответа."
        if mode == "smart":
            return "Приоритет качеству ответа."
        if mode == "private":
            return "Только локальная работа."
        return "Сначала локально, потом облако."

    @Property(str, notify=assistantUserStatusChanged)
    def assistantUserStatus(self) -> str:
        mode = self.assistantMode
        if not self._local_llm_probe_requested():
            if mode == "private":
                return "Локальный режим не установлен"
            return "Работает через облако"
        diagnostics = self._local_llm_diagnostics()
        if diagnostics.ready:
            return "Локально готово"
        if mode == "private":
            return "Локальный режим не установлен"
        return "Работает через облако"

    @Property(str, notify=localLlmBackendChanged)
    def localLlmBackend(self) -> str:
        return self._normalize_local_backend(self.services.settings.get("local_llm_backend", "auto"))

    @localLlmBackend.setter
    def localLlmBackend(self, value: str) -> None:
        backend = self._normalize_local_backend(value)
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("local_llm_backend", backend)
        self._local_llm_diagnostics_requested = True
        self._refresh_local_llm_diagnostics()
        self.localLlmBackendChanged.emit()
        self.localReadinessChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()

    @Property("QVariantList", notify=localLlmBackendOptionsChanged)
    def localLlmBackendOptions(self) -> list[dict[str, str]]:
        return [
            {"key": "auto", "title": "Авто"},
            {"key": "ollama", "title": "Ollama"},
            {"key": "llama_cpp", "title": "llama.cpp"},
        ]

    @Property(str, notify=localLlmModelChanged)
    def localLlmModel(self) -> str:
        return str(self.services.settings.get("local_llm_model", "")).strip()

    @localLlmModel.setter
    def localLlmModel(self, value: str) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("local_llm_model", str(value or "").strip())
        self._local_llm_diagnostics_requested = True
        self._refresh_local_llm_diagnostics()
        self.localLlmModelChanged.emit()
        self.localReadinessChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()

    @Property(str, notify=localReadinessChanged)
    def localReadiness(self) -> str:
        if not self._local_llm_probe_requested():
            return ""
        return self._local_llm_diagnostics().user_status

    @Property(bool, notify=localReadinessChanged)
    def localLlmReady(self) -> bool:
        if not self._local_llm_probe_requested():
            return False
        return bool(self._local_llm_diagnostics().ready)

    @Property(bool, notify=localRuntimeBusyChanged)
    def localRuntimeBusy(self) -> bool:
        return self._local_runtime_busy

    @Property(str, notify=localReadinessChanged)
    def localRuntimeActionText(self) -> str:
        if self.localLlmReady:
            return ""
        if self._local_runtime_busy:
            return "Подготавливаю локальный режим..."
        if self._local_runtime_status_code == "installer_started":
            return "Продолжить подготовку"
        if self._local_runtime_status_code == "model_pull_failed":
            return "Повторить подготовку"
        return "Подготовить локальный режим"

    @Property(bool, notify=localReadinessChanged)
    def localRuntimeActionVisible(self) -> bool:
        return os.name == "nt" and not self.localLlmReady

    @Property(str, notify=localReadinessChanged)
    def localRuntimeStatus(self) -> str:
        if self._local_runtime_busy:
            return "Скачиваю и настраиваю локальный режим. Это может занять несколько минут."
        if self.localLlmReady:
            return "Локальный режим готов."
        if self._local_runtime_status_code == "installer_started":
            return "Запущен установщик локального движка. После завершения нажмите ещё раз."
        if self._local_runtime_status_code == "model_pull_failed":
            return "Не удалось догрузить локальную модель. Попробуйте ещё раз."
        if self._local_runtime_status_code == "runtime_failed":
            return "Не удалось подготовить локальный режим. Попробуйте ещё раз."
        if self.assistantMode == "private":
            return "Для приватного режима нужен локальный пакет. Его можно подготовить одной кнопкой."
        return ""

    @Property(str, notify=textBackendOverrideChanged)
    def textBackendOverride(self) -> str:
        return self._normalize_override(self.services.settings.get("text_backend_override", "auto"), TEXT_OVERRIDES)

    @textBackendOverride.setter
    def textBackendOverride(self, value: str) -> None:
        override = self._normalize_override(value, TEXT_OVERRIDES)
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("text_backend_override", override)
        self.textBackendOverrideChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()

    @Property("QVariantList", notify=textBackendOverrideOptionsChanged)
    def textBackendOverrideOptions(self) -> list[dict[str, str]]:
        return [
            {"key": "auto", "title": "Авто"},
            {"key": "local_llama", "title": "Локальная Llama"},
            {"key": "groq", "title": "Groq"},
            {"key": "cerebras", "title": "Cerebras"},
            {"key": "gemini", "title": "Gemini"},
            {"key": "openrouter", "title": "OpenRouter"},
        ]

    @Property(str, notify=sttBackendOverrideChanged)
    def sttBackendOverride(self) -> str:
        return self._normalize_override(self.services.settings.get("stt_backend_override", "auto"), STT_OVERRIDES)

    @sttBackendOverride.setter
    def sttBackendOverride(self, value: str) -> None:
        override = self._normalize_override(value, STT_OVERRIDES)
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("stt_backend_override", override)
        self.sttBackendOverrideChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()

    @Property(str, notify=aiModeChanged)
    def aiMode(self) -> str:
        return self._normalize_ai_mode(self.services.settings.get("ai_mode", "auto"))

    @aiMode.setter
    def aiMode(self, value: str) -> None:
        value = self._normalize_ai_mode(value)
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("ai_mode", value)
        self.aiModeChanged.emit()
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
        self.aiProviderChanged.emit()
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
        self.aiModeChanged.emit()
        self.aiProviderChanged.emit()
        self.aiProfileChanged.emit()

    @Property(str, notify=aiModelChanged)
    def aiModel(self) -> str:
        return self.services.settings.get("ai_model", "openai/gpt-oss-20b")

    @aiModel.setter
    def aiModel(self, value: str) -> None:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.set("ai_model", value)
        self.aiModelChanged.emit()

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

    @Property(bool, notify=connectionsChanged)
    def cerebrasApiKeySet(self) -> bool:
        return bool(self.cerebrasApiKey)

    @Property(str, notify=connectionsChanged)
    def geminiApiKey(self) -> str:
        return str(self._registration().get("gemini_api_key", "")).strip()

    @Property(bool, notify=connectionsChanged)
    def geminiApiKeySet(self) -> bool:
        return bool(self.geminiApiKey)

    @Property(str, notify=connectionsChanged)
    def openrouterApiKey(self) -> str:
        return str(self._registration().get("openrouter_api_key", "")).strip()

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
            "lastError": "Telegram-сервис недоступен.",
            "lastPollAt": "",
        }

    @Property("QVariantMap", notify=connectionsChanged)
    def connections(self) -> dict[str, object]:
        registration = self._registration()
        return {
            "groqApiKey": self.groqApiKey,
            "groqApiKeyMasked": self.groqApiKeyMasked,
            "groqApiKeySet": self.groqApiKeySet,
            "cerebrasApiKey": self.cerebrasApiKey,
            "cerebrasApiKeyMasked": self._mask_secret(self.cerebrasApiKey),
            "cerebrasApiKeySet": self.cerebrasApiKeySet,
            "geminiApiKey": self.geminiApiKey,
            "geminiApiKeyMasked": self._mask_secret(self.geminiApiKey),
            "geminiApiKeySet": self.geminiApiKeySet,
            "openrouterApiKey": self.openrouterApiKey,
            "openrouterApiKeyMasked": self._mask_secret(self.openrouterApiKey),
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
        if self._update_summary_cache is None:
            self._refresh_update_snapshot()
        return self._update_summary_cache

    @Property("QVariantMap", notify=updateSummaryChanged)
    def updateStatus(self) -> dict[str, object]:
        if self._update_status_cache is None:
            self._refresh_update_snapshot()
        return dict(self._update_status_cache)

    @Slot(str, str, str, str, str, str, result=bool)
    def saveConnections(
        self,
        groq_api_key: str,
        cerebras_api_key: str,
        gemini_api_key: str,
        openrouter_api_key: str,
        telegram_bot_token: str,
        telegram_user_id: str,
    ) -> bool:
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

    @Slot(str, str, str, str, str, result=bool)
    def saveAdvancedConnections(
        self,
        gemini_api_key: str,
        cerebras_api_key: str,
        openrouter_api_key: str,
        local_llm_backend: str,
        local_llm_model: str,
    ) -> bool:
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.save_registration(
                {
                    "groq_api_key": str(self.groqApiKey),
                    "cerebras_api_key": self._resolve_secret_input(
                        cerebras_api_key,
                        str(self._registration().get("cerebras_api_key", "")),
                    ),
                    "gemini_api_key": self._resolve_secret_input(
                        gemini_api_key,
                        str(self._registration().get("gemini_api_key", "")),
                    ),
                    "openrouter_api_key": self._resolve_secret_input(
                        openrouter_api_key,
                        str(self._registration().get("openrouter_api_key", "")),
                    ),
                    "telegram_bot_token": str(self.telegramBotToken),
                    "telegram_user_id": str(self.telegramUserId),
                },
                skipped=bool(self._registration().get("skipped", False)),
            )
            self.services.settings.set("local_llm_backend", self._normalize_local_backend(local_llm_backend))
            self.services.settings.set("local_llm_model", str(local_llm_model or "").strip())
        self._local_llm_diagnostics_requested = True
        self._refresh_local_llm_diagnostics()
        self._connection_feedback = "Дополнительные подключения сохранены."
        self.localLlmBackendChanged.emit()
        self.localLlmModelChanged.emit()
        self.localReadinessChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()
        self.connectionsChanged.emit()
        self.connectionFeedbackChanged.emit()
        return True

    @Slot(result=bool)
    def installLocalRuntime(self) -> bool:
        with self._operation_lock:
            if self._local_runtime_busy:
                return False
            self._local_runtime_busy = True
        self._local_llm_diagnostics_requested = True
        self._local_runtime_feedback = "Готовлю локальную модель..."
        self.localRuntimeBusyChanged.emit()
        self.localReadinessChanged.emit()

        def worker() -> None:
            ok = False
            status_code = "runtime_failed"
            message = "Не удалось подготовить локальный пакет."
            try:
                result = self._local_runtime_service().ensure_ready(self.localLlmModel)
                ok = bool(getattr(result, "ok", False))
                status_code = str(getattr(result, "status_code", "") or "runtime_finished")
                message = str(getattr(result, "message", "") or message)
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or message
            self._localRuntimeFinished.emit(ok, status_code, message)

        try:
            self._worker_pool.submit(worker)
        except RuntimeError:
            with self._operation_lock:
                self._local_runtime_busy = False
            self._local_runtime_feedback = "Не удалось запустить подготовку локальной модели."
            self.localRuntimeBusyChanged.emit()
            self.localReadinessChanged.emit()
            return False
        return True

    @Slot()
    def clearTelegramConnection(self) -> None:
        registration = self._registration()
        payload = {
            "groq_api_key": str(registration.get("groq_api_key", "")).strip(),
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
            self._refresh_update_snapshot()
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
            self._refresh_update_snapshot()
            self.updateSummaryChanged.emit()
            return False
        return True

    @Slot(result=bool)
    def applyUpdate(self) -> bool:
        updates = getattr(self.services, "updates", None)
        if updates is None or not hasattr(updates, "apply_update"):
            self._refresh_update_snapshot()
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
            self._refresh_update_snapshot()
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
        self._local_llm_diagnostics_requested = False
        self._local_runtime_status_code = ""
        self._local_runtime_feedback = ""
        self._refresh_local_llm_diagnostics()
        self._refresh_update_snapshot()
        self._connection_feedback = "Все данные удалены. Нужна повторная регистрация."
        self.themeModeChanged.emit()
        self.startupEnabledChanged.emit()
        self.minimizeToTrayEnabledChanged.emit()
        self.startMinimizedEnabledChanged.emit()
        self.saveHistoryEnabledChanged.emit()
        self.assistantModeChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()
        self.localLlmBackendChanged.emit()
        self.localLlmModelChanged.emit()
        self.localReadinessChanged.emit()
        self.textBackendOverrideChanged.emit()
        self.sttBackendOverrideChanged.emit()
        self.aiModeChanged.emit()
        self.aiProviderChanged.emit()
        self.aiProfileChanged.emit()
        self.aiModelChanged.emit()
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
        self._refresh_update_snapshot()
        self.updateSummaryChanged.emit()

    @Slot(bool, str, str)
    def _on_local_runtime_finished(self, _ok: bool, status_code: str, feedback: str) -> None:
        with self._operation_lock:
            self._local_runtime_busy = False
        self._local_llm_diagnostics_requested = True
        self._local_runtime_status_code = str(status_code or "").strip()
        self._local_runtime_feedback = str(feedback or "").strip()
        self._local_llm_diagnostics_cache = self._load_local_llm_diagnostics()
        self._local_llm_diagnostics_loaded = True
        self.localRuntimeBusyChanged.emit()
        self.localLlmBackendChanged.emit()
        self.localLlmModelChanged.emit()
        self.localReadinessChanged.emit()
        self.assistantModeSummaryChanged.emit()
        self.assistantUserStatusChanged.emit()

    @Slot()
    def requestLocalDiagnostics(self) -> None:
        if self._shutting_down:
            return
        self._local_llm_diagnostics_requested = True
        self._refresh_local_llm_diagnostics()
        self.localReadinessChanged.emit()
        self.assistantUserStatusChanged.emit()
        self.assistantModeSummaryChanged.emit()

    @Slot()
    def shutdown(self) -> None:
        self._shutting_down = True
        try:
            self._worker_pool.shutdown(wait=True, cancel_futures=True)
        except RuntimeError:
            pass

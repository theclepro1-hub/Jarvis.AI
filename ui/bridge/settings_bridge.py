from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Property, Signal, Slot

from core.updates.update_service import DEFAULT_VERSION


_SETTINGS_WRITE_LOCK = threading.RLock()


class SettingsBridge(QObject):
    themeModeChanged = Signal()
    startupEnabledChanged = Signal()
    minimizeToTrayEnabledChanged = Signal()
    startMinimizedEnabledChanged = Signal()
    saveHistoryEnabledChanged = Signal()
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

    def _updates_service_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_updates"):
            return getattr(self.services, "_updates")
        if hasattr(self.services, "__dict__") and "updates" in vars(self.services):
            return vars(self.services).get("updates")
        return None

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

    @Property(str, notify=aiModeChanged)
    def aiMode(self) -> str:
        return self.services.settings.get("ai_mode", "auto")

    @aiMode.setter
    def aiMode(self, value: str) -> None:
        if value not in {"auto", "fast", "quality", "local"}:
            value = "auto"
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
        if mode == "local":
            return "local"
        if provider == "groq" and mode == "fast":
            return "groq_fast"
        if provider == "gemini" and mode == "quality":
            return "gemini_quality"
        if provider == "cerebras" and mode == "fast":
            return "cerebras_fast"
        if provider == "openrouter":
            return "openrouter_free"
        return "auto"

    @aiProfile.setter
    def aiProfile(self, value: str) -> None:
        profile_map = {
            "auto": ("auto", "auto"),
            "groq_fast": ("fast", "groq"),
            "gemini_quality": ("quality", "gemini"),
            "cerebras_fast": ("fast", "cerebras"),
            "openrouter_free": ("auto", "openrouter"),
            "local": ("local", "auto"),
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
        telegram = getattr(self.services, "telegram", None)
        if telegram is not None and hasattr(telegram, "is_configured"):
            return bool(telegram.is_configured())
        return bool(self.telegramBotToken and self.telegramUserId)

    @Property("QVariantMap", notify=telegramStatusChanged)
    def telegramStatus(self) -> dict[str, object]:
        telegram = getattr(self.services, "telegram", None)
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
            "telegramBotToken": self.telegramBotToken,
            "telegramBotTokenMasked": self.telegramBotTokenMasked,
            "telegramBotTokenSet": self.telegramBotTokenSet,
            "telegramUserId": self.telegramUserId,
            "telegramConfigured": self.telegramConfigured,
            "saveHistoryEnabled": self.saveHistoryEnabled,
            "skipped": bool(registration.get("skipped", False)),
            "groq_api_key": self.groqApiKey,
            "telegram_bot_token": self.telegramBotToken,
            "telegram_user_id": self.telegramUserId,
        }

    @Property("QVariantList", notify=pinnedCommandsChanged)
    def pinnedCommands(self) -> list[dict[str, str]]:
        actions = getattr(self.services, "actions", None)
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
    def saveConnections(self, groq_api_key: str, telegram_bot_token: str, telegram_user_id: str) -> bool:
        registration = self._registration()
        with _SETTINGS_WRITE_LOCK:
            self.services.settings.save_registration(
                {
                    "groq_api_key": self._resolve_secret_input(groq_api_key, str(registration.get("groq_api_key", ""))),
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
            except Exception as exc:  # noqa: BLE001
                ok = False
                feedback = f"Telegram не ответил: {type(exc).__name__}"
            if not feedback:
                if ok:
                    feedback = "Тестовое сообщение отправлено в Telegram."
                else:
                    error = ""
                    if hasattr(telegram, "last_error"):
                        error = str(telegram.last_error()).strip()
                    feedback = f"Telegram не ответил: {error or 'проверьте токен и ID'}"
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

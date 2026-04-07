from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot


class SettingsBridge(QObject):
    themeModeChanged = Signal()
    startupEnabledChanged = Signal()
    minimizeToTrayEnabledChanged = Signal()
    startMinimizedEnabledChanged = Signal()
    aiModeChanged = Signal()
    aiProviderChanged = Signal()
    aiProfileChanged = Signal()
    aiModelChanged = Signal()
    connectionsChanged = Signal()
    connectionFeedbackChanged = Signal()
    updateSummaryChanged = Signal()

    def __init__(self, state, services, app_bridge) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self.app_bridge = app_bridge
        self._connection_feedback = ""

    @Property(str, notify=themeModeChanged)
    def themeMode(self) -> str:
        return self.services.settings.get("theme_mode", "midnight")

    @themeMode.setter
    def themeMode(self, value: str) -> None:
        self.services.settings.set("theme_mode", value)
        self.themeModeChanged.emit()

    @Property(bool, notify=startupEnabledChanged)
    def startupEnabled(self) -> bool:
        return self.services.settings.get("startup_enabled", False)

    @startupEnabled.setter
    def startupEnabled(self, value: bool) -> None:
        self.services.startup.set_enabled(value, minimized=self.startMinimizedEnabled)
        self.services.settings.set("startup_enabled", self.services.startup.is_enabled())
        self.startupEnabledChanged.emit()

    @Property(bool, notify=minimizeToTrayEnabledChanged)
    def minimizeToTrayEnabled(self) -> bool:
        return self.services.settings.get("minimize_to_tray_enabled", True)

    @minimizeToTrayEnabled.setter
    def minimizeToTrayEnabled(self, value: bool) -> None:
        self.services.settings.set("minimize_to_tray_enabled", value)
        self.minimizeToTrayEnabledChanged.emit()

    @Property(bool, notify=startMinimizedEnabledChanged)
    def startMinimizedEnabled(self) -> bool:
        return self.services.settings.get("start_minimized_enabled", True)

    @startMinimizedEnabled.setter
    def startMinimizedEnabled(self, value: bool) -> None:
        self.services.settings.set("start_minimized_enabled", value)
        if self.startupEnabled:
            self.services.startup.set_enabled(True, minimized=value)
        self.startMinimizedEnabledChanged.emit()

    @Property(str, notify=aiModeChanged)
    def aiMode(self) -> str:
        return self.services.settings.get("ai_mode", "auto")

    @aiMode.setter
    def aiMode(self, value: str) -> None:
        if value not in {"auto", "fast", "quality", "local"}:
            value = "auto"
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
            "skipped": bool(registration.get("skipped", False)),
            # Snake-case keys keep this bridge usable from tests and older QML bindings.
            "groq_api_key": self.groqApiKey,
            "telegram_bot_token": self.telegramBotToken,
            "telegram_user_id": self.telegramUserId,
        }

    @Property(str, notify=connectionFeedbackChanged)
    def connectionFeedback(self) -> str:
        return self._connection_feedback

    @Slot(str, str, str, result=bool)
    def saveConnections(self, groq_api_key: str, telegram_bot_token: str, telegram_user_id: str) -> bool:
        registration = self._registration()
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
        return True

    @Slot()
    def clearTelegramConnection(self) -> None:
        registration = self._registration()
        payload = {
            "groq_api_key": str(registration.get("groq_api_key", "")).strip(),
            "telegram_user_id": "",
            "telegram_bot_token": "",
        }
        self.services.settings.save_registration(payload, skipped=False)
        self._refresh_telegram_transport()
        self._connection_feedback = "Telegram отключён."
        self.connectionsChanged.emit()
        self.connectionFeedbackChanged.emit()

    @Property(str, notify=updateSummaryChanged)
    def updateSummary(self) -> str:
        return self.services.updates.summary()

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

from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot


class RegistrationBridge(QObject):
    registrationChanged = Signal()
    feedbackChanged = Signal()

    def __init__(self, state, services, app_bridge) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self.app_bridge = app_bridge
        self._feedback = ""

    @Property("QVariantMap", notify=registrationChanged)
    def registration(self) -> dict[str, str]:
        record = self.services.registration.load()
        return {
            "groq_api_key": record.groq_api_key,
            "cerebras_api_key": record.cerebras_api_key,
            "gemini_api_key": record.gemini_api_key,
            "openrouter_api_key": record.openrouter_api_key,
            "telegram_user_id": record.telegram_user_id,
            "telegram_bot_token": record.telegram_bot_token,
            "skipped": record.skipped,
        }

    @Property(str, notify=feedbackChanged)
    def feedback(self) -> str:
        return self._feedback

    @Slot(str, str, str)
    @Slot(str, str, str, str, str, str)
    def saveRegistration(
        self,
        groq_api_key: str,
        arg2: str,
        arg3: str,
        arg4: str = "",
        arg5: str = "",
        arg6: str = "",
    ) -> None:
        if arg4 or arg5 or arg6:
            cerebras_api_key = arg2
            gemini_api_key = arg3
            openrouter_api_key = arg4
            telegram_user_id = arg5
            telegram_bot_token = arg6
        else:
            cerebras_api_key = ""
            gemini_api_key = ""
            openrouter_api_key = ""
            telegram_user_id = arg2
            telegram_bot_token = arg3
        record = self.services.registration.save(
            groq_api_key,
            cerebras_api_key,
            gemini_api_key,
            openrouter_api_key,
            telegram_user_id,
            telegram_bot_token,
        )
        if record.is_complete:
            self._feedback = "Подключения сохранены. Открываю JARVIS."
            self.feedbackChanged.emit()
            self.registrationChanged.emit()
            self.app_bridge.finishRegistration()
            return
        self._feedback = "Заполните три поля: ключ Groq, Telegram ID и токен Telegram-бота."
        self.feedbackChanged.emit()

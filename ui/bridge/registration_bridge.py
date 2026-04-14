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
            "telegram_user_id": record.telegram_user_id,
            "telegram_bot_token": record.telegram_bot_token,
        }

    @Property(str, notify=feedbackChanged)
    def feedback(self) -> str:
        return self._feedback

    @Slot(str, str, str)
    def saveRegistration(self, groq_api_key: str, telegram_user_id: str, telegram_bot_token: str) -> None:
        record = self.services.registration.save(groq_api_key, telegram_user_id, telegram_bot_token)
        if self.services.registration.is_complete(record):
            self._feedback = "Подключение сохранено. Можно переходить в JARVIS."
            self.feedbackChanged.emit()
            self.registrationChanged.emit()
            self.app_bridge.finishRegistration()
            return
        if self.services.registration.requires_cloud_for_completion():
            self._feedback = "Нужны три поля: ключ облачного ИИ, Telegram ID и токен Telegram-бота."
        else:
            self._feedback = "Для приватного режима нужны Telegram ID и токен Telegram-бота."
        self.feedbackChanged.emit()

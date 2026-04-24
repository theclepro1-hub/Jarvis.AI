from __future__ import annotations

from dataclasses import fields

from core.registration.registration_model import RegistrationModel


class RegistrationService:
    def __init__(self, settings_service) -> None:
        self.settings = settings_service

    def load(self) -> RegistrationModel:
        payload = self.settings.get_registration()
        if not isinstance(payload, dict):
            return RegistrationModel()
        allowed = {item.name for item in fields(RegistrationModel)}
        sanitized = {key: value for key, value in payload.items() if key in allowed}
        return RegistrationModel(**sanitized)

    def save(self, groq_api_key: str, telegram_user_id: str, telegram_bot_token: str) -> RegistrationModel:
        payload = {
            "groq_api_key": groq_api_key.strip(),
            "telegram_user_id": telegram_user_id.strip(),
            "telegram_bot_token": telegram_bot_token.strip(),
        }
        self.settings.save_registration(payload, skipped=False)
        return self.load()

    def skip(self) -> RegistrationModel:
        current = self.settings.get_registration()
        self.settings.save_registration(current, skipped=True)
        return self.load()

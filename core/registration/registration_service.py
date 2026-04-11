from __future__ import annotations

from core.registration.registration_model import RegistrationModel


class RegistrationService:
    def __init__(self, settings_service) -> None:
        self.settings = settings_service

    def load(self) -> RegistrationModel:
        payload = self.settings.get_registration()
        return RegistrationModel(**payload)

    def save(
        self,
        groq_api_key: str,
        cerebras_api_key: str,
        gemini_api_key: str,
        openrouter_api_key: str,
        telegram_user_id: str,
        telegram_bot_token: str,
    ) -> RegistrationModel:
        payload = {
            "groq_api_key": groq_api_key.strip(),
            "cerebras_api_key": cerebras_api_key.strip(),
            "gemini_api_key": gemini_api_key.strip(),
            "openrouter_api_key": openrouter_api_key.strip(),
            "telegram_user_id": telegram_user_id.strip(),
            "telegram_bot_token": telegram_bot_token.strip(),
        }
        self.settings.save_registration(payload, skipped=False)
        return self.load()

    def skip(self) -> RegistrationModel:
        current = self.settings.get_registration()
        self.settings.save_registration(current, skipped=True)
        return self.load()

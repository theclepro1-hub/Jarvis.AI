from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RegistrationModel:
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    deepseek_api_key: str = ""
    xai_api_key: str = ""
    telegram_user_id: str = ""
    telegram_bot_token: str = ""
    skipped: bool = False

    @property
    def has_cloud_completion_key(self) -> bool:
        return any(
            key.strip()
            for key in (
                self.groq_api_key,
                self.cerebras_api_key,
                self.gemini_api_key,
                self.openrouter_api_key,
                self.deepseek_api_key,
                self.xai_api_key,
            )
        )

    @property
    def is_complete(self) -> bool:
        return bool(
            self.has_cloud_completion_key
            and self.telegram_user_id.strip()
            and self.telegram_bot_token.strip()
        )

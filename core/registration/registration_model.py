from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RegistrationModel:
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    telegram_user_id: str = ""
    telegram_bot_token: str = ""
    skipped: bool = False

    @property
    def is_complete(self) -> bool:
        return bool(
            self.groq_api_key.strip()
            and self.telegram_user_id.strip()
            and self.telegram_bot_token.strip()
        )

import json

from core.settings.settings_service import SettingsService
from core.voice.voice_service import VoiceService
from core.voice.wake_service import WakeService


class FakeStore:
    def __init__(self) -> None:
        self.payload = {
            "theme_mode": "midnight",
            "startup_enabled": False,
            "privacy_mode": "balance",
            "ai_provider": "groq",
            "ai_model": "openai/gpt-oss-20b",
            "voice_mode": "balance",
            "command_style": "one_shot",
            "wake_word_enabled": True,
            "microphone_name": "Системный по умолчанию",
            "registration": {
                "groq_api_key": "",
                "telegram_user_id": "",
                "telegram_bot_token": "",
                "skipped": False,
            },
            "custom_apps": [],
        }

    def load(self):
        return self.payload.copy()

    def save(self, payload):
        self.payload = payload


def test_wake_service_detects_wake_word_in_partial_payload():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    payload = json.dumps({"partial": "джарвис открой steam"}, ensure_ascii=False)
    assert wake._contains_wake(payload, partial=True) is True  # noqa: SLF001


def test_wake_service_ignores_non_matching_payload():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    payload = json.dumps({"text": "просто разговор"}, ensure_ascii=False)
    assert wake._contains_wake(payload) is False  # noqa: SLF001

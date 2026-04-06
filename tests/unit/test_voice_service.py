from core.settings.settings_service import SettingsService
from core.voice.voice_service import VoiceService


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
        }

    def load(self):
        return self.payload.copy()

    def save(self, payload):
        self.payload = payload


def test_voice_runtime_without_key_reports_not_connected():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    status = voice.runtime_status()
    assert status["model"] == "не подключена"
    assert "нужен Groq API Key" in status["command"]

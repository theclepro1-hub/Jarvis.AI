from core.registration.registration_service import RegistrationService
from core.settings.settings_service import SettingsService


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


def test_registration_completes_when_all_fields_are_filled():
    settings = SettingsService(FakeStore())
    service = RegistrationService(settings)
    result = service.save("fake_groq_key", "123", "bot_token")
    assert result.is_complete is True
    assert service.is_complete(result) is True


def test_private_registration_can_complete_without_groq():
    settings = SettingsService(FakeStore())
    settings.set("assistant_mode", "private")
    service = RegistrationService(settings)

    result = service.save("", "123", "bot_token")

    assert result.is_complete is False
    assert service.requires_groq_for_completion() is False
    assert service.is_complete(result) is True


def test_registration_does_not_complete_with_only_non_groq_cloud_key() -> None:
    store = FakeStore()
    store.payload["registration"]["gemini_api_key"] = "gemini-key"
    settings = SettingsService(store)
    service = RegistrationService(settings)

    result = service.save("", "123", "bot_token")

    assert result.groq_api_key == ""
    assert result.gemini_api_key == "gemini-key"
    assert service.requires_groq_for_completion() is True
    assert service.is_complete(result) is False


def test_registration_can_be_skipped():
    settings = SettingsService(FakeStore())
    service = RegistrationService(settings)
    result = service.skip()
    assert result.skipped is True

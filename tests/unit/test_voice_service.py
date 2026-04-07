from __future__ import annotations

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
            "custom_apps": [],
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
    assert status["command"] == "Нужен ключ Groq"


def test_voice_service_normalizes_microphones_and_filters_driver_dump(monkeypatch):
    devices = [
        {"name": "Microphone (Logitech PRO X Gaming Headset)", "max_input_channels": 2},
        {"name": "Микрофон (Logitech PRO X Gaming Headset)", "max_input_channels": 2},
        {"name": "Input (@System32\\drivers\\bthhfenum.sys,#...)", "max_input_channels": 1},
        {"name": "Primary Driver - Microphone (G435 Wireless Gaming Headset)", "max_input_channels": 2},
        {"name": "Stereo Mix (Realtek HD Audio Stereo input)", "max_input_channels": 0},
        {"name": "Realtek HD Audio Mic input", "max_input_channels": 2},
    ]
    monkeypatch.setattr("core.voice.voice_service.sd.query_devices", lambda: devices)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    assert voice.microphones[0] == "Системный по умолчанию"
    assert "Input (@System32\\drivers\\bthhfenum.sys,#...)" not in voice.microphones
    assert len(voice.microphones) == len(set(voice.microphones))
    assert voice.normalize_microphone_selection("microphone (Logitech PRO X Gaming Headset)") == "Logitech PRO X Gaming Headset"
    assert voice.normalize_microphone_selection("Primary Driver - Microphone (G435 Wireless Gaming Headset)") == "G435 Wireless Gaming Headset"


def test_voice_service_strips_wake_word_from_transcription():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    assert voice._strip_wake_word("Джарвис открой YouTube") == "открой YouTube"  # noqa: SLF001
    assert voice._strip_wake_word("jarvis запусти музыку") == "запусти музыку"  # noqa: SLF001

from __future__ import annotations

from core.settings.settings_service import SettingsService
from core.voice.tts_service import TTSService
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
            "microphone_name": "Системный микрофон",
            "voice_output_name": "Системный вывод",
            "voice_response_enabled": False,
            "tts_engine": "system",
            "tts_voice_name": "Голос по умолчанию",
            "tts_rate": 185,
            "tts_volume": 85,
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
    assert status["tts"] == "голосовые ответы выключены"


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

    assert voice.microphones[0] == "Системный микрофон"
    assert "Input (@System32\\drivers\\bthhfenum.sys,#...)" not in voice.microphones
    assert "Primary Driver - Microphone (G435 Wireless Gaming Headset)" not in voice.microphones
    assert len(voice.microphones) == len(set(voice.microphones))
    assert voice.normalize_microphone_selection("microphone (Logitech PRO X Gaming Headset)") == "Logitech PRO X Gaming Headset"


def test_voice_service_strips_wake_word_from_transcription():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    assert voice._strip_wake_word("Джарвис открой YouTube") == "открой YouTube"  # noqa: SLF001
    assert voice._strip_wake_word("jarvis запусти музыку") == "запусти музыку"  # noqa: SLF001


def test_voice_service_normalizes_output_devices_and_filters_inputs(monkeypatch):
    devices = [
        {"name": "Speakers (Realtek HD Audio)", "max_output_channels": 2},
        {"name": "Headphones (G435 Wireless Gaming Headset)", "max_output_channels": 2},
        {"name": "Microphone (Logitech PRO X Gaming Headset)", "max_output_channels": 0},
        {"name": "Input (@System32\\drivers\\bthhfenum.sys,#...)", "max_output_channels": 2},
        {"name": "Primary Driver - Speakers (Realtek HD Audio)", "max_output_channels": 2},
    ]
    monkeypatch.setattr("core.voice.voice_service.sd.query_devices", lambda: devices)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    assert voice.output_devices[0] == "Системный вывод"
    assert "Input (@System32\\drivers\\bthhfenum.sys,#...)" not in voice.output_devices
    assert "Primary Driver - Speakers (Realtek HD Audio)" not in voice.output_devices
    assert "Realtek HD Audio" in voice.output_devices
    assert "G435" in voice.output_devices


def test_voice_service_reports_tts_output_device_limitation(monkeypatch):
    devices = [{"name": "Speakers (Realtek HD Audio)", "max_output_channels": 2}]
    monkeypatch.setattr("core.voice.voice_service.sd.query_devices", lambda: devices)
    monkeypatch.setattr(TTSService, "_module_available", lambda self, name: name == "pyttsx3")

    settings = SettingsService(FakeStore())
    settings.set("voice_output_name", "Realtek HD Audio")
    settings.set("voice_response_enabled", True)
    settings.set("tts_engine", "pyttsx3")
    voice = VoiceService(settings)

    result = voice.test_jarvis_voice()

    assert "голос пока говорит через системный вывод" in result


def test_voice_service_builds_structured_input_output_device_models(monkeypatch):
    devices = [
        {
            "name": "Microphone (Logitech PRO X Gami)",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 0,
        },
        {
            "name": "Microphone (Logitech PRO X Gaming Headset)",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 0,
        },
        {
            "name": "Stereo Mix (Realtek HD Audio Stereo input)",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 0,
        },
        {
            "name": "Line In (Realtek HD Audio Line input)",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 0,
        },
        {
            "name": "AF24H3 (NVIDIA High Definition Audio)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 0,
        },
        {
            "name": "SPDIF Out (Realtek HDA SPDIF Out)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 0,
        },
        {
            "name": "Headphones (G435 Wireless Gaming Headset)",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 0,
        },
        {
            "name": "Microphone (G435 Wireless Gaming Headset)",
            "max_input_channels": 2,
            "max_output_channels": 2,
            "hostapi": 0,
        },
    ]
    monkeypatch.setattr("core.voice.voice_service.sd.query_devices", lambda: devices)
    monkeypatch.setattr("core.voice.voice_service.sd.query_hostapis", lambda: [{"name": "Windows WASAPI"}])

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    input_names = [device.name for device in voice.microphone_device_models]
    output_names = [device.name for device in voice.output_device_models]

    assert voice.microphone_device_models[0].as_qml() == {
        "id": "system_default",
        "name": VoiceService.DEFAULT_INPUT_LABEL,
        "kind": "input",
        "hostapi": "system",
        "channels": 0,
        "isDefault": True,
        "isUsable": True,
    }
    assert "Logitech PRO X" in input_names
    assert "Logitech PRO X Gami" not in input_names
    assert all("Stereo" not in name and "Line" not in name and "NVIDIA" not in name for name in input_names)
    assert "G435" in output_names
    assert all("Microphone" not in name and "SPDIF" not in name and "NVIDIA" not in name for name in output_names)
    assert {device.kind for device in voice.microphone_device_models} == {"input"}
    assert {device.kind for device in voice.output_device_models} == {"output"}


def test_tts_engines_report_output_routing_capability_without_sapi(monkeypatch):
    monkeypatch.setattr(TTSService, "_module_available", lambda self, name: name == "pyttsx3")
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    engines = voice.available_tts_engines()

    assert [engine["key"] for engine in engines] == ["system"]
    assert all(engine["supportsOutputDevice"] is False for engine in engines)
    assert voice.can_route_tts_output() is False


def test_tts_engines_enable_output_routing_with_sapi(monkeypatch):
    monkeypatch.setattr(TTSService, "_module_available", lambda self, name: name == "win32com.client")
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    engines = voice.available_tts_engines()

    assert engines[0]["key"] == "system"
    assert engines[0]["supportsOutputDevice"] is True
    assert engines[0]["available"] is True
    assert voice.can_route_tts_output() is True


def test_wake_not_heard_status_is_status_only():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    voice.set_wake_runtime_status("not_heard", ready=False, detail="Не расслышал команду после слова активации")

    assert voice.runtime_status()["wakeWord"] == "Не расслышал команду после слова активации"

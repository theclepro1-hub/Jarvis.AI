from __future__ import annotations

import threading

from core.settings.settings_service import SettingsService
from core.voice.speech_capture_service import SpeechCaptureService
from core.voice.stt_service import STTService
from core.voice.tts_service import TTSService


class FakeStore:
    def __init__(self) -> None:
        self.payload = {
            "voice_response_enabled": True,
            "tts_engine": "system",
            "tts_voice_name": "Голос по умолчанию",
            "voice_output_name": "Системный вывод",
            "tts_rate": 185,
            "tts_volume": 85,
            "stt_engine": "auto",
            "network": {
                "proxy_mode": "system",
                "proxy_url": "",
                "no_proxy": "localhost,127.0.0.1,::1",
                "timeout_seconds": 20.0,
            },
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


def test_speech_capture_reports_mic_open_failed(monkeypatch):
    class BrokenStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise OSError("boom")

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", BrokenStream)

    service = SpeechCaptureService(lambda: None, threading.Event())
    result = service.capture_until_silence()

    assert result.status == "mic_open_failed"
    assert "Не удалось открыть микрофон" in result.detail


def test_stt_service_reports_missing_model_without_key(tmp_path):
    settings = SettingsService(FakeStore())
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.status == "model_missing"
    assert "Groq" in result.detail
    assert service.status_text() == "Нужен ключ Groq"
    assert service.can_transcribe() is False


def test_tts_service_reports_unavailable_without_dependencies(monkeypatch):
    monkeypatch.setattr("core.voice.tts_service.importlib.util.find_spec", lambda _name: None)

    settings = SettingsService(FakeStore())
    service = TTSService(settings)

    engines = service.available_engines()

    assert all(not engine.available for engine in engines)
    assert all(engine.supports_output_device is False for engine in engines)
    assert service.test_voice().status == "unavailable"
    assert "не установлен" in service.test_voice().message
    assert "pyttsx3" not in service.test_voice().message
    assert "Edge" not in service.test_voice().message


def test_tts_service_does_not_treat_system_output_as_custom_route(monkeypatch):
    monkeypatch.setattr("core.voice.tts_service.importlib.util.find_spec", lambda _name: None)

    settings = SettingsService(FakeStore())
    settings.set("voice_output_name", "Системный вывод")
    service = TTSService(settings)

    result = service.test_voice()

    assert result.status == "unavailable"
    assert "колонки" not in result.message.casefold()


def test_tts_service_does_not_treat_empty_output_as_custom_route(monkeypatch):
    monkeypatch.setattr("core.voice.tts_service.importlib.util.find_spec", lambda _name: None)

    settings = SettingsService(FakeStore())
    settings.set("voice_output_name", "")
    service = TTSService(settings)

    result = service.test_voice()

    assert result.status == "unavailable"
    assert "колонки" not in result.message.casefold()


def test_tts_engine_selection_hides_unready_online_voice(monkeypatch):
    monkeypatch.setattr("core.voice.tts_service.importlib.util.find_spec", lambda name: name == "win32com.client")

    settings = SettingsService(FakeStore())
    settings.set("tts_engine", "edge")
    service = TTSService(settings)

    assert service.tts_engine() == "system"
    assert [engine.key for engine in service.available_engines()] == ["system"]

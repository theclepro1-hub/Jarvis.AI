from __future__ import annotations

import threading

from core.settings.settings_service import SettingsService
from core.voice.speech_capture_service import SpeechCaptureService
from core.voice.stt_service import STTService
from core.voice.tts_service import TTSService
from core.voice.voice_models import TranscriptionResult


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
    service._faster_whisper_available = lambda: False  # noqa: SLF001

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.status == "model_missing"
    assert "backend" in result.detail.casefold() or "Groq" in result.detail
    assert service.status_text() == "Нужен ключ Groq или локальный backend распознавания"
    assert service.can_transcribe() is False


def test_stt_service_prefers_local_faster_whisper_engine_alias(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    assert service.engine() == "local_faster_whisper"


def test_stt_service_local_chain_falls_back_to_vosk(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    model_path = tmp_path / "vosk-model"
    model_path.mkdir(parents=True)
    service = STTService(settings, local_model_path=model_path)
    service._faster_whisper_available = lambda: True  # noqa: SLF001
    service._transcribe_with_local_faster_whisper = lambda _raw: TranscriptionResult(  # noqa: SLF001
        status="stt_failed",
        detail="fw failed",
        engine="local_faster_whisper",
        backend_trace=("local_faster_whisper",),
        latency_ms=120.0,
    )
    service._transcribe_with_local_vosk = lambda _raw: TranscriptionResult(  # noqa: SLF001
        status="ok",
        text="открой параметры",
        detail="ok",
        engine="local_vosk",
        backend_trace=("local_vosk",),
        latency_ms=35.0,
    )

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.ok is True
    assert result.text == "открой параметры"
    assert result.backend_trace == ("local_faster_whisper", "local_vosk")
    assert result.latency_ms == 155.0


def test_stt_service_normalizes_whitespace_and_repeated_punctuation(tmp_path):
    settings = SettingsService(FakeStore())
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    normalized = service._normalize_transcript_text("  открой   параметры  !!  ")  # noqa: SLF001

    assert normalized == "открой параметры!"


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

from __future__ import annotations

import sys
import threading
import time
import types

from core.settings.settings_service import SettingsService
from core.voice.faster_whisper_runtime import clear_faster_whisper_model_cache, load_faster_whisper_model
from core.voice.model_paths import MODEL_DIR_NAME
from core.voice.speech_capture_service import SpeechCaptureService
from core.voice.stt_service import STTService
from core.voice.tts_service import TTSService
from core.voice.voice_service import VoiceService
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
            "voice_mode": "balance",
        }

    def load(self):
        return self.payload.copy()

    def save(self, payload):
        self.payload = payload


def make_ready_vosk_model(model_path):
    model_path.mkdir(parents=True, exist_ok=True)
    for relative_path in ("am/final.mdl", "conf/model.conf", "graph/Gr.fst", "ivector/final.ie"):
        target = model_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test")


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
    assert service.status_text() == "Стандартный режим: нужен локальный backend или ключ Groq"
    assert service.can_transcribe() is False


def test_stt_service_maps_legacy_voice_modes_to_canonical_values(tmp_path):
    settings = SettingsService(FakeStore())
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    settings.set("voice_mode", "balance")
    assert service.assistant_mode() == "standard"

    settings.set("voice_mode", "quality")
    assert service.assistant_mode() == "smart"


def test_stt_service_prefers_explicit_assistant_mode_over_legacy_voice_mode(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("voice_mode", "balance")
    settings.set("assistant_mode", "private")
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    assert service.assistant_mode() == "private"


def test_stt_service_respects_backend_override_before_legacy_engine(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("assistant_mode", "standard")
    settings.set("stt_engine", "groq")
    settings.set("stt_backend_override", "local_vosk")
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    assert service.engine() == "local_vosk"


def test_stt_service_fast_mode_prefers_groq_before_local(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("voice_mode", "fast")
    settings.set("stt_engine", "auto")
    settings.set("registration", {**settings.get_registration(), "groq_api_key": "test-key"})
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    service._transcribe_with_local_vosk = lambda _raw, _cancel_event=None: (_ for _ in ()).throw(AssertionError("local Vosk should not run first"))  # noqa: SLF001
    service._transcribe_with_local_faster_whisper = lambda _raw, _cancel_event=None: (_ for _ in ()).throw(AssertionError("local Whisper should not run first"))  # noqa: SLF001
    service._transcribe_with_groq = lambda _raw, _cancel_event=None: TranscriptionResult(  # noqa: SLF001
        status="ok",
        text="открой steam",
        detail="ok",
        engine="groq_whisper",
        backend_trace=("groq_whisper",),
        latency_ms=42.0,
    )

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.ok is True
    assert result.engine == "groq_whisper"


def test_stt_service_private_mode_never_uses_groq_fallback(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("voice_mode", "private")
    settings.set("stt_engine", "auto")
    settings.set("registration", {**settings.get_registration(), "groq_api_key": "test-key"})
    service = STTService(settings, local_model_path=tmp_path / "missing-model")
    service._faster_whisper_available = lambda: False  # noqa: SLF001
    service._transcribe_with_groq = lambda _raw, _cancel_event=None: (_ for _ in ()).throw(AssertionError("private mode must not call Groq"))  # noqa: SLF001

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.status == "model_missing"
    assert "локаль" in result.detail.casefold()
    assert "fallback" in result.detail.casefold()
    assert "Groq" not in service.status_text()
    assert "облач" in service.status_text().casefold()


def test_stt_service_prefers_local_faster_whisper_engine_alias(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    assert service.engine() == "local_faster_whisper"


def test_stt_service_local_chain_falls_back_to_vosk(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    settings.set("stt_local_model", str(tmp_path / "fw-model"))
    model_path = tmp_path / "vosk-model"
    make_ready_vosk_model(model_path)
    (tmp_path / "fw-model").mkdir(parents=True)
    (tmp_path / "fw-model" / "model.bin").write_bytes(b"fw")
    service = STTService(settings, local_model_path=model_path)
    service._faster_whisper_available = lambda: True  # noqa: SLF001
    service._transcribe_with_local_faster_whisper = lambda _raw, _cancel_event=None: TranscriptionResult(  # noqa: SLF001
        status="stt_failed",
        detail="fw failed",
        engine="local_faster_whisper",
        backend_trace=("local_faster_whisper",),
        latency_ms=120.0,
    )
    service._transcribe_with_local_vosk = lambda _raw, _cancel_event=None: TranscriptionResult(  # noqa: SLF001
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


def test_stt_service_warmup_skips_remote_faster_whisper_and_uses_vosk(monkeypatch, tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    settings.set("stt_local_model", "small")
    model_path = tmp_path / "vosk-model"
    make_ready_vosk_model(model_path)
    service = STTService(settings, local_model_path=model_path)
    service.faster_whisper_download_root = tmp_path / "fw-cache"
    service._faster_whisper_available = lambda: True  # noqa: SLF001

    faster_whisper_calls = []
    vosk_calls = []

    monkeypatch.setattr(
        "core.voice.stt_service.load_faster_whisper_model",
        lambda *args, **kwargs: faster_whisper_calls.append((args, kwargs)),
    )
    monkeypatch.setattr("core.voice.stt_service.load_vosk_model", lambda path: vosk_calls.append(path))

    assert service.warm_up_local_backend() is True
    assert faster_whisper_calls == []
    assert vosk_calls == [model_path]


def test_stt_service_remote_faster_whisper_ref_does_not_block_local_vosk_path(monkeypatch, tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    settings.set("stt_local_model", "small")
    model_path = tmp_path / "vosk-model"
    make_ready_vosk_model(model_path)
    service = STTService(settings, local_model_path=model_path)
    service.faster_whisper_download_root = tmp_path / "fw-cache"
    service._faster_whisper_available = lambda: True  # noqa: SLF001

    monkeypatch.setattr(
        service,
        "_transcribe_with_local_faster_whisper",
        lambda _raw, _cancel_event=None: (_ for _ in ()).throw(AssertionError("faster-whisper should be skipped")),
    )
    service._transcribe_with_local_vosk = lambda _raw, _cancel_event=None: TranscriptionResult(  # noqa: SLF001
        status="ok",
        text="открой проводник",
        detail="ok",
        engine="local_vosk",
        backend_trace=("local_vosk",),
        latency_ms=28.0,
    )

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.ok is True
    assert result.text == "открой проводник"
    assert result.backend_trace == ("local_vosk",)


def test_stt_service_standard_mode_prefers_vosk_before_heavier_whisper(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "auto")
    settings.set("voice_mode", "standard")
    settings.set("stt_local_model", str(tmp_path / "fw-model"))
    model_path = tmp_path / "vosk-model"
    make_ready_vosk_model(model_path)
    (tmp_path / "fw-model").mkdir(parents=True)
    (tmp_path / "fw-model" / "model.bin").write_bytes(b"fw")
    service = STTService(settings, local_model_path=model_path)
    service._faster_whisper_available = lambda: True  # noqa: SLF001
    order: list[str] = []

    service._transcribe_with_local_vosk = lambda _raw, _cancel_event=None: order.append("local_vosk") or TranscriptionResult(  # noqa: SLF001
        status="ok",
        text="открой параметры",
        detail="ok",
        engine="local_vosk",
        backend_trace=("local_vosk",),
        latency_ms=20.0,
    )
    service._transcribe_with_local_faster_whisper = lambda _raw, _cancel_event=None: order.append("local_faster_whisper") or TranscriptionResult(  # noqa: SLF001
        status="ok",
        text="открой параметры",
        detail="ok",
        engine="local_faster_whisper",
        backend_trace=("local_faster_whisper",),
        latency_ms=60.0,
    )

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.ok is True
    assert order == ["local_vosk"]


def test_voice_service_private_mode_reports_local_only_model_missing():
    settings = SettingsService(FakeStore())
    settings.set("voice_mode", "private")
    service = VoiceService(settings)

    note = service._stt_note_from_result(  # noqa: SLF001
        TranscriptionResult(
            status="model_missing",
            detail="Приватный режим требует локальный backend распознавания. Облачный fallback отключён.",
            engine="local_faster_whisper",
        )
    )

    assert "локаль" in note.casefold()
    assert "Groq" not in note


def test_stt_service_private_mode_never_uses_cloud_transcription(monkeypatch, tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "auto")
    settings.set("voice_mode", "private")
    model_path = tmp_path / "vosk-model"
    make_ready_vosk_model(model_path)
    service = STTService(settings, local_model_path=model_path)
    service._local_faster_whisper_ready = lambda: False  # noqa: SLF001
    service._local_vosk_available = lambda: True  # noqa: SLF001

    monkeypatch.setattr(
        service,
        "_transcribe_with_groq",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cloud STT must not run in private mode")),
    )
    service._transcribe_with_local_vosk = lambda _raw, _cancel_event=None: TranscriptionResult(  # noqa: SLF001
        status="ok",
        text="открой настройки",
        detail="ok",
        engine="local_vosk",
        backend_trace=("local_vosk",),
        latency_ms=11.0,
    )

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.ok is True
    assert result.engine == "local_vosk"
    assert result.backend_trace == ("local_vosk",)


def test_faster_whisper_model_load_does_not_hold_global_lock_during_init(monkeypatch, tmp_path):
    clear_faster_whisper_model_cache()
    started = threading.Barrier(2)
    constructor_calls = []

    class FakeWhisperModel:
        def __init__(self, model_ref, **kwargs):  # noqa: ANN003
            constructor_calls.append((model_ref, kwargs))
            started.wait(timeout=1.0)
            time.sleep(0.15)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel))

    elapsed = {}

    def worker(name: str) -> None:
        begin = time.perf_counter()
        load_faster_whisper_model(name, tmp_path / "fw-cache")
        elapsed[name] = time.perf_counter() - begin

    first = threading.Thread(target=worker, args=("model-a",))
    second = threading.Thread(target=worker, args=("model-b",))

    suite_begin = time.perf_counter()
    first.start()
    second.start()
    first.join(timeout=2.0)
    second.join(timeout=2.0)
    suite_elapsed = time.perf_counter() - suite_begin

    assert first.is_alive() is False
    assert second.is_alive() is False
    assert len(constructor_calls) == 2
    assert suite_elapsed < 0.35
    assert max(elapsed.values()) < 0.35


def test_stt_service_cancels_before_entering_backend(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    model_path = tmp_path / "vosk-model"
    model_path.mkdir(parents=True)
    service = STTService(settings, local_model_path=model_path)
    cancelled = threading.Event()
    cancelled.set()

    result = service.transcribe_pcm_bytes(b"\x00" * 3200, cancel_event=cancelled)

    assert result.status == "cancelled"
    assert result.detail == "Запись остановлена."


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


def test_stt_service_prefers_repo_vosk_cache_before_appdata(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    cached_model = repo_root / "build" / "model_cache" / MODEL_DIR_NAME
    cached_model.mkdir(parents=True)
    for relative_path in ("am/final.mdl", "conf/model.conf", "graph/Gr.fst", "ivector/final.ie"):
        target = cached_model / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test")
    monkeypatch.setattr("core.voice.model_paths._repo_root", lambda: repo_root)
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    settings = SettingsService(FakeStore())
    service = STTService(settings)

    assert service.local_model_path == cached_model

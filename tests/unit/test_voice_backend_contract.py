from __future__ import annotations

import sys
import threading
import time
import types
from array import array
from pathlib import Path

from core.settings.settings_service import SettingsService
from core.voice.faster_whisper_runtime import (
    clear_faster_whisper_model_cache,
    find_existing_faster_whisper_model,
    load_faster_whisper_model,
    preseed_faster_whisper_model,
    resolve_local_faster_whisper_model,
)
from core.voice.speech_capture_service import CaptureConfig, SpeechCaptureService
from core.voice.stt_service import (
    COMMAND_HOTWORDS,
    COMMAND_PROMPT,
    LOCAL_FASTER_WHISPER_BEAM_SIZE,
    LOCAL_FASTER_WHISPER_BEST_OF,
    LOCAL_FASTER_WHISPER_VAD,
    STTService,
    WAKE_FASTER_WHISPER_BEAM_SIZE,
    WAKE_FASTER_WHISPER_BEST_OF,
    WAKE_FASTER_WHISPER_VAD,
    WAKE_HOTWORDS,
    WAKE_PROMPT,
)
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
            "stt_local_model": "small",
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


def make_ready_faster_whisper_model(model_path: Path) -> None:
    model_path.mkdir(parents=True, exist_ok=True)
    (model_path / "model.bin").write_bytes(b"fw")


def test_speech_capture_reports_mic_open_failed(monkeypatch):
    class BrokenStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise OSError("boom")

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", BrokenStream)

    service = SpeechCaptureService(lambda: None, threading.Event())
    result = service.capture_until_silence()

    assert result.status == "mic_open_failed"
    assert "Не удалось открыть микрофон" in result.detail


def test_speech_capture_uses_default_stream_latency(monkeypatch):
    captured: dict[str, object] = {}

    class FakeStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        def read(self, blocksize):  # noqa: ANN001
            return b"\x00" * (blocksize * 2), False

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", FakeStream)

    service = SpeechCaptureService(lambda: None, threading.Event())
    result = service.capture_until_silence()

    assert result.status == "no_speech"
    assert "latency" not in captured


def test_speech_capture_ignores_single_noise_spike_before_speech(monkeypatch):
    frames = 1600

    def pcm_block(amplitude: int) -> bytes:
        return array("h", [amplitude] * frames).tobytes()

    blocks = iter((pcm_block(205), pcm_block(0), pcm_block(0), pcm_block(0)))

    class FakeStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        def read(self, blocksize):  # noqa: ANN001
            return next(blocks, pcm_block(0)), False

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", FakeStream)

    service = SpeechCaptureService(
        lambda: None,
        threading.Event(),
        config=CaptureConfig(max_seconds=0.4, silence_seconds=0.2, energy_threshold=160.0),
    )
    result = service.capture_until_silence()

    assert result.status == "no_speech"


def test_speech_capture_treats_wake_pre_roll_as_active_speech(monkeypatch):
    frames = 1600

    def pcm_block(amplitude: int) -> bytes:
        return array("h", [amplitude] * frames).tobytes()

    blocks = iter((pcm_block(0), pcm_block(0), pcm_block(0)))

    class FakeStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        def read(self, blocksize):  # noqa: ANN001
            return next(blocks, pcm_block(0)), False

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", FakeStream)

    service = SpeechCaptureService(
        lambda: None,
        threading.Event(),
        config=CaptureConfig(max_seconds=0.3, silence_seconds=0.1, energy_threshold=160.0, pre_roll_grace_seconds=0.1),
    )
    result = service.capture_until_silence(pre_roll=pcm_block(180))

    assert result.status == "ok"
    assert result.speech_started is True


def test_speech_capture_does_not_treat_silent_pre_roll_as_speech(monkeypatch):
    frames = 1600

    def pcm_block(amplitude: int) -> bytes:
        return array("h", [amplitude] * frames).tobytes()

    blocks = iter((pcm_block(0), pcm_block(0), pcm_block(0), pcm_block(0)))

    class FakeStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        def read(self, blocksize):  # noqa: ANN001
            return next(blocks, pcm_block(0)), False

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", FakeStream)

    service = SpeechCaptureService(
        lambda: None,
        threading.Event(),
        config=CaptureConfig(max_seconds=0.3, silence_seconds=0.1, energy_threshold=160.0, pre_roll_grace_seconds=0.1),
    )
    result = service.capture_until_silence(pre_roll=pcm_block(0))

    assert result.status == "no_speech"


def test_speech_capture_adapts_to_steady_noise_before_real_speech(monkeypatch):
    frames = 1600

    def pcm_block(amplitude: int) -> bytes:
        return array("h", [amplitude] * frames).tobytes()

    blocks = iter(
        (
            pcm_block(182),
            pcm_block(188),
            pcm_block(190),
            pcm_block(242),
            pcm_block(246),
            pcm_block(0),
            pcm_block(0),
            pcm_block(0),
        )
    )

    class FakeStream:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        def read(self, blocksize):  # noqa: ANN001
            return next(blocks, pcm_block(0)), False

    monkeypatch.setattr("core.voice.speech_capture_service.sd.RawInputStream", FakeStream)

    service = SpeechCaptureService(
        lambda: None,
        threading.Event(),
        config=CaptureConfig(max_seconds=0.8, silence_seconds=0.2, energy_threshold=160.0, noise_floor_frames=3),
    )
    result = service.capture_until_silence()

    assert result.status == "ok"
    assert result.speech_started is True


def test_speech_capture_default_gate_stays_less_aggressive() -> None:
    config = CaptureConfig()

    assert config.energy_threshold <= 128.0
    assert config.noise_margin <= 18.0
    assert config.speech_gate_ratio <= 1.08
    assert config.end_threshold_ratio <= 0.68


def test_stt_service_reports_missing_model_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = SettingsService(FakeStore())
    service = STTService(settings, local_model_path=tmp_path / "missing-model")
    service._faster_whisper_available = lambda: False  # noqa: SLF001

    result = service.transcribe_pcm_bytes(b"\x00" * 3200)

    assert result.status == "model_missing"
    assert "backend" in result.detail.casefold() or "облач" in result.detail.casefold() or "локальн" in result.detail.casefold()
    assert service.status_text() == "Нужен ключ для облачного распознавания или локальный backend распознавания речи"
    assert service.can_transcribe() is False


def test_stt_service_prefers_local_faster_whisper_engine_alias(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    service = STTService(settings, local_model_path=tmp_path / "missing-model")

    assert service.engine() == "local_faster_whisper"


def test_stt_service_warmup_uses_downloadable_faster_whisper_ref(monkeypatch, tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    settings.set("stt_local_model", "small")
    service = STTService(settings)
    service.faster_whisper_download_root = tmp_path / "fw-cache"
    service._faster_whisper_available = lambda: True  # noqa: SLF001

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(
        "core.voice.stt_service.load_faster_whisper_model",
        lambda *args, **kwargs: calls.append((args, kwargs)) or object(),
    )

    assert service.warm_up_local_backend() is True
    assert calls[0][0][0] == "small"


def test_stt_service_standard_route_prefers_local_faster_whisper(tmp_path):
    settings = SettingsService(FakeStore())
    model_path = tmp_path / "fw-model"
    make_ready_faster_whisper_model(model_path)
    settings.set("stt_local_model", str(model_path))
    service = STTService(settings)

    assert service._resolved_stt_route() == ("local_faster_whisper", "groq_whisper")  # noqa: SLF001


def test_stt_service_accepts_env_backed_groq_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "env-groq")
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "groq_whisper")
    service = STTService(settings, local_model_path=tmp_path / "missing-model")
    service._faster_whisper_available = lambda: False  # noqa: SLF001

    assert service.status_text() == "Облачное распознавание готово"
    assert service.can_transcribe() is True


def test_stt_service_prefers_env_override_for_local_model(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_UNITY_FASTER_WHISPER_MODEL", "medium")
    settings = SettingsService(FakeStore())
    service = STTService(settings)

    assert service._faster_whisper_model_ref() == "medium"  # noqa: SLF001


def test_stt_service_local_faster_whisper_uses_ru_prompt_and_vad_tuning(monkeypatch, tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    model_path = tmp_path / "fw-model"
    make_ready_faster_whisper_model(model_path)
    settings.set("stt_local_model", str(model_path))
    service = STTService(settings)
    service._faster_whisper_available = lambda: True  # noqa: SLF001

    captured: dict[str, object] = {}

    class FakeModel:
        def transcribe(self, _path, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            return [types.SimpleNamespace(text="открой "), types.SimpleNamespace(text="ютуб")], types.SimpleNamespace()

    monkeypatch.setattr("core.voice.stt_service.load_faster_whisper_model", lambda *args, **kwargs: FakeModel())

    result = service._transcribe_with_local_faster_whisper(b"\x00" * 3200)  # noqa: SLF001

    assert result.ok is True
    assert result.text == "открой ютуб"
    assert captured["language"] == "ru"
    assert captured["beam_size"] == LOCAL_FASTER_WHISPER_BEAM_SIZE
    assert captured["best_of"] == LOCAL_FASTER_WHISPER_BEST_OF
    assert captured["temperature"] == 0.0
    assert captured["vad_filter"] is True
    assert captured["vad_parameters"] == LOCAL_FASTER_WHISPER_VAD
    assert captured["condition_on_previous_text"] is False
    assert captured["initial_prompt"] == COMMAND_PROMPT
    assert captured["hotwords"] == COMMAND_HOTWORDS


def test_stt_service_wake_window_uses_wake_prompt_and_hotwords(monkeypatch, tmp_path):
    settings = SettingsService(FakeStore())
    model_path = tmp_path / "fw-model"
    make_ready_faster_whisper_model(model_path)
    settings.set("stt_local_model", str(model_path))
    service = STTService(settings)
    service._faster_whisper_available = lambda: True  # noqa: SLF001

    captured: dict[str, object] = {}

    class FakeModel:
        def transcribe(self, _path, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            return [types.SimpleNamespace(text="джарвис открой ютуб")], types.SimpleNamespace()

    monkeypatch.setattr("core.voice.stt_service.load_faster_whisper_model", lambda *args, **kwargs: FakeModel())

    result = service.transcribe_wake_window(b"\x00" * 3200)

    assert result.ok is True
    assert captured["initial_prompt"] == WAKE_PROMPT
    assert captured["hotwords"] == WAKE_HOTWORDS
    assert captured["beam_size"] == WAKE_FASTER_WHISPER_BEAM_SIZE
    assert captured["best_of"] == WAKE_FASTER_WHISPER_BEST_OF
    assert captured["vad_parameters"] == WAKE_FASTER_WHISPER_VAD
    assert captured["chunk_length"] == 3


def test_stt_service_explicit_local_faster_whisper_override_wins_route_selection(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_backend_override", "local_faster_whisper")
    service = STTService(settings, local_model_path=tmp_path / "fw-model")

    assert service._resolved_stt_route() == ("local_faster_whisper",)  # noqa: SLF001


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


def test_find_existing_faster_whisper_model_uses_local_appdata_cache(monkeypatch, tmp_path):
    localappdata = tmp_path / "localappdata"
    source_root = localappdata / "JarvisAi_Unity" / "models" / "faster-whisper"
    model_path = source_root / "small"
    make_ready_faster_whisper_model(model_path)
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    resolved = find_existing_faster_whisper_model("small")

    assert resolved == model_path


def test_preseed_faster_whisper_model_copies_existing_hf_snapshot(monkeypatch, tmp_path):
    hf_cache = tmp_path / "hf-cache"
    snapshot = hf_cache / "models--Systran--faster-whisper-small" / "snapshots" / "abc123"
    make_ready_faster_whisper_model(snapshot)
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HF_HUB_CACHE", str(hf_cache))

    target_root = tmp_path / "bundle-cache"
    preseeded = preseed_faster_whisper_model("small", target_root)
    resolved = resolve_local_faster_whisper_model("small", target_root)

    assert preseeded == resolved
    assert resolved is not None
    assert (resolved / "model.bin").exists()
    assert (target_root / "models--Systran--faster-whisper-small" / "refs" / "main").read_text(encoding="utf-8").strip() == "preseed"


def test_preseed_faster_whisper_model_prefers_explicit_seed_root(monkeypatch, tmp_path):
    source_root = tmp_path / "seed-root"
    snapshot = source_root / "models--Systran--faster-whisper-small" / "snapshots" / "seeded"
    make_ready_faster_whisper_model(snapshot)
    refs_dir = source_root / "models--Systran--faster-whisper-small" / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text("seeded", encoding="utf-8")
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.setenv("JARVIS_UNITY_FASTER_WHISPER_SEED_DIR", str(source_root))

    target_root = tmp_path / "bundle-cache"
    preseeded = preseed_faster_whisper_model("small", target_root)

    assert preseeded is not None
    assert resolve_local_faster_whisper_model("small", target_root) == preseeded
    assert preseeded.name == "preseed"


def test_stt_service_cancels_before_entering_backend(tmp_path):
    settings = SettingsService(FakeStore())
    settings.set("stt_engine", "local")
    model_path = tmp_path / "fw-model"
    make_ready_faster_whisper_model(model_path)
    settings.set("stt_local_model", str(model_path))
    service = STTService(settings)
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

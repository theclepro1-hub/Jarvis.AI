from __future__ import annotations

from pathlib import Path

from core.settings.settings_service import SettingsService
from core.voice.voice_service import VoiceService
from core.voice.voice_models import TranscriptionResult
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
            "microphone_name": "Системный микрофон",
            "voice_output_name": "Системный вывод",
            "voice_response_enabled": False,
            "tts_engine": "system",
            "tts_voice_name": "Голос по умолчанию",
            "tts_rate": 185,
            "tts_volume": 85,
            "stt_local_model": "small",
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


def make_ready_faster_whisper_model(model_path: Path) -> None:
    model_path.mkdir(parents=True, exist_ok=True)
    (model_path / "model.bin").write_bytes(b"fw")


def test_wake_service_detects_wake_word_in_payloads() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake._contains_wake('{"partial": "джарвис открой steam"}', partial=True) is True  # noqa: SLF001
    assert wake._contains_wake('{"text": "жаравис открой steam"}') is True  # noqa: SLF001
    assert wake._contains_wake("гарри открой steam") is True  # noqa: SLF001
    assert wake._contains_wake("гаривис открой steam") is True  # noqa: SLF001


def test_wake_service_ignores_non_matching_noise() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake._contains_wake('{"partial": "герой открой steam"}', partial=True) is False  # noqa: SLF001
    assert wake._contains_wake("просто разговор") is False  # noqa: SLF001


def test_wake_service_reports_missing_backend_without_source(monkeypatch) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    monkeypatch.setattr(wake, "_wake_model_source", lambda: None)

    result = wake.start(lambda _pre_roll: None)

    assert wake.phase == "error"
    assert "wake backend" in result
    assert "wake backend" in wake.status()


def test_wake_service_reports_downloadable_or_loaded_model_status(monkeypatch, tmp_path) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    ready_path = tmp_path / "fw-model"
    make_ready_faster_whisper_model(ready_path)

    monkeypatch.setattr(wake, "_wake_model_source", lambda: "small")
    assert wake.model_status() == "готова к загрузке"

    monkeypatch.setattr(wake, "_wake_model_source", lambda: ready_path)
    assert wake.model_status() == "загружена"


def test_wake_service_uses_local_appdata_for_user_model_path(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake.user_model_path == tmp_path / "JarvisAi_Unity" / "models" / "faster-whisper"


def test_wake_service_warm_up_delegates_to_local_backend(monkeypatch) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    calls: list[bool] = []

    monkeypatch.setattr(voice.stt_service, "warm_up_local_backend", lambda cancel_event=None: calls.append(True) or True)

    assert wake.warm_up_model() is True
    assert calls == [True]


def test_wake_service_candidate_burst_hands_audio_to_callback(monkeypatch) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    captured: list[bytes] = []

    monkeypatch.setattr(
        voice.stt_service,
        "transcribe_wake_window",
        lambda raw_bytes, cancel_event=None: TranscriptionResult(  # noqa: ARG005
            status="ok",
            text="джарвис открой steam",
            detail="ok",
            engine="local_faster_whisper",
        ),
    )
    wake._callback = captured.append  # noqa: SLF001

    detected = wake._handle_candidate_burst(b"pcm")  # noqa: SLF001

    assert detected is True
    assert captured == [b"pcm"]
    assert wake.phase == "capturing_command"


def test_wake_service_candidate_burst_returns_to_waiting_on_non_wake(monkeypatch) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    monkeypatch.setattr(
        voice.stt_service,
        "transcribe_wake_window",
        lambda raw_bytes, cancel_event=None: TranscriptionResult(  # noqa: ARG005
            status="ok",
            text="просто разговор",
            detail="ok",
            engine="local_faster_whisper",
        ),
    )

    detected = wake._handle_candidate_burst(b"pcm")  # noqa: SLF001

    assert detected is False
    assert wake.phase == "waiting_wake"
    assert wake.status() == "Жду «Джарвис»"


def test_wake_service_reports_transcribing_status_truthfully() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    wake._set_phase("transcribing", "Распознаю команду", ready=False)  # noqa: SLF001

    assert wake.phase == "transcribing"
    assert wake.status() == "Распознаю команду"
    assert voice.runtime_status()["wakeWord"] == "Распознаю команду"


def test_wake_service_marks_capture_phase_as_handoff() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    wake._phase = "capturing_command"  # noqa: SLF001
    assert wake._phase_in_handoff() is True  # noqa: SLF001

    wake._phase = "idle"  # noqa: SLF001
    assert wake._phase_in_handoff() is False  # noqa: SLF001

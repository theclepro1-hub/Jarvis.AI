from __future__ import annotations

from core.settings.settings_service import SettingsService
from core.voice.voice_models import WakeSessionMetrics
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


def test_wake_service_warm_up_model_loads_openwakeword_runtime() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    class Runtime:
        def __init__(self) -> None:
            self.calls = 0

        def load(self) -> bool:
            self.calls += 1
            return True

    runtime = Runtime()
    wake._runtime = runtime  # noqa: SLF001

    assert wake.warm_up_model() is True
    assert runtime.calls == 1


def test_voice_service_warms_up_local_stt_backend(monkeypatch) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    calls: list[tuple[object | None, bool]] = []

    monkeypatch.setattr(
        voice.stt_service,
        "warm_up_local_backend",
        lambda cancel_event=None, allow_download=True: calls.append((cancel_event, allow_download)) or True,
    )

    assert voice.warm_up_local_stt_backend() is True
    assert calls == [(voice._manual_stop_event, True)]  # noqa: SLF001


def test_voice_service_reports_wake_timings_in_sequence() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    voice._wake_metrics = WakeSessionMetrics(  # noqa: SLF001
        session_id="abc123",
        wake_backend="openwakeword",
        stt_backend="local_faster_whisper",
        pre_roll_bytes=3200,
        detected_at=1.0,
        capture_started_at=1.05,
        capture_finished_at=1.95,
        stt_started_at=2.0,
        stt_finished_at=2.25,
        route_handoff_at=2.3,
        final_status="handoff",
    )

    summary = voice.latest_wake_metrics_summary()

    assert summary.index("pre-roll") < summary.index("wake→capture") < summary.index("capture") < summary.index("stt") < summary.index("handoff") < summary.index("total")
    assert "backend wake openwakeword · stt local_faster_whisper" in summary


def test_wake_service_stop_cancels_active_voice_pipeline() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    calls: list[str] = []

    voice.cancel_active_pipeline = lambda: calls.append("cancelled")  # type: ignore[method-assign]

    wake.stop()

    assert calls == ["cancelled"]


def test_wake_service_scores_named_model_prediction() -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake._prediction_score({"hey_jarvis_v0.1": 0.7, "alexa": 0.9}) == 0.7  # noqa: SLF001

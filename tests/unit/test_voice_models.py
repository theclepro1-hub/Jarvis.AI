from __future__ import annotations

from core.voice.voice_models import SpeechCaptureResult, TranscriptionResult, WakeSessionMetrics


def test_wake_session_metrics_report_handoff_and_timings() -> None:
    metrics = WakeSessionMetrics(
        session_id="abc123",
        phase="routing",
        detail="handoff",
        wake_backend="vosk",
        stt_backend="groq_whisper",
        backend_trace=("vosk", "groq_whisper"),
        detected_at=10.0,
        capture_started_at=10.05,
        capture_finished_at=10.55,
        stt_started_at=10.60,
        stt_finished_at=11.00,
        route_handoff_at=11.20,
        pre_roll_bytes=32000,
        captured_audio_bytes=64000,
        captured_audio_seconds=2.0,
        transcript="open youtube",
        final_status="handoff",
        failure_detail="",
    )

    payload = metrics.as_dict()

    assert payload["sessionId"] == "abc123"
    assert payload["wakeBackend"] == "vosk"
    assert payload["sttBackend"] == "groq_whisper"
    assert payload["backendTrace"] == "vosk -> groq_whisper"
    assert payload["wakeToCaptureMs"] == 50.0
    assert payload["captureMs"] == 500.0
    assert payload["sttMs"] == 400.0
    assert payload["sttToRouteMs"] == 200.0
    assert payload["totalMs"] == 1200.0
    assert payload["preRollMs"] == 1000.0
    assert payload["capturedAudioMs"] == 2000.0
    assert payload["transcript"] == "open youtube"
    assert payload["finalStatus"] == "handoff"
    assert payload["routeHookSeen"] is True


def test_capture_and_transcription_results_keep_boolean_contract() -> None:
    capture = SpeechCaptureResult(status="ok", raw_audio=b"1234", speech_started=True, duration_seconds=0.25)
    failed_capture = SpeechCaptureResult(status="cancelled")
    transcription = TranscriptionResult(status="ok", text="open youtube", engine="local_vosk", latency_ms=42.0)

    assert capture.ok is True
    assert failed_capture.ok is False
    assert transcription.ok is True

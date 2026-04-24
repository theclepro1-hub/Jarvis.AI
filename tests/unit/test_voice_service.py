from __future__ import annotations

import threading
import time

from core.settings.settings_service import SettingsService
from core.voice.tts_service import TTSService
from core.voice.voice_models import SpeechCaptureResult, TTSResult, TranscriptionResult
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


def _capture_after_wake_text(monkeypatch, text: str) -> TranscriptionResult:
    class FakeCaptureService:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def capture_until_silence(self, pre_roll=b""):  # noqa: ARG002
            return SpeechCaptureResult(status="ok", raw_audio=b"pcm", speech_started=True, duration_seconds=0.8)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    monkeypatch.setattr("core.voice.voice_service.SpeechCaptureService", FakeCaptureService)
    monkeypatch.setattr(
        voice.stt_service,
        "transcribe_pcm_bytes",
        lambda _raw, cancel_event=None: TranscriptionResult(status="ok", text=text, detail="ok", engine="stub"),
    )
    return voice.capture_after_wake_result(b"")


def test_voice_runtime_without_key_reports_not_connected():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    voice.stt_service._faster_whisper_available = lambda: False  # noqa: SLF001
    voice.stt_service._local_vosk_available = lambda: False  # noqa: SLF001

    status = voice.runtime_status()

    assert status["model"] == "не подключена"
    assert status["command"] == "Нужен ключ Groq или локальный backend распознавания"
    assert status["tts"] == "голосовые ответы выключены"


def test_voice_runtime_auto_mode_reports_local_backend_without_groq():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    voice.stt_service._local_faster_whisper_ready = lambda: True  # noqa: SLF001

    status = voice.runtime_status()

    assert status["model"] == "загружена"
    assert status["command"] == "локальное распознавание готово"


def test_voice_service_defers_audio_device_scan_until_needed(monkeypatch):
    calls = {"devices": 0, "hostapis": 0}

    def fake_query_devices():
        calls["devices"] += 1
        return [{"name": "Microphone (Logitech PRO X Gaming Headset)", "max_input_channels": 2}]

    def fake_query_hostapis():
        calls["hostapis"] += 1
        return [{"name": "Windows WASAPI"}]

    monkeypatch.setattr("core.voice.voice_service.sd.query_devices", fake_query_devices)
    monkeypatch.setattr("core.voice.voice_service.sd.query_hostapis", fake_query_hostapis)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    assert calls == {"devices": 0, "hostapis": 0}
    assert voice.microphones[0] == "Системный микрофон"
    assert calls["devices"] == 2
    assert calls["hostapis"] == 2


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

    assert voice._strip_wake_word("гаррис открой YouTube").casefold() == "открой YouTube".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("нарве открой YouTube").casefold() == "открой YouTube".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("нарве с открой YouTube").casefold() == "открой YouTube".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("Джарвис открой YouTube").casefold() == "открой YouTube".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("jarvis запусти музыку").casefold() == "запусти музыку".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("гарви с как дела").casefold() == "как дела?".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("да любишь как дела у тебя").casefold() == "как дела у тебя?".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("жарвис, как дела?").casefold() == "как дела?".casefold()  # noqa: SLF001
    assert voice._strip_wake_word("как у джарвиса дела") == "как у джарвиса дела"  # noqa: SLF001
    assert voice._strip_wake_word("джарвис") == ""  # noqa: SLF001


def test_voice_service_normalizes_text_consistently_for_manual_and_wake():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    assert voice._normalize_command_text("как дела у тебя") == "Как дела у тебя?"  # noqa: SLF001
    assert voice._normalize_command_text("привет") == "Привет"  # noqa: SLF001
    assert voice._normalize_command_text("открой ютуб") == "Открой ютуб"  # noqa: SLF001
    assert voice._normalize_command_text("да открой ютуб", strip_connectors=True) == "Открой ютуб"  # noqa: SLF001


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


def test_tts_custom_output_does_not_fallback_to_system_default(monkeypatch):
    settings = SettingsService(FakeStore())
    settings.set("voice_output_name", "Logitech PRO X")
    settings.set("voice_response_enabled", True)
    tts = TTSService(settings)

    monkeypatch.setattr(tts, "_module_available", lambda name: name in {"win32com.client", "pyttsx3"})
    monkeypatch.setattr(
        tts,
        "_speak_with_sapi",
        lambda _text: TTSResult(
            status="failed",
            message="SAPI failed",
            engine="system",
            available=False,
            supports_output_device=True,
        ),
    )

    result = tts.speak("Проверка")

    assert result.status == "failed"
    assert result.message == "SAPI failed"


def test_voice_service_interrupt_tts_stops_engine_and_clears_speaking_state(monkeypatch):
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    calls: list[str] = []

    def fake_stop() -> bool:
        calls.append("stop")
        return True

    monkeypatch.setattr(voice.tts_service, "stop", fake_stop)
    voice._speaking_count = 1  # noqa: SLF001
    voice._speaking_cooldown_until = time.monotonic() + 10.0  # noqa: SLF001

    assert voice.interrupt_tts() is True

    assert calls == ["stop"]
    assert voice.is_speaking is False


def test_voice_service_interrupt_tts_is_idempotent(monkeypatch):
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    monkeypatch.setattr(voice.tts_service, "stop", lambda: False)

    assert voice.interrupt_tts() is False
    assert voice.is_speaking is False


def test_wake_not_heard_status_is_status_only():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    voice.set_wake_runtime_status("not_heard", ready=False, detail="Не расслышал команду после слова активации")

    assert voice.runtime_status()["wakeWord"] == "Не расслышал команду после слова активации"


def test_wake_capture_status_uses_recording_wording():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    voice.set_wake_runtime_status("capturing_command", ready=False, detail="Подхватываю начало команды")

    assert voice.wake_status_text() == "Подхватываю начало команды"


def test_capture_after_wake_treats_filler_as_not_heard(monkeypatch):
    class FakeCaptureService:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def capture_until_silence(self, pre_roll=b""):  # noqa: ARG002
            return SpeechCaptureResult(status="ok", raw_audio=b"pcm", speech_started=True, duration_seconds=0.8)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    monkeypatch.setattr("core.voice.voice_service.SpeechCaptureService", FakeCaptureService)
    monkeypatch.setattr(
        voice.stt_service,
        "transcribe_pcm_bytes",
        lambda _raw, cancel_event=None: TranscriptionResult(status="ok", text="джарвис эээ", detail="ok", engine="stub"),
    )

    result = voice.capture_after_wake_result(b"")

    assert result.status == "no_speech"
    assert result.detail == "Не расслышал команду"
    assert voice.runtime_status()["wakeWord"] == "Не расслышал команду"


def test_capture_after_wake_keeps_short_real_command(monkeypatch):
    class FakeCaptureService:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def capture_until_silence(self, pre_roll=b""):  # noqa: ARG002
            return SpeechCaptureResult(status="ok", raw_audio=b"pcm", speech_started=True, duration_seconds=0.8)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    monkeypatch.setattr("core.voice.voice_service.SpeechCaptureService", FakeCaptureService)
    monkeypatch.setattr(
        voice.stt_service,
        "transcribe_pcm_bytes",
        lambda _raw, cancel_event=None: TranscriptionResult(status="ok", text="джарвис ютуб", detail="ok", engine="stub"),
    )

    result = voice.capture_after_wake_result(b"")

    assert result.ok is True
    assert result.text.casefold() == "ютуб".casefold()


def test_capture_after_wake_rejects_long_background_speech_without_wake_prefix(monkeypatch):
    class FakeCaptureService:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def capture_until_silence(self, pre_roll=b""):  # noqa: ARG002
            return SpeechCaptureResult(status="ok", raw_audio=b"pcm", speech_started=True, duration_seconds=1.2)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    monkeypatch.setattr("core.voice.voice_service.SpeechCaptureService", FakeCaptureService)
    monkeypatch.setattr(
        voice.stt_service,
        "transcribe_pcm_bytes",
        lambda _raw, cancel_event=None: TranscriptionResult(
            status="ok",
            text="у меня не будет рака я не думаю об этом",
            detail="ok",
            engine="stub",
        ),
    )

    result = voice.capture_after_wake_result(b"")

    assert result.status == "no_speech"
    assert result.detail == "Не расслышал команду"


def test_capture_after_wake_rejects_non_question_noise_with_wake_prefix(monkeypatch):
    result = _capture_after_wake_text(monkeypatch, "джарвис ла ла ла ла")

    assert result.status == "no_speech"
    assert result.detail == "Не расслышал команду"


def test_capture_after_wake_accepts_how_are_you_question_with_wake_prefix(monkeypatch):
    result = _capture_after_wake_text(monkeypatch, "джарвис как дела")

    assert result.ok is True
    assert result.text.casefold() == "Как дела?".casefold()


def test_capture_after_wake_accepts_what_is_youtube_question_with_wake_prefix(monkeypatch):
    result = _capture_after_wake_text(monkeypatch, "джарвис что такое ютуб")

    assert result.ok is True
    assert result.text.casefold() == "Что такое ютуб?".casefold()


def test_capture_after_wake_rejects_non_command_non_question_phrase_even_with_wake_prefix(monkeypatch):
    result = _capture_after_wake_text(monkeypatch, "джарвис от грусти")

    assert result.status == "no_speech"
    assert result.detail == "Не расслышал команду"


def test_manual_capture_stop_cancels_pending_transcription():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    started = threading.Event()
    notes: list[str] = []
    texts: list[str] = []
    finished = threading.Event()

    voice.capture_service.capture_until_silence = lambda: SpeechCaptureResult(  # type: ignore[method-assign]
        status="ok",
        raw_audio=b"pcm",
        speech_started=True,
        duration_seconds=0.4,
    )

    def fake_transcribe(_raw: bytes, cancel_event=None):  # noqa: ANN001
        started.set()
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(0.01)
        return TranscriptionResult(status="cancelled", detail="Запись остановлена.")

    voice.stt_service.transcribe_pcm_bytes = fake_transcribe  # type: ignore[method-assign]

    voice.start_manual_capture(on_text=texts.append, on_note=notes.append, on_finish=finished.set)
    assert started.wait(1.0)

    assert voice.stop_manual_capture() == "Останавливаю запись..."
    assert finished.wait(1.0)

    assert texts == []
    assert notes == ["Запись остановлена."]
    assert voice.is_recording is False


def test_capture_after_wake_can_be_cancelled_during_transcription(monkeypatch):
    class FakeCaptureService:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def capture_until_silence(self, pre_roll=b""):  # noqa: ARG002
            return SpeechCaptureResult(status="ok", raw_audio=b"pcm", speech_started=True, duration_seconds=0.8)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    started = threading.Event()
    result_box: dict[str, TranscriptionResult] = {}

    monkeypatch.setattr("core.voice.voice_service.SpeechCaptureService", FakeCaptureService)

    def fake_transcribe(_raw: bytes, cancel_event=None):  # noqa: ANN001
        started.set()
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(0.01)
        return TranscriptionResult(status="cancelled", detail="Запись остановлена.", engine="local_vosk")

    voice.stt_service.transcribe_pcm_bytes = fake_transcribe  # type: ignore[method-assign]

    worker = threading.Thread(
        target=lambda: result_box.setdefault("result", voice.capture_after_wake_result(b"wake")),
        daemon=True,
    )
    worker.start()
    assert started.wait(1.0)

    voice.cancel_active_pipeline()
    worker.join(timeout=1.0)

    result = result_box["result"]
    assert worker.is_alive() is False
    assert result.status == "cancelled"
    assert voice.runtime_status()["wakeWord"] == "Запись остановлена."


def test_transcribe_with_cancel_times_out_when_backend_hangs():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    started = threading.Event()
    release = threading.Event()

    def fake_transcribe(_raw: bytes, cancel_event=None):  # noqa: ANN001
        started.set()
        release.wait(1.0)
        return TranscriptionResult(status="ok", text="done", detail="ok", engine="stub")

    voice.stt_service.transcribe_pcm_bytes = fake_transcribe  # type: ignore[method-assign]
    voice.STT_JOB_TIMEOUT_SECONDS = 0.05

    pipeline_id = voice._begin_pipeline()  # noqa: SLF001
    result = voice._transcribe_with_cancel(b"pcm", pipeline_id)  # noqa: SLF001

    assert started.wait(1.0)
    assert result.status == "stt_timeout"
    release.set()


def test_transcribe_timeout_result_is_not_downgraded_to_cancelled():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    def timeout_then_cancel(_raw: bytes, cancel_event=None):  # noqa: ANN001
        voice.cancel_active_pipeline()
        return TranscriptionResult(status="stt_timeout", detail="STT backend timeout.")

    voice.stt_service.transcribe_pcm_bytes = timeout_then_cancel  # type: ignore[method-assign]

    pipeline_id = voice._begin_pipeline()  # noqa: SLF001
    result = voice._transcribe_with_cancel(b"pcm", pipeline_id)  # noqa: SLF001

    assert result.status == "stt_timeout"


def test_stop_stt_worker_stops_idle_worker_and_is_idempotent():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    voice.stt_service.transcribe_pcm_bytes = lambda _raw, cancel_event=None: TranscriptionResult(  # type: ignore[method-assign]
        status="ok",
        text="ok",
        detail="ok",
        engine="stub",
    )

    pipeline_id = voice._begin_pipeline()  # noqa: SLF001
    result = voice._transcribe_with_cancel(b"pcm", pipeline_id)  # noqa: SLF001
    assert result.ok is True

    with voice._stt_worker_cv:  # noqa: SLF001
        worker_before = voice._stt_worker_thread  # noqa: SLF001
    assert worker_before is not None and worker_before.is_alive()

    voice.stop_stt_worker(timeout=0.2)

    with voice._stt_worker_cv:  # noqa: SLF001
        worker_after = voice._stt_worker_thread  # noqa: SLF001
        assert voice._stt_active_job is None  # noqa: SLF001
        assert voice._stt_pending_job is None  # noqa: SLF001
    assert worker_after is None or not worker_after.is_alive()

    voice.stop_stt_worker(timeout=0.2)


def test_stop_stt_worker_without_running_worker_keeps_service_usable():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    voice.stop_stt_worker(timeout=0.2)

    voice.stt_service.transcribe_pcm_bytes = lambda _raw, cancel_event=None: TranscriptionResult(  # type: ignore[method-assign]
        status="ok",
        text="ok",
        detail="ok",
        engine="stub",
    )
    pipeline_id = voice._begin_pipeline()  # noqa: SLF001
    result = voice._transcribe_with_cancel(b"pcm", pipeline_id)  # noqa: SLF001

    assert result.ok is True


def test_voice_service_stop_stt_worker_cancels_and_allows_restart(monkeypatch):
    class FakeCaptureService:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def capture_until_silence(self, pre_roll=b""):  # noqa: ARG002
            return SpeechCaptureResult(status="ok", raw_audio=b"pcm", speech_started=True, duration_seconds=0.8)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    started = threading.Event()
    result_box: dict[str, TranscriptionResult] = {}

    monkeypatch.setattr("core.voice.voice_service.SpeechCaptureService", FakeCaptureService)

    def blocking_transcribe(_raw: bytes, cancel_event=None):  # noqa: ANN001
        started.set()
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(0.01)
        return TranscriptionResult(status="cancelled", detail="Запись остановлена.")

    voice.stt_service.transcribe_pcm_bytes = blocking_transcribe  # type: ignore[method-assign]

    worker = threading.Thread(
        target=lambda: result_box.setdefault("result", voice.capture_after_wake_result(b"wake")),
        daemon=True,
    )
    worker.start()
    assert started.wait(1.0)

    voice.stop_stt_worker()
    worker.join(timeout=1.0)

    result = result_box["result"]
    assert worker.is_alive() is False
    assert result.status == "cancelled"

    voice.stt_service.transcribe_pcm_bytes = lambda _raw, cancel_event=None: TranscriptionResult(  # type: ignore[method-assign]
        status="ok",
        text="Готово",
        detail="ok",
        engine="stub",
    )
    pipeline_id = voice._begin_pipeline()  # noqa: SLF001
    restarted = voice._transcribe_with_cancel(b"pcm", pipeline_id)  # noqa: SLF001

    assert restarted.ok is True
    assert restarted.text == "Готово"

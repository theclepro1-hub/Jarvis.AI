from __future__ import annotations

import threading
from types import SimpleNamespace

from ui.bridge.voice_bridge import VoiceBridge


class _Settings:
    def __init__(self) -> None:
        self.payload = {
            "wake_word_enabled": True,
            "allow_ai_after_wake": False,
            "voice_mode": "balance",
            "command_style": "one_shot",
        }

    def get(self, key, default=None):  # noqa: ANN001
        return self.payload.get(key, default)

    def set(self, key, value) -> None:  # noqa: ANN001
        self.payload[key] = value


class _Wake:
    def __init__(self) -> None:
        self.start_calls = 0
        self.warm_up_calls = 0

    def start(self, *_args, **_kwargs) -> str:
        self.start_calls += 1
        return "ok"

    def stop(self) -> None:
        return None

    def status(self) -> str:
        return "Жду «Джарвис»"

    def model_status(self) -> str:
        return "загружена"

    def warm_up_model(self) -> bool:
        self.warm_up_calls += 1
        return True


class _Voice:
    def __init__(self) -> None:
        self.is_recording = False
        self.warm_up_calls = 0
        self.handoff_calls = 0
        self.status_calls: list[tuple[str, bool, str]] = []
        self.metrics = {
            "sessionId": "",
            "phase": "idle",
            "detail": "",
            "wakeBackend": "",
            "sttBackend": "",
            "backendTrace": "",
            "wakeToCaptureMs": 0.0,
            "captureMs": 0.0,
            "sttMs": 0.0,
            "sttToRouteMs": 0.0,
            "totalMs": 0.0,
            "preRollMs": 0.0,
            "capturedAudioMs": 0.0,
            "transcript": "",
            "finalStatus": "",
            "failureDetail": "",
            "routeHookSeen": False,
        }

    def warm_up_local_stt_backend(self) -> bool:
        self.warm_up_calls += 1
        return True

    def latest_wake_metrics(self) -> dict[str, object]:
        return dict(self.metrics)

    def set_wake_runtime_status(self, *_args, **_kwargs) -> None:
        status = str(_args[0]) if _args else str(_kwargs.get("status", ""))
        ready = bool(_kwargs.get("ready", False))
        detail = str(_kwargs.get("detail", ""))
        self.status_calls.append((status, ready, detail))

    def mark_wake_route_handoff(self) -> None:
        self.handoff_calls += 1

    def summary(self) -> str:
        return "summary"

    def strip_wake_word(self, text: str) -> str:
        cleaned = text.strip()
        for prefix in ("Джарвис, ", "Джарвис ", "джарвис, ", "джарвис "):
            if cleaned.startswith(prefix):
                return cleaned[len(prefix):].strip()
        return cleaned

    def runtime_status(self) -> dict[str, str]:
        return {"wakeWord": "Жду «Джарвис»", "command": "готово", "ai": "ok", "model": "загружена", "tts": "ok"}

    def microphone_device_models(self):  # noqa: ANN201
        return []

    def output_device_models(self):  # noqa: ANN201
        return []


class _ChatBridge:
    def __init__(self) -> None:
        self.received: list[tuple[str, str]] = []

    def submitTranscribedText(self, text: str, source: str = "voice") -> None:
        self.received.append((text, source))


class _Services:
    def __init__(self) -> None:
        self.settings = _Settings()
        self.wake = _Wake()
        self.voice = _Voice()
        self.chat_history = SimpleNamespace(clear=lambda: None)
        self.command_router = SimpleNamespace(handle=lambda *_args, **_kwargs: SimpleNamespace(kind="ai", queue_items=[], execution_result=None))
        self.ai = SimpleNamespace()


class _LazyVoiceServices:
    def __init__(self) -> None:
        self.settings = _Settings()
        self.wake = _Wake()
        self._voice = None

    @property
    def voice(self):  # noqa: ANN201
        raise AssertionError("voice service must remain lazy during chat-screen idle rendering")


def test_voice_bridge_warms_up_once_and_starts_wake(monkeypatch):
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    wake_ready = threading.Event()

    def wake_warm() -> bool:
        services.wake.warm_up_calls += 1
        wake_ready.set()
        return True

    services.wake.warm_up_model = wake_warm

    bridge.startWakeRuntime()
    assert wake_ready.wait(1.0)

    bridge.startWakeRuntime()

    assert services.wake.start_calls == 2
    assert services.wake.warm_up_calls == 1
    assert services.voice.warm_up_calls == 0


def test_voice_bridge_prewarm_refreshes_cached_status(monkeypatch):
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    calls = {"warmup": 0, "refresh": 0}
    monkeypatch.setattr(bridge, "_start_voice_runtime_warmup", lambda: calls.__setitem__("warmup", calls["warmup"] + 1))
    monkeypatch.setattr(bridge, "_refresh_voice_status_cache", lambda: calls.__setitem__("refresh", calls["refresh"] + 1))

    bridge.prewarm()

    assert calls["warmup"] == 1
    assert calls["refresh"] == 1
    assert services.wake.start_calls == 0


def test_voice_bridge_deliver_transcribed_text_clears_transient_handoff_status():
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    bridge._deliver_transcribed_text("открой ютуб")  # noqa: SLF001

    assert state.status == "Передаю команду в обработку"
    assert services.voice.handoff_calls == 1
    assert chat_bridge.received == [("открой ютуб", "voice")]
    assert bridge.recordingHint == "Ручной микрофон готов."


def test_voice_bridge_preserves_recognized_text_when_wake_hint_is_active():
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    bridge._wake_hint = "Джарвис услышан. Подхватываю команду..."  # noqa: SLF001
    bridge._deliver_transcribed_text("Джарвис, открой ютуб")  # noqa: SLF001

    assert chat_bridge.received == [("Джарвис, открой ютуб", "voice")]
    assert bridge.wakeHint == "Джарвис услышан. Подхватываю команду..."
    bridge._finalize_capture()  # noqa: SLF001
    assert bridge.wakeHint == ""


def test_voice_bridge_marks_wake_transcription_with_wake_source() -> None:
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    bridge._wake_capture_active = True  # noqa: SLF001
    bridge._deliver_transcribed_text("открой ютуб")  # noqa: SLF001

    assert chat_bridge.received == [("открой ютуб", "wake")]


def test_voice_bridge_round_trips_allow_ai_after_wake_setting() -> None:
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    assert bridge.allowAiAfterWake is False

    bridge.setAllowAiAfterWake(True)

    assert bridge.allowAiAfterWake is True
    assert services.settings.payload["allow_ai_after_wake"] is True


def test_voice_bridge_preserves_failure_note_through_finalize():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._push_voice_note("Не расслышал команду после слова активации.")  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert state.status == "Не расслышал"
    assert bridge.recordingHint == "Не расслышал команду после слова активации."


def test_voice_bridge_preserves_missing_key_note_through_finalize():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._push_voice_note("Нужен ключ для облачного распознавания речи.")  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert state.status == "Нужен ключ для облачного распознавания речи."
    assert bridge.recordingHint == "Нужен ключ для облачного распознавания речи."


def test_voice_bridge_classifies_generic_cloud_note_as_stt_error():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._handle_voice_test_note("Нужен ключ для облачного распознавания речи.")  # noqa: SLF001

    assert bridge.voiceTest["stage"] == "error_stt"


def test_voice_bridge_preserves_missing_model_note_through_finalize():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._push_voice_note("Нужна локальная модель или ключ для облачного распознавания речи.")  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert state.status == "Нужна локальная модель или ключ для облачного распознавания речи."
    assert bridge.recordingHint == "Нужна локальная модель или ключ для облачного распознавания речи."


def test_voice_bridge_clears_wake_hint_when_capture_finishes():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._wake_hint = "Услышал «Джарвис». Подхватываю начало команды..."  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert bridge.wakeHint == ""


def test_voice_bridge_marks_wake_command_as_recognizing_before_handoff():
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    class _WakeResult:
        ok = True
        text = "открой параметры"

    services.voice.capture_after_wake_result = lambda _pre_roll: _WakeResult()  # noqa: E731

    bridge._finish_after_wake(b"wake")  # noqa: SLF001

    assert services.voice.status_calls[0] == (
        "recognizing_command",
        False,
        "Распознаю команду после «Джарвис»",
    )
    assert services.voice.handoff_calls == 1
    assert chat_bridge.received == [("открой параметры", "voice")]
    assert state.status == "Готов"
    assert bridge.recordingHint == "Ручной микрофон готов."


def test_voice_bridge_treats_wake_capture_as_active_recording_until_finalize():
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    class _WakeResult:
        ok = True
        text = "открой ютуб"

    services.voice.capture_after_wake_result = lambda _pre_roll: _WakeResult()  # noqa: E731

    bridge._handle_wake_detected(b"wake")  # noqa: SLF001

    assert bridge.isRecording is True
    assert "Джарвис" in bridge.recordingHint

    bridge._finish_after_wake(b"wake")  # noqa: SLF001

    assert bridge.isRecording is False
    assert bridge.recordingHint == "Ручной микрофон готов."
    assert chat_bridge.received == [("открой ютуб", "wake")]


def test_voice_bridge_runtime_status_keeps_command_backend_and_exposes_wake_model():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    status = bridge.runtimeStatus

    assert status["wakeWord"] == "Жду «Джарвис»"
    assert status["wakeModel"] == "загружена"
    assert status["model"] == "загружена"
    assert status["command"] == "готово"


def test_voice_bridge_failed_warmup_can_retry_on_next_start():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    wake_ready = threading.Event()
    attempts = {"wake": 0}

    def wake_warm() -> bool:
        attempts["wake"] += 1
        services.wake.warm_up_calls += 1
        if attempts["wake"] == 1:
            return False
        wake_ready.set()
        return True

    services.wake.warm_up_model = wake_warm

    bridge.startWakeRuntime()
    assert wake_ready.wait(0.2) is False

    wake_ready.clear()
    bridge.startWakeRuntime()

    assert wake_ready.wait(1.0)
    assert services.wake.start_calls == 2
    assert services.wake.warm_up_calls == 2


def test_voice_bridge_is_recording_does_not_force_lazy_voice_service():
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, _LazyVoiceServices(), chat_bridge=_ChatBridge())

    assert bridge.isRecording is False

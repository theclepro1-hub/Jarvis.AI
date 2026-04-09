from __future__ import annotations

import threading
from types import SimpleNamespace

from ui.bridge.voice_bridge import VoiceBridge


class _Settings:
    def __init__(self) -> None:
        self.payload = {"wake_word_enabled": True, "voice_mode": "balance", "command_style": "one_shot"}

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
        return None

    def mark_wake_route_handoff(self) -> None:
        self.handoff_calls += 1

    def summary(self) -> str:
        return "summary"

    def runtime_status(self) -> dict[str, str]:
        return {"wakeWord": "Жду «Джарвис»", "command": "готово", "ai": "ok", "model": "загружена", "tts": "ok"}

    def microphone_device_models(self):  # noqa: ANN201
        return []

    def output_device_models(self):  # noqa: ANN201
        return []


class _ChatBridge:
    def __init__(self) -> None:
        self.received: list[str] = []

    def submitTranscribedText(self, text: str) -> None:
        self.received.append(text)


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
    voice_ready = threading.Event()

    def wake_warm() -> bool:
        services.wake.warm_up_calls += 1
        wake_ready.set()
        return True

    def voice_warm() -> bool:
        services.voice.warm_up_calls += 1
        voice_ready.set()
        return True

    services.wake.warm_up_model = wake_warm
    services.voice.warm_up_local_stt_backend = voice_warm

    bridge.startWakeRuntime()
    assert wake_ready.wait(1.0)
    assert voice_ready.wait(1.0)

    bridge.startWakeRuntime()

    assert services.wake.start_calls == 2
    assert services.wake.warm_up_calls == 1
    assert services.voice.warm_up_calls == 1


def test_voice_bridge_deliver_transcribed_text_sets_handoff_status():
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    bridge._deliver_transcribed_text("открой ютуб")  # noqa: SLF001

    assert state.status == "Передаю команду в обработку"
    assert services.voice.handoff_calls == 1
    assert chat_bridge.received == ["открой ютуб"]
    assert bridge.recordingHint == "Команда распознана. Передаю в обработку..."


def test_voice_bridge_preserves_failure_note_through_finalize():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._push_voice_note("Не расслышал команду после слова активации.")  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert state.status == "Не расслышал"
    assert bridge.recordingHint == "Не расслышал команду после слова активации."


def test_voice_bridge_keeps_wake_hint_until_explicit_clear():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._wake_hint = "Услышал «Джарвис». Подхватываю начало команды..."  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert bridge.wakeHint == "Услышал «Джарвис». Подхватываю начало команды..."

    bridge.clearWakeHint()

    assert bridge.wakeHint == ""


def test_voice_bridge_is_recording_does_not_force_lazy_voice_service():
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, _LazyVoiceServices(), chat_bridge=_ChatBridge())

    assert bridge.isRecording is False

from __future__ import annotations

import sys
import threading
import types
from types import SimpleNamespace

if "PySide6.QtCore" not in sys.modules:
    class _BoundSignal:
        def __init__(self) -> None:
            self._subscribers: list[object] = []

        def connect(self, callback) -> None:  # noqa: ANN001
            self._subscribers.append(callback)

        def emit(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            for callback in list(self._subscribers):
                callback(*args, **kwargs)

    class _SignalDescriptor:
        def __set_name__(self, _owner, name: str) -> None:  # noqa: ANN001
            self._name = f"__signal_{name}"

        def __get__(self, instance, _owner):  # noqa: ANN001, ANN202
            if instance is None:
                return self
            signal = instance.__dict__.get(self._name)
            if signal is None:
                signal = _BoundSignal()
                instance.__dict__[self._name] = signal
            return signal

    class _QObject:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

    def _property(*_args, **_kwargs):  # noqa: ANN002, ANN003
        def decorator(func):  # noqa: ANN001
            return property(func)

        return decorator

    def _slot(*_args, **_kwargs):  # noqa: ANN002, ANN003
        def decorator(func):  # noqa: ANN001
            return func

        return decorator

    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.QObject = _QObject
    qtcore.Property = _property
    qtcore.Signal = lambda *_args, **_kwargs: _SignalDescriptor()
    qtcore.Slot = _slot
    pyside6 = types.ModuleType("PySide6")
    pyside6.QtCore = qtcore
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore

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
    assert chat_bridge.received == ["открой параметры"]
    assert state.status == "Готов"


def test_voice_bridge_runtime_status_keeps_command_backend_and_exposes_wake_model():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    status = bridge.runtimeStatus

    assert status["wakeWord"] == "Жду «Джарвис»"
    assert status["wakeModel"] == "загружена"
    assert status["model"] == "загружена"
    assert "облако" in status["command"].casefold()
    assert status["assistantMode"] == "standard"
    assert status["assistantWake"] == "Локально"
    assert status["assistantTextRoute"] == "Автоматически"
    assert status["assistantSttRoute"] == "Автоматически"
    assert status["assistantPrivacy"] == "Сначала локально, потом облако"
    assert status["assistantReadiness"].startswith("Не хватает")


def test_voice_bridge_failed_warmup_can_retry_on_next_start():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    wake_ready = threading.Event()
    voice_ready = threading.Event()
    attempts = {"voice": 0}

    def wake_warm() -> bool:
        services.wake.warm_up_calls += 1
        wake_ready.set()
        return True

    def voice_warm() -> bool:
        attempts["voice"] += 1
        services.voice.warm_up_calls += 1
        if attempts["voice"] == 1:
            return False
        voice_ready.set()
        return True

    services.wake.warm_up_model = wake_warm
    services.voice.warm_up_local_stt_backend = voice_warm

    bridge.startWakeRuntime()
    assert wake_ready.wait(1.0)

    wake_ready.clear()
    bridge.startWakeRuntime()

    assert wake_ready.wait(1.0)
    assert voice_ready.wait(1.0)
    assert services.wake.start_calls == 2
    assert services.voice.warm_up_calls == 2


def test_voice_bridge_is_recording_does_not_force_lazy_voice_service():
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, _LazyVoiceServices(), chat_bridge=_ChatBridge())

    assert bridge.isRecording is False


def test_voice_bridge_normalizes_legacy_mode_values():
    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    assert bridge.mode == "standard"

    bridge.setMode("quality")

    assert bridge.mode == "smart"
    assert bridge.assistantMode == "smart"
    assert services.settings.payload["assistant_mode"] == "smart"
    assert services.settings.payload["ai_mode"] == "quality"
    assert services.settings.payload["voice_mode"] == "smart"


def test_voice_bridge_private_local_only_note_is_reported_as_stt_error():
    services = _Services()
    services.settings.payload["voice_mode"] = "private"
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    note = bridge._wake_failure_note(  # noqa: SLF001
        SimpleNamespace(
            status="model_missing",
            detail="Приватный режим требует локальный backend распознавания. Облачный fallback отключён.",
        )
    )
    bridge._push_voice_note(note)  # noqa: SLF001

    assert "локаль" in note.casefold()
    assert "Groq" not in note
    assert state.status == "Ошибка распознавания"

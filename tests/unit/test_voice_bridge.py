from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

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
        self.stop_calls = 0

    def start(self, *_args, **_kwargs) -> str:
        self.start_calls += 1
        return "ok"

    def stop(self) -> None:
        self.stop_calls += 1
        return None

    def status(self) -> str:
        return 'Жду «Джарвис»'

    def model_status(self) -> str:
        return 'загружена'

    def warm_up_model(self) -> bool:
        self.warm_up_calls += 1
        return True


class _Voice:
    def __init__(self) -> None:
        self.is_recording = False
        self.warm_up_calls = 0
        self.jarvis_test_calls = 0
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

    def test_jarvis_voice(self) -> str:
        self.jarvis_test_calls += 1
        return "Проверка голоса: ок"

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
        return {"wakeWord": 'Жду «Джарвис»', "command": 'готово', "ai": "ok", "model": 'загружена', "tts": "ok"}

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
    state = SimpleNamespace(status='Готов')
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
    state = SimpleNamespace(status='Готов')
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)
    initial_status = state.status

    bridge._deliver_transcribed_text('открой ютуб')  # noqa: SLF001

    assert state.status != initial_status
    assert services.voice.handoff_calls == 1
    assert chat_bridge.received == ['открой ютуб']
    assert isinstance(bridge.recordingHint, str)
    assert bridge.recordingHint


def test_voice_bridge_preserves_failure_note_through_finalize():
    services = _Services()
    state = SimpleNamespace(status='Готов')
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    note = bridge._wake_failure_note(SimpleNamespace(status="no_speech", detail=""))  # noqa: SLF001

    bridge._push_voice_note(note)  # noqa: SLF001
    status_before_finalize = state.status
    bridge._finalize_capture()  # noqa: SLF001

    assert state.status == status_before_finalize
    assert bridge.recordingHint == note


def test_voice_bridge_keeps_wake_hint_until_explicit_clear():
    services = _Services()
    state = SimpleNamespace(status='Готов')
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    bridge._wake_hint = 'Услышал «Джарвис». Подхватываю начало команды...'  # noqa: SLF001
    bridge._finalize_capture()  # noqa: SLF001

    assert bridge.wakeHint == 'Услышал «Джарвис». Подхватываю начало команды...'

    bridge.clearWakeHint()

    assert bridge.wakeHint == ""


def test_voice_bridge_marks_wake_command_as_recognizing_before_handoff():
    services = _Services()
    chat_bridge = _ChatBridge()
    state = SimpleNamespace(status='Готов')
    bridge = VoiceBridge(state, services, chat_bridge=chat_bridge)

    class _WakeResult:
        ok = True
        text = 'открой параметры'

    services.voice.capture_after_wake_result = lambda _pre_roll: _WakeResult()  # noqa: E731

    bridge._finish_after_wake(b"wake")  # noqa: SLF001

    status, ready, detail = services.voice.status_calls[0]
    assert status == "recognizing_command"
    assert ready is False
    assert isinstance(detail, str)
    assert detail
    assert services.voice.handoff_calls == 1
    assert chat_bridge.received == ['открой параметры']
    assert isinstance(state.status, str)
    assert state.status


def test_voice_bridge_failed_warmup_can_retry_on_next_start():
    services = _Services()
    state = SimpleNamespace(status='Готов')
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


def test_voice_bridge_restarts_wake_after_successful_model_download():
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="ready")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    services.wake.phase = "error"
    model_ready = {"value": False}

    def wake_warm() -> bool:
        services.wake.warm_up_calls += 1
        model_ready["value"] = True
        return True

    services.wake.warm_up_model = wake_warm
    services.wake.model_status = lambda: "ready" if model_ready["value"] else "missing"

    bridge.startWakeRuntime()
    starts_before = services.wake.start_calls

    deadline = time.monotonic() + 1.0
    while services.wake.start_calls <= starts_before and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert services.wake.start_calls == starts_before + 1


def test_voice_bridge_restarts_wake_when_warmup_reports_false_but_model_is_ready():
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="ready")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    services.wake.phase = "error"
    model_ready = {"value": False}

    def wake_warm() -> bool:
        services.wake.warm_up_calls += 1
        model_ready["value"] = True
        return False

    services.wake.warm_up_model = wake_warm
    services.wake.model_status = lambda: "ready" if model_ready["value"] else "missing"

    bridge.startWakeRuntime()
    starts_before = services.wake.start_calls

    deadline = time.monotonic() + 1.0
    while services.wake.start_calls <= starts_before and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert services.wake.start_calls == starts_before + 1


def test_voice_bridge_selected_device_prefers_exact_model_name():
    services = _Services()
    state = SimpleNamespace(status="ready")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    class _Model:
        def __init__(self, name: str) -> None:
            self._name = name

        def as_qml(self) -> dict[str, str]:
            return {"name": self._name}

    canonical = "realtek hd audio mic"

    def normalize(value: str) -> str:
        text = str(value).casefold()
        if "realtek" in text:
            return canonical
        return value

    services.voice.normalize_microphone_selection = normalize
    services.voice.microphone_device_models = lambda: [_Model("Realtek HD Audio Mic • Windows WDM-KS • 2 кан.")]
    services.settings.set("microphone_name", canonical)

    assert bridge.selectedMicrophone == "Realtek HD Audio Mic • Windows WDM-KS • 2 кан."


def test_voice_bridge_selected_output_prefers_exact_model_name():
    services = _Services()
    state = SimpleNamespace(status="ready")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())

    class _Model:
        def __init__(self, name: str) -> None:
            self._name = name

        def as_qml(self) -> dict[str, str]:
            return {"name": self._name}

    canonical = "logitech pro x"

    def normalize(value: str) -> str:
        text = str(value).casefold()
        if "logitech" in text:
            return canonical
        return value

    services.voice.normalize_output_selection = normalize
    services.voice.output_device_models = lambda: [_Model("Logitech PRO X • Windows DirectSound • 1 кан.")]
    services.settings.set("voice_output_name", canonical)

    assert bridge.selectedOutputDevice == "Logitech PRO X • Windows DirectSound • 1 кан."


def test_voice_bridge_ignores_second_wake_detect_while_capture_is_inflight():
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="ready")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    capture_entered = threading.Event()
    release_capture = threading.Event()
    capture_calls = {"count": 0}

    class _WakeResult:
        ok = False
        text = ""
        status = "no_speech"
        detail = ""

    def slow_capture(_pre_roll: bytes) -> _WakeResult:
        capture_calls["count"] += 1
        capture_entered.set()
        release_capture.wait(1.0)
        return _WakeResult()

    services.voice.capture_after_wake_result = slow_capture

    bridge._handle_wake_detected(b"first")  # noqa: SLF001
    assert capture_entered.wait(1.0)

    bridge._handle_wake_detected(b"second")  # noqa: SLF001
    assert capture_calls["count"] == 1

    release_capture.set()
    deadline = time.monotonic() + 1.0
    while bridge._wake_capture_inflight and time.monotonic() < deadline:  # noqa: SLF001
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert capture_calls["count"] == 1


def test_voice_bridge_is_recording_does_not_force_lazy_voice_service():
    state = SimpleNamespace(status='Готов')
    bridge = VoiceBridge(state, _LazyVoiceServices(), chat_bridge=_ChatBridge())

    assert bridge.isRecording is False


def test_run_jarvis_voice_test_emits_result_signal() -> None:
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    result_spy = QSignalSpy(bridge.testResultChanged)

    bridge.runJarvisVoiceTest()

    assert result_spy.wait(1000)
    assert services.voice.jarvis_test_calls == 1
    assert isinstance(bridge.testResult, str)
    assert bridge.testResult
    assert result_spy.count() == 1


def test_run_jarvis_voice_test_skips_parallel_requests() -> None:
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    started = threading.Event()
    release = threading.Event()
    result_spy = QSignalSpy(bridge.testResultChanged)

    def slow_test() -> str:
        services.voice.jarvis_test_calls += 1
        started.set()
        release.wait(1.0)
        return "ok"

    services.voice.test_jarvis_voice = slow_test

    bridge.runJarvisVoiceTest()
    assert started.wait(1.0)

    bridge.runJarvisVoiceTest()
    assert services.voice.jarvis_test_calls == 1

    release.set()
    deadline = time.monotonic() + 1.0
    while result_spy.count() == 0 and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert result_spy.count() >= 1


def test_wake_word_reenable_waits_for_inflight_stop() -> None:
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    stop_entered = threading.Event()
    release_stop = threading.Event()
    stop_spy = QSignalSpy(bridge.wakeStopCompleted)

    def blocking_stop() -> None:
        stop_entered.set()
        release_stop.wait(1.0)

    services.wake.stop = blocking_stop

    bridge.wakeWordEnabled = False
    assert stop_entered.wait(1.0)

    starts_before = services.wake.start_calls
    bridge.wakeWordEnabled = True
    assert services.wake.start_calls == starts_before

    release_stop.set()
    deadline = time.monotonic() + 1.0
    while stop_spy.count() == 0 and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert stop_spy.count() >= 1
    restart_deadline = time.monotonic() + 1.0
    while services.wake.start_calls == starts_before and time.monotonic() < restart_deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert services.wake.start_calls == starts_before + 1


def test_shutdown_does_not_emit_late_wake_stop_completed() -> None:
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    stop_entered = threading.Event()
    release_stop = threading.Event()
    stop_spy = QSignalSpy(bridge.wakeStopCompleted)

    def blocking_stop() -> None:
        services.wake.stop_calls += 1
        stop_entered.set()
        release_stop.wait(1.0)

    services.wake.stop = blocking_stop

    bridge.wakeWordEnabled = False
    assert stop_entered.wait(1.0)

    shutdown_done = threading.Event()
    threading.Thread(target=lambda: (bridge.shutdown(), shutdown_done.set()), daemon=True).start()
    time.sleep(0.05)
    release_stop.set()
    assert shutdown_done.wait(1.0)

    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert stop_spy.count() == 0
    assert services.wake.stop_calls == 1
    assert bridge._wake_stop_inflight is False  # noqa: SLF001
    assert bridge._wake_stop_actions == []  # noqa: SLF001


def test_shutdown_resets_jarvis_test_inflight_flag() -> None:
    QCoreApplication.instance() or QCoreApplication([])

    services = _Services()
    state = SimpleNamespace(status="Готов")
    bridge = VoiceBridge(state, services, chat_bridge=_ChatBridge())
    started = threading.Event()
    release = threading.Event()

    def slow_test() -> str:
        services.voice.jarvis_test_calls += 1
        started.set()
        release.wait(1.0)
        return "ok"

    services.voice.test_jarvis_voice = slow_test

    bridge.runJarvisVoiceTest()
    assert started.wait(1.0)
    assert bridge._jarvis_voice_test_inflight is True  # noqa: SLF001

    bridge.shutdown()
    assert bridge._jarvis_voice_test_inflight is False  # noqa: SLF001
    release.set()

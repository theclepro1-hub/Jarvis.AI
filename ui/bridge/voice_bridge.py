from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Property, Signal, Slot


class VoiceBridge(QObject):
    modeChanged = Signal()
    commandStyleChanged = Signal()
    wakeWordEnabledChanged = Signal()
    summaryChanged = Signal()
    statusChanged = Signal()
    microphonesChanged = Signal()
    selectedMicrophoneChanged = Signal()
    testResultChanged = Signal()
    recordingChanged = Signal()
    recordingHintChanged = Signal()
    transcribedTextReady = Signal(str)
    voiceNoteReady = Signal(str)
    captureFinished = Signal()
    wakeDetected = Signal(bytes)
    wakeStatusUpdated = Signal()

    def __init__(self, state, services, chat_bridge=None) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self._test_result = "Пока без активного теста."
        self._recording_hint = "Ручной микрофон готов."
        self._chat_bridge = chat_bridge
        self.transcribedTextReady.connect(self._deliver_transcribed_text)
        self.voiceNoteReady.connect(self._push_voice_note)
        self.captureFinished.connect(self._finalize_capture)
        self.wakeDetected.connect(self._handle_wake_detected)
        self.wakeStatusUpdated.connect(self._emit_voice_status_change)

    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        return self.services.settings.get("voice_mode", "balance")

    @mode.setter
    def mode(self, value: str) -> None:
        self.services.settings.set("voice_mode", value)
        self.modeChanged.emit()
        self.summaryChanged.emit()

    @Property(str, notify=commandStyleChanged)
    def commandStyle(self) -> str:
        return self.services.settings.get("command_style", "one_shot")

    @commandStyle.setter
    def commandStyle(self, value: str) -> None:
        self.services.settings.set("command_style", value)
        self.commandStyleChanged.emit()
        self.summaryChanged.emit()

    @Property(bool, notify=wakeWordEnabledChanged)
    def wakeWordEnabled(self) -> bool:
        return self.services.settings.get("wake_word_enabled", True)

    @wakeWordEnabled.setter
    def wakeWordEnabled(self, value: bool) -> None:
        self.services.settings.set("wake_word_enabled", value)
        if value:
            self.startWakeRuntime()
        else:
            self.services.wake.stop()
        self.wakeWordEnabledChanged.emit()
        self.summaryChanged.emit()
        self.statusChanged.emit()

    @Property("QVariantList", notify=microphonesChanged)
    def microphones(self) -> list[str]:
        return self.services.voice.microphones

    @Property(str, notify=selectedMicrophoneChanged)
    def selectedMicrophone(self) -> str:
        selected = self.services.settings.get("microphone_name", "Системный по умолчанию")
        return self.services.voice.normalize_microphone_selection(selected)

    @selectedMicrophone.setter
    def selectedMicrophone(self, value: str) -> None:
        normalized = self.services.voice.normalize_microphone_selection(value)
        self.services.settings.set("microphone_name", normalized)
        self.selectedMicrophoneChanged.emit()
        self.summaryChanged.emit()
        self.statusChanged.emit()
        if self.wakeWordEnabled and not self.services.voice.is_recording:
            self.services.wake.stop()
            self.startWakeRuntime()

    @Property(str, notify=summaryChanged)
    def summary(self) -> str:
        return self.services.voice.summary()

    @Property("QVariantMap", notify=statusChanged)
    def runtimeStatus(self) -> dict[str, str]:
        status = self.services.voice.runtime_status()
        status["wakeWord"] = self.services.wake.status()
        status["model"] = self.services.wake.model_status()
        return status

    @Property(str, notify=testResultChanged)
    def testResult(self) -> str:
        return self._test_result

    @Property(bool, notify=recordingChanged)
    def isRecording(self) -> bool:
        return self.services.voice.is_recording

    @Property(str, notify=recordingHintChanged)
    def recordingHint(self) -> str:
        return self._recording_hint

    @Slot()
    def runWakeWordTest(self) -> None:
        self._test_result = self.services.voice.test_wake_word()
        self.testResultChanged.emit()

    @Slot(str)
    def setMode(self, value: str) -> None:
        self.mode = value

    @Slot(str)
    def setCommandStyle(self, value: str) -> None:
        self.commandStyle = value

    @Slot(bool)
    def setWakeWordEnabled(self, value: bool) -> None:
        self.wakeWordEnabled = value

    @Slot(str)
    def setMicrophone(self, value: str) -> None:
        self.selectedMicrophone = value

    @Slot()
    def toggleManualCapture(self) -> None:
        if not self.services.voice.is_recording:
            self.services.wake.stop()
            self._recording_hint = self.services.voice.start_manual_capture(
                on_text=self.transcribedTextReady.emit,
                on_note=self.voiceNoteReady.emit,
                on_finish=self.captureFinished.emit,
            )
            self.recordingHintChanged.emit()
            self.recordingChanged.emit()
            self.state.status = "Слушаю"
            return

        self._recording_hint = "Останавливаю запись..."
        self.recordingHintChanged.emit()
        self.recordingChanged.emit()
        self.state.status = "Останавливаю"
        self.services.voice.stop_manual_capture()

    def startWakeRuntime(self) -> None:
        if not self.services.settings.get("wake_word_enabled", True):
            return
        if self.services.voice.is_recording:
            return
        self.services.wake.start(self._emit_wake_detected, self._emit_wake_status_updated)
        self.summaryChanged.emit()
        self.statusChanged.emit()

    @Slot()
    def shutdown(self) -> None:
        self.services.wake.stop()

    def _deliver_transcribed_text(self, text: str) -> None:
        if self._chat_bridge is not None:
            self._chat_bridge.submitTranscribedText(text)

    def _push_voice_note(self, note: str) -> None:
        if self._chat_bridge is not None:
            self._chat_bridge.appendAssistantNote(note)

    def _finalize_capture(self) -> None:
        self.recordingChanged.emit()
        self._recording_hint = "Ручной микрофон готов."
        self.recordingHintChanged.emit()
        self.state.status = "Готов"
        if self.wakeWordEnabled:
            self.startWakeRuntime()

    def _emit_wake_detected(self, pre_roll: bytes) -> None:
        self.wakeDetected.emit(pre_roll)

    def _emit_wake_status_updated(self) -> None:
        self.wakeStatusUpdated.emit()

    def _handle_wake_detected(self, pre_roll: bytes) -> None:
        if self.services.voice.is_recording:
            return
        self._recording_hint = "Слово активации найдено. Подхватываю команду..."
        self.recordingHintChanged.emit()
        self.state.status = "Слушаю"
        self.services.voice.set_wake_runtime_status("transcribing", ready=False, detail="Распознаю команду")
        thread = threading.Thread(target=self._finish_after_wake, args=(pre_roll,), daemon=True)
        thread.start()

    def _finish_after_wake(self, pre_roll: bytes) -> None:
        text = self.services.voice.capture_after_wake(pre_roll)
        if text:
            self.transcribedTextReady.emit(text)
        else:
            self.voiceNoteReady.emit("Wake word услышан, но команду после него разобрать не удалось.")
        self.captureFinished.emit()

    def _emit_voice_status_change(self) -> None:
        self.summaryChanged.emit()
        self.statusChanged.emit()

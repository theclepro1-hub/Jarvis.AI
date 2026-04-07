from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Property, Signal, Slot


class VoiceBridge(QObject):
    modeChanged = Signal()
    commandStyleChanged = Signal()
    wakeWordEnabledChanged = Signal()
    voiceResponseEnabledChanged = Signal()
    ttsEngineChanged = Signal()
    ttsOutputRoutingChanged = Signal()
    ttsVoicesChanged = Signal()
    selectedTtsVoiceChanged = Signal()
    ttsRateChanged = Signal()
    ttsVolumeChanged = Signal()
    summaryChanged = Signal()
    statusChanged = Signal()
    microphonesChanged = Signal()
    outputDevicesChanged = Signal()
    selectedMicrophoneChanged = Signal()
    selectedOutputDeviceChanged = Signal()
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
        self._test_result = "Проверка ещё не запускалась."
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

    @Property(bool, notify=voiceResponseEnabledChanged)
    def voiceResponseEnabled(self) -> bool:
        return self.services.voice.voice_response_enabled()

    @voiceResponseEnabled.setter
    def voiceResponseEnabled(self, value: bool) -> None:
        self.services.settings.set("voice_response_enabled", bool(value))
        self.voiceResponseEnabledChanged.emit()
        self.summaryChanged.emit()
        self.statusChanged.emit()

    @Property(str, notify=ttsEngineChanged)
    def ttsEngine(self) -> str:
        return self.services.voice.tts_engine()

    @ttsEngine.setter
    def ttsEngine(self, value: str) -> None:
        self.services.settings.set("tts_engine", value)
        self.ttsEngineChanged.emit()
        self.ttsOutputRoutingChanged.emit()
        self.ttsVoicesChanged.emit()
        self.selectedTtsVoiceChanged.emit()
        self.statusChanged.emit()

    @Property("QVariantList", notify=ttsEngineChanged)
    def ttsEngines(self) -> list[dict[str, object]]:
        return self.services.voice.available_tts_engines()

    @Property(bool, notify=ttsOutputRoutingChanged)
    def canRouteTtsOutput(self) -> bool:
        return self.services.voice.can_route_tts_output()

    @Property("QVariantList", notify=ttsVoicesChanged)
    def ttsVoices(self) -> list[str]:
        return self.services.voice.available_tts_voices()

    @Property(str, notify=selectedTtsVoiceChanged)
    def selectedTtsVoice(self) -> str:
        selected = self.services.voice.tts_voice_name()
        return selected if selected in self.services.voice.available_tts_voices() else "Голос по умолчанию"

    @selectedTtsVoice.setter
    def selectedTtsVoice(self, value: str) -> None:
        self.services.settings.set("tts_voice_name", value or "Голос по умолчанию")
        self.selectedTtsVoiceChanged.emit()

    @Property(int, notify=ttsRateChanged)
    def ttsRate(self) -> int:
        return self.services.voice.tts_rate()

    @ttsRate.setter
    def ttsRate(self, value: int) -> None:
        self.services.settings.set("tts_rate", max(80, min(320, int(value))))
        self.ttsRateChanged.emit()

    @Property(int, notify=ttsVolumeChanged)
    def ttsVolume(self) -> int:
        return self.services.voice.tts_volume()

    @ttsVolume.setter
    def ttsVolume(self, value: int) -> None:
        self.services.settings.set("tts_volume", max(0, min(100, int(value))))
        self.ttsVolumeChanged.emit()

    @Property("QVariantList", notify=microphonesChanged)
    def microphones(self) -> list[str]:
        return self.services.voice.microphones

    @Property("QVariantList", notify=microphonesChanged)
    def microphoneDeviceModels(self) -> list[dict[str, str | int | bool]]:
        return [device.as_qml() for device in self.services.voice.microphone_device_models]

    @Property("QVariantList", notify=outputDevicesChanged)
    def outputDevices(self) -> list[str]:
        return self.services.voice.output_devices

    @Property("QVariantList", notify=outputDevicesChanged)
    def outputDeviceModels(self) -> list[dict[str, str | int | bool]]:
        return [device.as_qml() for device in self.services.voice.output_device_models]

    @Property(str, notify=selectedMicrophoneChanged)
    def selectedMicrophone(self) -> str:
        selected = self.services.settings.get("microphone_name", "Системный микрофон")
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

    @Property(str, notify=selectedOutputDeviceChanged)
    def selectedOutputDevice(self) -> str:
        selected = self.services.settings.get("voice_output_name", "Системный вывод")
        return self.services.voice.normalize_output_selection(selected)

    @selectedOutputDevice.setter
    def selectedOutputDevice(self, value: str) -> None:
        normalized = self.services.voice.normalize_output_selection(value)
        self.services.settings.set("voice_output_name", normalized)
        self.selectedOutputDeviceChanged.emit()
        self.statusChanged.emit()

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

    @Slot()
    def runJarvisVoiceTest(self) -> None:
        self._test_result = self.services.voice.test_jarvis_voice()
        self.testResultChanged.emit()
        self.statusChanged.emit()

    @Slot(str)
    def setMode(self, value: str) -> None:
        self.mode = value

    @Slot(str)
    def setCommandStyle(self, value: str) -> None:
        self.commandStyle = value

    @Slot(bool)
    def setWakeWordEnabled(self, value: bool) -> None:
        self.wakeWordEnabled = value

    @Slot(bool)
    def setVoiceResponseEnabled(self, value: bool) -> None:
        self.voiceResponseEnabled = value

    @Slot(str)
    def setTtsEngine(self, value: str) -> None:
        self.ttsEngine = value

    @Slot(str)
    def setTtsVoice(self, value: str) -> None:
        self.selectedTtsVoice = value

    @Slot(int)
    def setTtsRate(self, value: int) -> None:
        self.ttsRate = value

    @Slot(int)
    def setTtsVolume(self, value: int) -> None:
        self.ttsVolume = value

    @Slot(str)
    def setMicrophone(self, value: str) -> None:
        self.selectedMicrophone = value

    @Slot(str)
    def setOutputDevice(self, value: str) -> None:
        self.selectedOutputDevice = value

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
        self._recording_hint = note
        self.recordingHintChanged.emit()
        self.state.status = "Готов"

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
        if hasattr(self.services.voice, "capture_after_wake_result"):
            result = self.services.voice.capture_after_wake_result(pre_roll)
            if result.ok and result.text.strip():
                self.transcribedTextReady.emit(result.text)
            else:
                self.voiceNoteReady.emit(self._wake_failure_note(result))
            self.captureFinished.emit()
            return

        text = self.services.voice.capture_after_wake(pre_roll)
        if text:
            self.transcribedTextReady.emit(text)
        else:
            self.services.voice.set_wake_runtime_status(
                "not_heard",
                ready=False,
                detail="Не расслышал команду после слова активации",
            )
            self.voiceNoteReady.emit("Не расслышал команду после слова активации.")
        self.captureFinished.emit()

    def _emit_voice_status_change(self) -> None:
        self.summaryChanged.emit()
        self.statusChanged.emit()

    def _wake_failure_note(self, result) -> str:  # noqa: ANN001
        status = str(getattr(result, "status", ""))
        detail = str(getattr(result, "detail", "") or "").strip()
        if status == "mic_open_failed":
            return "Не удалось открыть микрофон. Проверьте выбранное устройство."
        if status == "stt_key_missing":
            return "Нужен ключ Groq для облачного распознавания."
        if status == "model_missing":
            return "Нужен ключ Groq или локальная модель распознавания."
        if status == "no_speech":
            return "Не расслышал команду после слова активации."
        if detail:
            return detail
        return "Не удалось разобрать команду после слова активации."

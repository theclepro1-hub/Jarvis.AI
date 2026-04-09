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
    wakeHintChanged = Signal()
    voiceTestChanged = Signal()
    voiceTimingsChanged = Signal()
    voiceTestTextReady = Signal(str)
    voiceTestNoteReady = Signal(str)
    voiceTestFinished = Signal()
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
        self._wake_hint = ""
        self._voice_test = self._empty_voice_test()
        self._chat_bridge = chat_bridge
        self._warmup_lock = threading.Lock()
        self._warmup_started = False
        self.voiceTestTextReady.connect(self._handle_voice_test_text)
        self.voiceTestNoteReady.connect(self._handle_voice_test_note)
        self.voiceTestFinished.connect(self._finish_voice_test)
        self.transcribedTextReady.connect(self._deliver_transcribed_text)
        self.voiceNoteReady.connect(self._push_voice_note)
        self.captureFinished.connect(self._finalize_capture)
        self.wakeDetected.connect(self._handle_wake_detected)
        self.wakeStatusUpdated.connect(self._emit_voice_status_change)

    def _voice_backend_if_ready(self):  # noqa: ANN202
        if hasattr(self.services, "_voice"):
            return getattr(self.services, "_voice")
        if hasattr(self.services, "__dict__") and "voice" in vars(self.services):
            return vars(self.services).get("voice")
        return None

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

    @Property("QVariantMap", notify=voiceTestChanged)
    def voiceTest(self) -> dict[str, object]:
        return self._voice_test

    @Property(bool, notify=recordingChanged)
    def isRecording(self) -> bool:
        voice_backend = self._voice_backend_if_ready()
        return bool(getattr(voice_backend, "is_recording", False))

    @Property(str, notify=recordingHintChanged)
    def recordingHint(self) -> str:
        return self._recording_hint

    @Property(str, notify=wakeHintChanged)
    def wakeHint(self) -> str:
        return self._wake_hint

    @Slot()
    def clearWakeHint(self) -> None:
        if not self._wake_hint:
            return
        self._wake_hint = ""
        self.wakeHintChanged.emit()

    @Property("QVariantMap", notify=voiceTimingsChanged)
    def voiceTimings(self) -> dict[str, object]:
        return self.services.voice.latest_wake_metrics()

    @Slot()
    def runWakeWordTest(self) -> None:
        self._test_result = self.services.voice.test_wake_word()
        self.testResultChanged.emit()

    @Slot()
    def runJarvisVoiceTest(self) -> None:
        self._test_result = self.services.voice.test_jarvis_voice()
        self.testResultChanged.emit()
        self.statusChanged.emit()

    @Slot()
    def runVoiceUnderstandingTest(self) -> None:
        if self.services.voice.is_recording:
            self._test_result = "Запись уже идёт."
            self.testResultChanged.emit()
            return

        self.services.wake.stop()
        self._voice_test = self._empty_voice_test(stage="listening")
        self.voiceTestChanged.emit()
        self._recording_hint = "Скажите короткую фразу для проверки."
        self.recordingHintChanged.emit()
        self.clearWakeHint()
        self.state.status = "Слушаю"
        self._test_result = "Слушаю..."
        self.testResultChanged.emit()
        self.services.voice.start_manual_capture(
            on_text=self.voiceTestTextReady.emit,
            on_note=self.voiceTestNoteReady.emit,
            on_finish=self.voiceTestFinished.emit,
        )

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
            self.clearWakeHint()
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
        self._start_voice_runtime_warmup()
        self.services.wake.start(self._emit_wake_detected, self._emit_wake_status_updated)
        self.summaryChanged.emit()
        self.statusChanged.emit()

    @Slot()
    def shutdown(self) -> None:
        self.services.wake.stop()

    def _deliver_transcribed_text(self, text: str) -> None:
        self._recording_hint = "Команда распознана. Передаю в обработку..."
        self.recordingHintChanged.emit()
        self.state.status = "Передаю команду в обработку"
        self.statusChanged.emit()
        self.services.voice.mark_wake_route_handoff()
        self.voiceTimingsChanged.emit()
        if self._chat_bridge is not None:
            self._chat_bridge.submitTranscribedText(text)

    def _push_voice_note(self, note: str) -> None:
        self._recording_hint = note
        self.recordingHintChanged.emit()
        lowered = note.casefold()
        if "не расслыш" in lowered or "not heard" in lowered:
            self.clearWakeHint()
            self.state.status = "Не расслышал"
        elif "микрофон" in lowered or "mic" in lowered:
            self.clearWakeHint()
            self.state.status = "Ошибка микрофона"
        elif "ошиб" in lowered or "error" in lowered or "stt" in lowered or "ключ" in lowered:
            self.clearWakeHint()
            self.state.status = "Ошибка распознавания"
        elif "останов" in lowered or "cancel" in lowered:
            self.clearWakeHint()
            self.state.status = "Запись остановлена"
        else:
            self.state.status = "Готов"
        self.statusChanged.emit()

    def _finalize_capture(self) -> None:
        self.recordingChanged.emit()
        if self.state.status not in {"Не расслышал", "Ошибка микрофона", "Ошибка распознавания", "Запись остановлена"}:
            self._recording_hint = "Ручной микрофон готов."
            self.recordingHintChanged.emit()
            self.state.status = "Готов"
        self.statusChanged.emit()
        if self.wakeWordEnabled:
            self.startWakeRuntime()

    def _emit_wake_detected(self, pre_roll: bytes) -> None:
        self.wakeDetected.emit(pre_roll)

    def _emit_wake_status_updated(self) -> None:
        self.wakeStatusUpdated.emit()

    def _handle_wake_detected(self, pre_roll: bytes) -> None:
        if self.services.voice.is_recording:
            return
        self._wake_hint = "Услышал «Джарвис». Подхватываю начало команды..."
        self.wakeHintChanged.emit()
        self.state.status = "Услышал «Джарвис»"
        self.statusChanged.emit()
        self.services.voice.set_wake_runtime_status(
            "capturing_command",
            ready=False,
            detail="Услышал «Джарвис». Подхватываю начало команды",
        )
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
        self.voiceTimingsChanged.emit()

    def _start_voice_runtime_warmup(self) -> None:
        with self._warmup_lock:
            if self._warmup_started:
                return
            self._warmup_started = True

        def _worker() -> None:
            wake_backend = getattr(self.services, "wake", None)
            voice_backend = getattr(self.services, "voice", None)
            try:
                if wake_backend is not None and hasattr(wake_backend, "warm_up_model"):
                    wake_backend.warm_up_model()
                if voice_backend is not None and hasattr(voice_backend, "warm_up_local_stt_backend"):
                    voice_backend.warm_up_local_stt_backend()
            finally:
                self.statusChanged.emit()
                self.voiceTimingsChanged.emit()

        threading.Thread(target=_worker, daemon=True).start()

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

    def _empty_voice_test(self, stage: str = "idle") -> dict[str, object]:
        return {
            "stage": stage,
            "heardText": "",
            "recognizedText": "",
            "intent": "",
            "command": "",
            "summary": "",
            "routeKind": "",
            "error": "",
            "commands": [],
            "steps": [],
        }

    def _handle_voice_test_text(self, text: str) -> None:
        heard = text.strip()
        normalized = self._strip_voice_test_wake_word(heard)
        route = self.services.command_router.preview(normalized, source="voice")
        execution = getattr(route, "execution_result", None)
        steps = []
        if execution is not None and getattr(execution, "steps", None):
            steps = [
                {
                    "title": str(step.title),
                    "status": str(step.status),
                    "detail": str(step.detail),
                    "kind": str(step.kind),
                }
                for step in execution.steps
            ]

        summary = route.assistant_lines[0] if route.assistant_lines else normalized
        intent = ""
        if execution is not None and getattr(execution, "steps", None):
            intent = str(execution.steps[0].kind)
        elif route.kind:
            intent = str(route.kind)

        stage = "understood_command"
        if route.kind == "ai" or any(step.get("status") == "needs_input" for step in steps):
            stage = "understood_text"

        self._voice_test = {
            "stage": stage,
            "heardText": heard,
            "recognizedText": normalized,
            "intent": intent,
            "command": summary,
            "summary": summary,
            "routeKind": route.kind,
            "error": "",
            "commands": list(route.commands),
            "steps": steps,
        }
        self._test_result = self._voice_test_summary()
        self.voiceTestChanged.emit()
        self.testResultChanged.emit()
        self.statusChanged.emit()

    def _handle_voice_test_note(self, note: str) -> None:
        clean = note.strip()
        stage = "error_stt"
        lowered = clean.casefold()
        if "микрофон" in lowered and ("не удалось" in lowered or "ошибка" in lowered):
            stage = "error_mic"
        elif "не удалось получить текст" in lowered or "не расслыш" in lowered:
            stage = "not_heard"
        elif "groq" in lowered or "ключ" in lowered or "stt" in lowered or "модель" in lowered:
            stage = "error_stt"

        self._voice_test = {
            **self._voice_test,
            "stage": stage,
            "error": clean,
            "summary": clean,
            "command": clean,
        }
        self._test_result = clean
        self.voiceTestChanged.emit()
        self.testResultChanged.emit()
        self.statusChanged.emit()

    def _finish_voice_test(self) -> None:
        if str(self._voice_test.get("stage", "idle")) == "listening":
            self._voice_test = {
                **self._voice_test,
                "stage": "not_heard",
                "error": "Не расслышал фразу.",
                "summary": "Не расслышал фразу.",
            }
            self._test_result = "Не расслышал фразу."
            self.voiceTestChanged.emit()
            self.testResultChanged.emit()
        self.recordingChanged.emit()
        self._recording_hint = "Ручной микрофон готов."
        self.recordingHintChanged.emit()
        self.state.status = "Готов"
        if self.wakeWordEnabled:
            self.startWakeRuntime()

    def _voice_test_summary(self) -> str:
        parts = []
        heard = str(self._voice_test.get("heardText", "")).strip()
        recognized = str(self._voice_test.get("recognizedText", "")).strip()
        command = str(self._voice_test.get("command", "")).strip()
        if heard:
            parts.append(f"Услышал: {heard}")
        if recognized and recognized != heard:
            parts.append(f"После очистки: {recognized}")
        intent = str(self._voice_test.get("intent", "")).strip()
        if intent:
            parts.append(f"Тип команды: {intent}")
        if command:
            parts.append(f"Что сделаю: {command}")
        error = str(self._voice_test.get("error", "")).strip()
        if error and not parts:
            return error
        return " | ".join(parts) if parts else "Проверка завершена."

    def _strip_voice_test_wake_word(self, text: str) -> str:
        normalizer = getattr(self.services.voice, "strip_wake_word", None)
        if callable(normalizer):
            return normalizer(text)
        return text.strip()

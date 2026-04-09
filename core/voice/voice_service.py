from __future__ import annotations

import importlib.util
import re
import threading
from typing import Callable

import sounddevice as sd

from core.routing.text_rules import WAKE_PREFIX_ALIASES, strip_leading_wake_prefix
from core.voice.audio_device_service import AudioDeviceService
from core.voice.speech_capture_service import CaptureConfig, SpeechCaptureService
from core.voice.stt_service import STTService
from core.voice.tts_service import TTSService
from core.voice.voice_models import SpeechCaptureResult, TranscriptionResult


class VoiceService:
    SAMPLE_RATE = 16_000
    CHANNELS = 1
    BLOCK_FRAMES = 1600
    MANUAL_MAX_SECONDS = 8.0
    SILENCE_SECONDS = 0.9
    WAKE_MAX_SECONDS = 4.4
    WAKE_SILENCE_SECONDS = 0.4
    WAKE_PRE_ROLL_GRACE_SECONDS = 0.35
    ENERGY_THRESHOLD = 160.0
    WAKE_FILLER_TOKENS = {
        "а",
        "э",
        "ээ",
        "эээ",
        "эм",
        "эмм",
        "эммм",
        "мм",
        "ммм",
        "ну",
        "ага",
        "угу",
        "да",
        "нет",
        "ой",
    }
    DEFAULT_INPUT_LABEL = "Системный микрофон"
    DEFAULT_OUTPUT_LABEL = "Системный вывод"
    DEFAULT_TTS_TEXT = "Я на связи."

    def __init__(self, settings_service) -> None:
        self.settings = settings_service
        self._manual_stop_event = threading.Event()
        self._manual_thread: threading.Thread | None = None
        self._recording = False
        self._wake_phase = "idle"
        self._wake_detail = "Слово активации не запущено"
        self._wake_ready = False
        self._audio_devices: AudioDeviceService | None = None

        self.capture_service = SpeechCaptureService(
            resolve_input_device=self._resolve_input_device,
            stop_event=self._manual_stop_event,
            config=CaptureConfig(
                sample_rate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                block_frames=self.BLOCK_FRAMES,
                max_seconds=self.MANUAL_MAX_SECONDS,
                silence_seconds=self.SILENCE_SECONDS,
                energy_threshold=self.ENERGY_THRESHOLD,
            ),
        )
        self.stt_service = STTService(self.settings)
        self.tts_service = TTSService(self.settings)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def audio_devices(self) -> AudioDeviceService:
        if self._audio_devices is None:
            self._audio_devices = AudioDeviceService(
                query_devices=lambda: sd.query_devices(),
                query_hostapis=lambda: sd.query_hostapis(),
                default_device_getter=lambda: sd.default.device,
            )
        return self._audio_devices

    @property
    def microphone_device_models(self):
        return self.audio_devices.microphone_models

    @property
    def output_device_models(self):
        return self.audio_devices.output_models

    @property
    def microphones(self):
        return self.audio_devices.microphones

    @property
    def output_devices(self):
        return self.audio_devices.output_devices

    def set_wake_runtime_status(self, phase: str, ready: bool = False, detail: str | None = None) -> None:
        normalized = {
            "waiting": "waiting_wake",
            "listening": "capturing_command",
        }.get(phase, phase)
        self._wake_phase = normalized
        self._wake_ready = ready
        if detail is not None:
            self._wake_detail = detail

    def wake_status_text(self) -> str:
        labels = {
            "preparing": "Готовлю слово активации",
            "waiting_wake": "Жду «Джарвис»",
            "capturing_command": self._wake_detail or "Подхватываю начало команды",
            "transcribing": self._wake_detail or "Распознаю команду",
            "routing": self._wake_detail or "Распознаю команду",
            "executing": self._wake_detail or "Выполняю",
            "not_heard": self._wake_detail or "Не расслышал",
            "error": self._wake_detail or "Ошибка слова активации",
            "no_key": "Нужен ключ Groq",
            "idle": self._wake_detail or "Слово активации не запущено",
        }
        return labels.get(self._wake_phase, self._wake_detail or "Готов")

    def command_status_text(self) -> str:
        engine = self.stt_service.engine()
        if engine in {"groq_whisper", "local_vosk"}:
            return self.stt_service.status_text()
        if self.stt_service._groq_key():
            return self.stt_service.status_text()
        return "Нужен ключ Groq"

    def model_status_text(self) -> str:
        engine = self.stt_service.engine()
        if engine in {"groq_whisper", "local_vosk"}:
            return "загружена" if self.stt_service.can_transcribe() else "не подключена"
        if self.stt_service._groq_key():
            return "загружена"
        return "не подключена"

    def summary(self) -> str:
        mode = self.settings.get("voice_mode", "balance")
        mode_label = {
            "private": "приватный",
            "balance": "баланс",
            "quality": "качество",
        }.get(mode, mode)
        style = self.settings.get("command_style", "one_shot")
        style_label = "одной фразой" if style == "one_shot" else "в два шага"
        return (
            f"Слово активации: {self.wake_status_text()}. "
            f"Распознавание речи: {self.command_status_text()}. "
            f"Режим: {mode_label}. Сценарий: {style_label}."
        )

    def runtime_status(self) -> dict[str, str]:
        return {
            "wakeWord": self.wake_status_text(),
            "command": self.command_status_text(),
            "ai": "Groq или резервный локальный режим",
            "model": self.model_status_text(),
            "tts": self.tts_status_text(),
        }

    def test_wake_word(self) -> str:
        if self._wake_phase == "waiting_wake" and self._wake_ready:
            return "Слово активации ждёт «Джарвис»."
        if self._wake_phase == "preparing":
            return "Слово активации ещё готовится."
        if self._wake_phase == "error":
            return self._wake_detail or "Ошибка слова активации."
        if self._wake_phase == "not_heard":
            return self._wake_detail or "Не расслышал команду после слова активации."
        return "Слово активации сейчас не запущено."

    def tts_status_text(self) -> str:
        return self.tts_service.status_text()

    def available_tts_engines(self) -> list[dict[str, object]]:
        return [
            {
                "key": engine.key,
                "title": engine.title,
                "note": engine.note,
                "supportsOutputDevice": engine.supports_output_device,
                "available": engine.available,
            }
            for engine in self.tts_service.available_engines()
        ]

    def available_tts_voices(self) -> list[str]:
        return self.tts_service.available_voices()

    def voice_response_enabled(self) -> bool:
        return self.tts_service.voice_response_enabled()

    def tts_engine(self) -> str:
        return self.tts_service.tts_engine()

    def can_route_tts_output(self) -> bool:
        return self.tts_service.can_route_output()

    def tts_voice_name(self) -> str:
        return self.tts_service.tts_voice_name()

    def tts_rate(self) -> int:
        return self.tts_service.tts_rate()

    def tts_volume(self) -> int:
        return self.tts_service.tts_volume()

    def speak(self, text: str, force: bool = False) -> str:
        return self.tts_service.speak(text, force=force).message

    def test_jarvis_voice(self) -> str:
        return self.tts_service.test_voice(self.DEFAULT_TTS_TEXT).message

    def start_manual_capture(
        self,
        on_text: Callable[[str], None] | None = None,
        on_note: Callable[[str], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> str:
        if self._recording:
            return "Запись уже идёт."

        self._manual_stop_event.clear()
        self._recording = True
        self._manual_thread = threading.Thread(
            target=self._manual_capture_worker,
            args=(on_text, on_note, on_finish),
            daemon=True,
        )
        self._manual_thread.start()
        return "Слушаю. Говорите один раз, запись остановится сама."

    def stop_manual_capture(self) -> str:
        if not self._recording and (self._manual_thread is None or not self._manual_thread.is_alive()):
            return ""

        self._manual_stop_event.set()
        return "Останавливаю запись..."

    def capture_after_wake(self, pre_roll: bytes) -> str:
        return self.capture_after_wake_result(pre_roll).text

    def capture_after_wake_result(self, pre_roll: bytes) -> TranscriptionResult:
        max_seconds, silence_seconds, energy_threshold, pre_roll_grace = self._wake_capture_tuning()
        wake_capture = SpeechCaptureService(
            resolve_input_device=self._resolve_input_device,
            stop_event=self._manual_stop_event,
            config=CaptureConfig(
                sample_rate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                block_frames=self.BLOCK_FRAMES,
                max_seconds=max_seconds,
                silence_seconds=silence_seconds,
                energy_threshold=energy_threshold,
                pre_roll_grace_seconds=pre_roll_grace,
            ),
        )
        capture = wake_capture.capture_until_silence(pre_roll=pre_roll)
        if not capture.ok:
            self._set_wake_error_from_capture(capture)
            return TranscriptionResult(status=capture.status, detail=capture.detail, engine="capture")

        self.set_wake_runtime_status("transcribing", ready=False, detail="Распознаю команду")
        transcription = self.stt_service.transcribe_pcm_bytes(capture.raw_audio)
        if transcription.ok:
            self.set_wake_runtime_status("routing", ready=False, detail="Распознаю команду")
            stripped_text, matched_prefix, has_tail = self._split_wake_prefix(transcription.text)
            if matched_prefix and not has_tail:
                detail = "Не расслышал команду"
                self.set_wake_runtime_status("not_heard", ready=False, detail=detail)
                return TranscriptionResult(status="no_speech", detail=detail, engine=transcription.engine)
            if self._looks_like_wake_garbage(stripped_text):
                detail = "Не расслышал команду"
                self.set_wake_runtime_status("not_heard", ready=False, detail=detail)
                return TranscriptionResult(status="no_speech", detail=detail, engine=transcription.engine)
            transcription = TranscriptionResult(
                status="ok",
                text=stripped_text,
                detail=transcription.detail,
                engine=transcription.engine,
            )
            return transcription

        if transcription.status == "no_speech":
            self.set_wake_runtime_status(
                "not_heard",
                ready=False,
                detail="Не расслышал команду",
            )
        else:
            self.set_wake_runtime_status("error", ready=False, detail=transcription.detail)
        return transcription

    def _manual_capture_worker(
        self,
        on_text: Callable[[str], None] | None,
        on_note: Callable[[str], None] | None,
        on_finish: Callable[[], None] | None,
    ) -> None:
        try:
            capture = self.capture_service.capture_until_silence()
            if not capture.ok:
                if on_note is not None:
                    on_note(self._capture_note_from_result(capture))
                return

            transcription = self.stt_service.transcribe_pcm_bytes(capture.raw_audio)
            if transcription.ok:
                if on_text is not None:
                    on_text(transcription.text)
            elif on_note is not None:
                on_note(self._stt_note_from_result(transcription))
        finally:
            self._recording = False
            self._manual_thread = None
            self._manual_stop_event.clear()
            if on_finish is not None:
                on_finish()

    def _capture_note_from_result(self, result: SpeechCaptureResult) -> str:
        if result.status == "mic_open_failed":
            return "Не удалось открыть микрофон. Проверьте выбранное устройство."
        if result.status == "cancelled":
            return "Запись остановлена."
        if result.status == "no_speech":
            return "Не удалось получить текст. Проверьте микрофон или ключ Groq."
        return result.detail or "Не удалось получить текст."

    def _stt_note_from_result(self, result: TranscriptionResult) -> str:
        if result.status == "stt_key_missing":
            return "Нужен ключ Groq."
        if result.status == "model_missing":
            return "Нужен ключ Groq или локальная модель распознавания."
        if result.status == "no_speech":
            return "Не удалось получить текст. Проверьте микрофон или ключ Groq."
        return result.detail or "Не удалось распознать речь."

    def _set_wake_error_from_capture(self, capture: SpeechCaptureResult) -> None:
        if capture.status == "mic_open_failed":
            self.set_wake_runtime_status("error", ready=False, detail="Не удалось открыть микрофон.")
        elif capture.status == "cancelled":
            self.set_wake_runtime_status("idle", ready=False, detail="Запись остановлена.")
        else:
            self.set_wake_runtime_status("not_heard", ready=False, detail=capture.detail or "Не расслышал команду.")

    def _resolve_input_device(self) -> int | None:
        selected = self.settings.get("microphone_name", self.DEFAULT_INPUT_LABEL)
        return self.audio_devices.resolve_input_device(str(selected))

    def _resolve_output_device(self) -> int | None:
        selected = self.settings.get("voice_output_name", self.DEFAULT_OUTPUT_LABEL)
        return self.audio_devices.resolve_output_device(str(selected))

    def normalize_microphone_selection(self, value: str) -> str:
        return self.audio_devices.normalize_microphone_selection(value)

    def normalize_output_selection(self, value: str) -> str:
        return self.audio_devices.normalize_output_selection(value)

    def _wake_capture_tuning(self) -> tuple[float, float, float, float]:
        mode = str(self.settings.get("voice_mode", "balance")).strip().casefold()
        command_style = str(self.settings.get("command_style", "one_shot")).strip().casefold()
        if mode == "quality":
            max_seconds, silence_seconds, energy_threshold, pre_roll_grace = 5.0, 0.55, 145.0, 0.4
        elif mode == "private":
            max_seconds, silence_seconds, energy_threshold, pre_roll_grace = 4.0, 0.45, 150.0, 0.3
        else:
            max_seconds, silence_seconds, energy_threshold, pre_roll_grace = (
                self.WAKE_MAX_SECONDS,
                self.WAKE_SILENCE_SECONDS,
                self.ENERGY_THRESHOLD,
                self.WAKE_PRE_ROLL_GRACE_SECONDS,
            )

        if command_style == "one_shot":
            max_seconds += 0.8
            silence_seconds += 0.12
        return max_seconds, silence_seconds, energy_threshold, pre_roll_grace

    def _capture_until_silence(
        self,
        pre_roll: bytes = b"",
        max_seconds: float = 4.5,
        silence_seconds: float = 0.9,
        energy_threshold: float = 160.0,
    ) -> bytes:
        custom = SpeechCaptureService(
            resolve_input_device=self._resolve_input_device,
            stop_event=self._manual_stop_event,
            config=CaptureConfig(
                sample_rate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                block_frames=self.BLOCK_FRAMES,
                max_seconds=max_seconds,
                silence_seconds=silence_seconds,
                energy_threshold=energy_threshold,
            ),
        )
        result = custom.capture_until_silence(pre_roll=pre_roll)
        return result.raw_audio if result.ok else b""

    def _transcribe_pcm_bytes(self, raw_bytes: bytes) -> str:
        result = self.stt_service.transcribe_pcm_bytes(raw_bytes)
        return result.text if result.ok else ""

    def _split_wake_prefix(self, text: str) -> tuple[str, bool, bool]:
        clean = text.strip()
        stripped = strip_leading_wake_prefix(clean)
        if not stripped:
            normalized = clean.casefold().strip(" ,.:;!?-")
            if normalized in WAKE_PREFIX_ALIASES:
                return "", True, False
            return "", False, False
        if stripped != clean:
            return stripped, True, True
        return clean, False, bool(clean)

    def _strip_wake_word(self, text: str) -> str:
        clean, _matched_prefix, has_tail = self._split_wake_prefix(text)
        return clean if has_tail else ""

    def strip_wake_word(self, text: str) -> str:
        return self._strip_wake_word(text)

    def _looks_like_wake_garbage(self, text: str) -> bool:
        clean = text.strip().casefold()
        if not clean:
            return True

        tokens = [token for token in re.split(r"[\s,.:;!?-]+", clean) if token]
        if not tokens:
            return True

        compact = "".join(tokens)
        wake_alias_compact = {alias.casefold().replace(" ", "") for alias in WAKE_PREFIX_ALIASES}
        if compact in wake_alias_compact:
            return True
        if all(token in self.WAKE_FILLER_TOKENS for token in tokens):
            return True
        if len(tokens) <= 2 and all(len(token) <= 2 for token in tokens):
            return True
        return False

    def _module_available(self, module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

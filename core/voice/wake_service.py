from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
import sys

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from core.routing.text_rules import STRICT_WAKE_ALIASES, normalize_text, strip_leading_wake_prefix


MODEL_DIR_NAME = "vosk-model-small-ru-0.22"


class WakeService:
    SAMPLE_RATE = 16_000
    BLOCK_FRAMES = 1600

    def __init__(self, settings_service, voice_service) -> None:
        self.settings = settings_service
        self.voice = voice_service
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            self.base_dir = Path(data_dir) / "models"
        else:
            base_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
            self.base_dir = base_root / "JarvisAi_Unity" / "models"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.user_model_path = self.base_dir / MODEL_DIR_NAME
        self.bundled_model_path = self._find_bundled_model_path()
        self.model_path = self.bundled_model_path if self.bundled_model_path.exists() else self.user_model_path
        self._callback = None
        self._status_callback = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._phase = "idle"
        self._detail = "Слово активации не запущено"
        self._buffer = deque(maxlen=18)
        self._last_detected_at = 0.0
        SetLogLevel(-1)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def phase(self) -> str:
        return self._phase

    def start(self, on_detected, on_status=None) -> str:
        self._callback = on_detected
        self._status_callback = on_status
        if self._thread and self._thread.is_alive():
            return self.status()
        if not self.model_path.exists():
            self._set_phase("error", "Локальная модель слова активации не загружена", ready=False)
            return self.status()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return "Готовлю слово активации"

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._phase != "error":
            self._set_phase("idle", "Слово активации не запущено", ready=False)
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def status(self) -> str:
        return self._detail

    def model_status(self) -> str:
        return "загружена" if self.model_path.exists() else "не загружена"

    def _run(self) -> None:
        try:
            self._set_phase("preparing", "Готовлю слово активации", ready=False)
            model = Model(str(self.model_path))
            recognizer = self._new_recognizer(model)

            audio_queue: queue.Queue[bytes] = queue.Queue()

            def callback(indata, frames, time_info, status):  # noqa: ARG001
                if status:
                    return
                audio_queue.put(bytes(indata))

            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_FRAMES,
                dtype="int16",
                device=self.voice._resolve_input_device(),
                channels=1,
                callback=callback,
            ):
                self._running = True
                self._set_phase("waiting_wake", "Жду «Джарвис»", ready=True)

                while not self._stop_event.is_set():
                    try:
                        data = audio_queue.get(timeout=0.3)
                    except queue.Empty:
                        continue

                    self._buffer.append(data)
                    if recognizer.AcceptWaveform(data):
                        detected = self._contains_wake(recognizer.Result())
                    else:
                        detected = self._contains_wake(recognizer.PartialResult(), partial=True)

                    if detected and time.time() - self._last_detected_at > 2.5:
                        self._last_detected_at = time.time()
                        pre_roll = b"".join(self._buffer)
                        self._buffer.clear()
                        self._set_phase("capturing_command", "Слушаю команду", ready=False)
                        self._running = False
                        if self._callback is not None:
                            self._callback(pre_roll)
                        return
        except Exception as exc:
            self._set_phase("error", f"Ошибка слова активации: {exc}", ready=False)
        finally:
            self._running = False
            if self._phase not in {"error", "transcribing", "routing", "executing"} and not self._stop_event.is_set():
                self._set_phase("idle", "Слово активации не запущено", ready=False)

    def _find_bundled_model_path(self) -> Path:
        candidates = []
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            candidates.append(Path(frozen_root) / "assets" / "models" / MODEL_DIR_NAME)
        candidates.append(Path(__file__).resolve().parents[2] / "assets" / "models" / MODEL_DIR_NAME)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[-1]

    def _new_recognizer(self, model: Model) -> KaldiRecognizer:
        grammar = [*STRICT_WAKE_ALIASES, "[unk]"]
        return KaldiRecognizer(model, self.SAMPLE_RATE, json.dumps(grammar, ensure_ascii=False))

    def _contains_wake(self, payload: str, partial: bool = False) -> bool:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False
        key = "partial" if partial else "text"
        text = normalize_text(str(data.get(key, "")))
        if not text:
            return False
        stripped = strip_leading_wake_prefix(text, aliases=STRICT_WAKE_ALIASES)
        return stripped != text or text.casefold().strip(" ,.:;!?-") in STRICT_WAKE_ALIASES

    def _set_phase(self, phase: str, detail: str, ready: bool) -> None:
        self._phase = phase
        self._detail = detail
        self.voice.set_wake_runtime_status(phase, ready=ready, detail=detail)
        self._emit_status()

    def _emit_status(self) -> None:
        if self._status_callback is not None:
            self._status_callback()

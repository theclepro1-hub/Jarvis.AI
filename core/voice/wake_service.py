from __future__ import annotations

import json
import os
import queue
import threading
import time
import zipfile
from collections import deque
from pathlib import Path
from urllib.request import urlopen

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel


MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
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
            self.base_dir = Path.home() / "AppData" / "Roaming" / "JarvisAi_Unity" / "models"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.base_dir / MODEL_DIR_NAME
        self._callback = None
        self._status_callback = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._buffer = deque(maxlen=18)
        self._last_detected_at = 0.0
        SetLogLevel(-1)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, on_detected, on_status=None) -> str:
        self._callback = on_detected
        self._status_callback = on_status
        if self._thread and self._thread.is_alive():
            return "Local wake runtime уже работает."
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return "Local wake runtime запускается."

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def status(self) -> str:
        if self._running:
            return "локально активно"
        if self.model_path.exists():
            return "локально готово"
        return "локальная модель не скачана"

    def _run(self) -> None:
        try:
            self.voice.set_wake_runtime_status("локальная модель подготавливается", False)
            self._emit_status()
            if not self.model_path.exists():
                self.voice.set_wake_runtime_status("скачиваю локальную модель", False)
                self._emit_status()
            self._ensure_model()
            if self._stop_event.is_set():
                return
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
                self.voice.set_wake_runtime_status("локально активно", True)
                self._emit_status()
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
                        self._running = False
                        if self._callback is not None:
                            self._callback(pre_roll)
                        return
        except Exception:
            self.voice.set_wake_runtime_status("local wake runtime недоступен", False)
            self._emit_status()
        finally:
            self._running = False

    def _ensure_model(self) -> None:
        if self.model_path.exists():
            return

        archive_path = self.base_dir / f"{MODEL_DIR_NAME}.zip"
        with urlopen(MODEL_URL, timeout=90) as response, archive_path.open("wb") as out:
            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                out.write(chunk)

        with zipfile.ZipFile(archive_path, "r") as zip_handle:
            zip_handle.extractall(self.base_dir)
        archive_path.unlink(missing_ok=True)

    def _new_recognizer(self, model: Model) -> KaldiRecognizer:
        return KaldiRecognizer(model, self.SAMPLE_RATE, '["джарвис", "[unk]"]')

    def _contains_wake(self, payload: str, partial: bool = False) -> bool:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False
        key = "partial" if partial else "text"
        text = str(data.get(key, "")).lower()
        return "джарвис" in text

    def _emit_status(self) -> None:
        if self._status_callback is not None:
            self._status_callback()

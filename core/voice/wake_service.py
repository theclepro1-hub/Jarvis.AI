from __future__ import annotations

import os
import queue
import sys
import threading
import time
from collections import deque
from pathlib import Path

import sounddevice as sd

from core.voice.openwakeword_runtime import (
    DEFAULT_OPENWAKEWORD_MODEL,
    OPENWAKEWORD_SAMPLE_RATE,
    OpenWakeWordRuntime,
)


class WakeService:
    SAMPLE_RATE = OPENWAKEWORD_SAMPLE_RATE
    BLOCK_FRAMES = 1280
    PRE_ROLL_FRAMES = 16
    HANDOFF_PHASES = {"capturing_command", "transcribing", "routing", "executing"}
    DETECTION_COOLDOWN_SECONDS = 1.1
    DEFAULT_THRESHOLD = 0.62
    DEFAULT_PATIENCE_FRAMES = 2
    MODEL_CACHE_DIR = "openwakeword"

    def __init__(self, settings_service, voice_service) -> None:
        self.settings = settings_service
        self.voice = voice_service
        self._callback = None
        self._status_callback = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._phase = "idle"
        self._detail = "Слово активации не запущено"
        self._buffer = deque(maxlen=self.PRE_ROLL_FRAMES)
        self._last_detected_at = 0.0
        self._runtime: OpenWakeWordRuntime | None = None
        self._consecutive_hits = 0

    @property
    def backend_name(self) -> str:
        return "openwakeword"

    @property
    def base_dir(self) -> Path:
        data_dir = str(os.environ.get("JARVIS_UNITY_DATA_DIR", "") or "").strip()
        if data_dir:
            return Path(data_dir) / "models" / self.MODEL_CACHE_DIR
        local_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
        return local_root / "JarvisAi_Unity" / "models" / self.MODEL_CACHE_DIR

    @property
    def user_model_path(self) -> Path:
        return self.base_dir

    @property
    def bundled_model_path(self) -> Path:
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            bundled = Path(frozen_root) / "assets" / "models" / self.MODEL_CACHE_DIR
            if bundled.exists():
                return bundled
        return self.base_dir

    @property
    def model_path(self) -> Path:
        model_source, model_name = self._wake_model_source()
        if model_source is not None:
            return model_source
        return self.base_dir / model_name

    @model_path.setter
    def model_path(self, value: Path) -> None:
        self.settings.set("wake_model_path", str(Path(value)))
        self._runtime = None

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

        runtime = self._wake_runtime()
        if not runtime.package_available():
            self._set_phase("error", "openWakeWord не установлен", ready=False)
            return self.status()
        if not runtime.has_model():
            self._set_phase("error", "Локальная wake-модель не найдена", ready=False)
            return self.status()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return "Готовлю слово активации"

    def stop(self) -> None:
        self._stop_event.set()
        cancel_pipeline = getattr(self.voice, "cancel_active_pipeline", None)
        if callable(cancel_pipeline):
            cancel_pipeline()
        self._running = False
        if self._phase != "error":
            self._set_phase("idle", "Слово активации не запущено", ready=False)
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def status(self) -> str:
        return self._detail

    def model_status(self) -> str:
        runtime = self._wake_runtime()
        if not runtime.package_available():
            return "не установлен"
        return "загружена" if runtime.has_model() else "не загружена"

    def warm_up_model(self) -> bool:
        runtime = self._wake_runtime()
        return runtime.load()

    def _run(self) -> None:
        try:
            self._set_phase("preparing", "Готовлю слово активации", ready=False)
            runtime = self._wake_runtime()
            if not runtime.load():
                if self._stop_event.is_set():
                    return
                detail = runtime.last_error or "Локальная wake-модель не готова"
                self._set_phase("error", detail, ready=False)
                return
            runtime.reset()

            audio_queue: queue.Queue[bytes] = queue.Queue()

            def callback(indata, frames, time_info, status):  # noqa: ARG001, ANN001
                if status or self._stop_event.is_set():
                    return
                audio_queue.put(bytes(indata))

            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_FRAMES,
                dtype="int16",
                device=self.voice._resolve_input_device(),  # noqa: SLF001
                channels=1,
                callback=callback,
            ):
                self._running = True
                self._consecutive_hits = 0
                self._set_phase("waiting_wake", "Жду «Джарвис»", ready=True)

                while not self._stop_event.is_set():
                    try:
                        data = audio_queue.get(timeout=0.3)
                    except queue.Empty:
                        continue

                    self._buffer.append(data)
                    prediction = runtime.predict(data)
                    if self._handle_prediction(prediction):
                        return
        except Exception as exc:
            self._set_phase("error", f"Ошибка слова активации: {exc}", ready=False)
        finally:
            self._running = False
            if not self._phase_in_handoff() and self._phase != "error" and not self._stop_event.is_set():
                self._set_phase("idle", "Слово активации не запущено", ready=False)

    def _handle_prediction(self, prediction: dict[str, float] | None) -> bool:
        if self._stop_event.is_set():
            return False

        score = self._prediction_score(prediction)
        if score < self._wake_threshold():
            self._consecutive_hits = 0
            return False

        self._consecutive_hits += 1
        if self._consecutive_hits < self._wake_patience_frames():
            return False

        now = time.time()
        if now - self._last_detected_at < self.DETECTION_COOLDOWN_SECONDS:
            self._consecutive_hits = 0
            return False

        self._last_detected_at = now
        self._consecutive_hits = 0
        pre_roll = b"".join(self._buffer)
        self._buffer.clear()
        self._set_phase("capturing_command", "Подхватываю начало команды", ready=False)
        self._running = False
        if self._callback is not None:
            self._callback(pre_roll)
        return True

    def _prediction_score(self, prediction: dict[str, float] | None) -> float:
        if not prediction:
            return 0.0
        _model_source, model_name = self._wake_model_source()
        normalized_target = model_name.replace(" ", "_").casefold()
        for key, value in prediction.items():
            normalized_key = str(key or "").replace(" ", "_").casefold()
            if normalized_key == normalized_target:
                return float(value)
        return max(float(value) for value in prediction.values()) if prediction else 0.0

    def _wake_runtime(self) -> OpenWakeWordRuntime:
        model_source, model_name = self._wake_model_source()
        if self._runtime is None:
            self._runtime = OpenWakeWordRuntime(model_source=model_source, model_name=model_name)
        return self._runtime

    def _wake_model_source(self) -> tuple[Path | None, str]:
        configured = self._configured_model_ref()
        model_name = configured or DEFAULT_OPENWAKEWORD_MODEL
        if not configured or not self._looks_like_model_path(configured):
            bundled = self._find_named_model_file(model_name)
            if bundled is not None:
                return bundled, bundled.stem
            return None, model_name

        candidate = Path(configured).expanduser()
        candidates = [candidate]
        if not candidate.is_absolute():
            candidates = [
                self.base_dir / candidate,
                self.bundled_model_path / candidate,
                candidate,
            ]
        for path in candidates:
            if path.exists():
                return path, path.stem
        return candidate if candidate.is_absolute() else self.base_dir / candidate, Path(configured).stem

    def _find_named_model_file(self, model_name: str) -> Path | None:
        normalized = str(model_name or "").replace(" ", "_").strip()
        if not normalized:
            return None
        candidates = [
            f"{normalized}.onnx",
            f"{normalized}.tflite",
            f"{normalized}_v0.1.onnx",
            f"{normalized}_v0.1.tflite",
        ]
        roots = (self.base_dir, self.bundled_model_path)
        for root in roots:
            for name in candidates:
                path = root / name
                if path.exists():
                    return path
        return None

    def _configured_model_ref(self) -> str:
        env_override = str(os.environ.get("JARVIS_UNITY_OPENWAKEWORD_MODEL", "") or "").strip()
        if env_override:
            return env_override
        for key in ("wake_model_path", "openwakeword_model"):
            value = str(self.settings.get(key, "") or "").strip()
            if value:
                return value
        return DEFAULT_OPENWAKEWORD_MODEL

    def _looks_like_model_path(self, value: str) -> bool:
        normalized = str(value or "").strip()
        if not normalized:
            return False
        path = Path(normalized)
        return (
            path.is_absolute()
            or path.suffix.casefold() in {".onnx", ".tflite"}
            or "/" in normalized
            or "\\" in normalized
            or normalized.startswith(".")
        )

    def _wake_threshold(self) -> float:
        raw = os.environ.get("JARVIS_UNITY_OPENWAKEWORD_THRESHOLD", "")
        if not raw:
            raw = str(self.settings.get("openwakeword_threshold", self.DEFAULT_THRESHOLD))
        try:
            return max(0.05, min(0.99, float(raw)))
        except (TypeError, ValueError):
            return self.DEFAULT_THRESHOLD

    def _wake_patience_frames(self) -> int:
        raw = os.environ.get("JARVIS_UNITY_OPENWAKEWORD_PATIENCE", "")
        if not raw:
            raw = str(self.settings.get("openwakeword_patience_frames", self.DEFAULT_PATIENCE_FRAMES))
        try:
            return max(1, min(8, int(raw)))
        except (TypeError, ValueError):
            return self.DEFAULT_PATIENCE_FRAMES

    def _set_phase(self, phase: str, detail: str, ready: bool) -> None:
        self._phase = phase
        self._detail = detail
        self.voice.set_wake_runtime_status(phase, ready=ready, detail=detail)
        self._emit_status()

    def _emit_status(self) -> None:
        if self._status_callback is not None:
            self._status_callback()

    def _phase_in_handoff(self) -> bool:
        return self._phase in self.HANDOFF_PHASES

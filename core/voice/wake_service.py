from __future__ import annotations

import json
import queue
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

from core.routing.text_rules import WAKE_PREFIX_ALIASES, normalize_text, strip_leading_wake_prefix


class WakeService:
    SAMPLE_RATE = 16_000
    BLOCK_FRAMES = 1600
    PRE_ROLL_FRAMES = 6
    HANDOFF_PHASES = {"capturing_command", "transcribing", "routing", "executing"}
    DETECTION_MAX_SECONDS = 2.4
    DETECTION_SILENCE_SECONDS = 0.22
    DETECTION_COOLDOWN_SECONDS = 2.2
    ENERGY_THRESHOLD = 96.0
    MIN_START_FRAMES = 2
    NOISE_FLOOR_FRAMES = 8
    NOISE_MARGIN = 16.0
    NOISE_RATIO = 1.18
    MAX_ADAPTIVE_THRESHOLD = 240.0
    END_THRESHOLD_RATIO = 0.72
    SPEECH_GATE_RATIO = 1.04

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

    @property
    def backend_name(self) -> str:
        return "local_faster_whisper"

    @property
    def base_dir(self) -> Path:
        return self.voice.stt_service.faster_whisper_download_root

    @property
    def user_model_path(self) -> Path:
        return self.voice.stt_service.faster_whisper_download_root

    @property
    def bundled_model_path(self) -> Path:
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            bundled = Path(frozen_root) / "assets" / "models" / "faster-whisper"
            if bundled.exists():
                return bundled
        return self.base_dir

    @property
    def model_path(self) -> Path:
        source = self._wake_model_source()
        if isinstance(source, Path):
            return source
        if isinstance(source, str) and source.strip():
            return self.base_dir / source.strip()
        return self.base_dir

    @model_path.setter
    def model_path(self, value: Path) -> None:
        self.voice.stt_service._local_model_override = Path(value)  # noqa: SLF001

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
        if self._wake_model_source() is None:
            self._set_phase("error", "Локальный wake backend не готов", ready=False)
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
        source = self._wake_model_source()
        if isinstance(source, Path):
            return "загружена"
        if isinstance(source, str) and source.strip():
            return "готова к загрузке"
        return "не загружена"

    def warm_up_model(self) -> bool:
        return self.voice.stt_service.warm_up_local_backend(cancel_event=self._stop_event)

    def _run(self) -> None:
        try:
            self._set_phase("preparing", "Готовлю слово активации", ready=False)
            if not self.warm_up_model():
                if self._stop_event.is_set():
                    return
                self._set_phase("error", "Локальный wake backend не готов", ready=False)
                return

            audio_queue: queue.Queue[bytes] = queue.Queue()

            def callback(indata, frames, time_info, status):  # noqa: ARG001, ANN001
                if status or self._stop_event.is_set():
                    return
                audio_queue.put(bytes(indata))

            detector = self._new_detector()
            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_FRAMES,
                dtype="int16",
                device=self.voice._resolve_input_device(),  # noqa: SLF001
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
                    burst = self._consume_detection_chunk(data, detector)
                    if burst is None:
                        continue
                    if self._handle_candidate_burst(burst):
                        return
        except Exception as exc:
            self._set_phase("error", f"Ошибка слова активации: {exc}", ready=False)
        finally:
            self._running = False
            if not self._phase_in_handoff() and self._phase != "error" and not self._stop_event.is_set():
                self._set_phase("idle", "Слово активации не запущено", ready=False)

    def _consume_detection_chunk(self, raw: bytes, detector: dict[str, Any]) -> bytes | None:
        frame_seconds = self.BLOCK_FRAMES / self.SAMPLE_RATE
        energy = self._chunk_energy(raw)

        if not detector["speech_started"]:
            if energy >= self._speech_gate(detector["start_threshold"]):
                detector["speech_frames"] += 1
                if detector["speech_frames"] >= self.MIN_START_FRAMES:
                    detector["speech_started"] = True
                    detector["silence_for"] = 0.0
                    detector["chunks"] = list(self._buffer)
                    detector["duration"] = len(detector["chunks"]) * frame_seconds
            else:
                detector["speech_frames"] = 0
                detector["noise_floor"].append(energy)
                detector["start_threshold"] = self._adaptive_threshold(detector["noise_floor"])
                detector["end_threshold"] = self._end_threshold(detector["start_threshold"])
            return None

        detector["chunks"].append(raw)
        detector["duration"] += frame_seconds
        if energy > detector["end_threshold"]:
            detector["silence_for"] = 0.0
        else:
            detector["silence_for"] += frame_seconds

        if detector["silence_for"] < self.DETECTION_SILENCE_SECONDS and detector["duration"] < self.DETECTION_MAX_SECONDS:
            return None

        burst = b"".join(detector["chunks"])
        self._reset_detector(detector)
        return burst if burst else None

    def _handle_candidate_burst(self, raw_bytes: bytes) -> bool:
        if not raw_bytes:
            return False
        self._set_phase("recognizing_command", "Распознаю слово активации", ready=False)
        result = self.voice.stt_service.transcribe_wake_window(raw_bytes, cancel_event=self._stop_event)
        if self._stop_event.is_set():
            return False
        if not result.ok or not self._contains_wake(result.text):
            self._set_phase("waiting_wake", "Жду «Джарвис»", ready=True)
            return False
        now = time.time()
        if now - self._last_detected_at < self.DETECTION_COOLDOWN_SECONDS:
            self._set_phase("waiting_wake", "Жду «Джарвис»", ready=True)
            return False
        self._last_detected_at = now
        self._buffer.clear()
        self._set_phase("capturing_command", "Подхватываю начало команды", ready=False)
        self._running = False
        if self._callback is not None:
            self._callback(raw_bytes)
        return True

    def _wake_model_source(self) -> str | Path | None:
        return self.voice.stt_service._resolve_local_faster_whisper_source()  # noqa: SLF001

    def _contains_wake(self, payload: str, partial: bool = False) -> bool:
        text = self._payload_text(payload, partial=partial)
        if not text:
            return False
        stripped = strip_leading_wake_prefix(text, aliases=WAKE_PREFIX_ALIASES)
        normalized = text.casefold().strip(" ,.:;!?-")
        return stripped != text or normalized in WAKE_PREFIX_ALIASES

    def _payload_text(self, payload: str, *, partial: bool) -> str:
        candidate = str(payload or "").strip()
        if not candidate:
            return ""
        if candidate[:1] == "{":
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                key = "partial" if partial else "text"
                candidate = str(data.get(key) or data.get("text") or data.get("partial") or "")
        return normalize_text(candidate)

    def _new_detector(self) -> dict[str, Any]:
        return {
            "speech_started": False,
            "speech_frames": 0,
            "silence_for": 0.0,
            "noise_floor": deque(maxlen=max(1, self.NOISE_FLOOR_FRAMES)),
            "start_threshold": self.ENERGY_THRESHOLD,
            "end_threshold": self._end_threshold(self.ENERGY_THRESHOLD),
            "chunks": [],
            "duration": 0.0,
        }

    def _reset_detector(self, detector: dict[str, Any]) -> None:
        detector["speech_started"] = False
        detector["speech_frames"] = 0
        detector["silence_for"] = 0.0
        detector["noise_floor"].clear()
        detector["start_threshold"] = self.ENERGY_THRESHOLD
        detector["end_threshold"] = self._end_threshold(self.ENERGY_THRESHOLD)
        detector["chunks"] = []
        detector["duration"] = 0.0

    def _chunk_energy(self, raw_bytes: bytes) -> float:
        if not raw_bytes:
            return 0.0
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples * samples)))

    def _adaptive_threshold(self, noise_floor: deque[float]) -> float:
        if not noise_floor:
            return self.ENERGY_THRESHOLD
        ambient = float(np.percentile(np.asarray(noise_floor, dtype=np.float32), 75))
        adaptive = max(
            self.ENERGY_THRESHOLD,
            ambient + self.NOISE_MARGIN,
            ambient * self.NOISE_RATIO,
        )
        return min(self.MAX_ADAPTIVE_THRESHOLD, adaptive)

    def _end_threshold(self, start_threshold: float) -> float:
        return max(
            self.ENERGY_THRESHOLD * self.END_THRESHOLD_RATIO,
            start_threshold * self.END_THRESHOLD_RATIO,
        )

    def _speech_gate(self, start_threshold: float) -> float:
        return max(
            start_threshold,
            self.ENERGY_THRESHOLD * self.SPEECH_GATE_RATIO,
        )

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

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np
import sounddevice as sd

from core.voice.voice_models import SpeechCaptureResult


@dataclass(frozen=True)
class CaptureConfig:
    sample_rate: int = 16_000
    channels: int = 1
    block_frames: int = 1600
    max_seconds: float = 4.5
    silence_seconds: float = 0.9
    energy_threshold: float = 160.0
    pre_roll_grace_seconds: float = 0.0
    min_start_frames: int = 2
    noise_floor_frames: int = 6
    noise_margin: float = 28.0
    noise_ratio: float = 1.18
    max_adaptive_threshold: float = 270.0
    end_threshold_ratio: float = 0.72
    speech_gate_ratio: float = 1.22


class SpeechCaptureService:
    def __init__(
        self,
        resolve_input_device: Callable[[], int | None],
        stop_event: threading.Event | None = None,
        config: CaptureConfig | None = None,
    ) -> None:
        self._resolve_input_device = resolve_input_device
        self._stop_event = stop_event or threading.Event()
        self._config = config or CaptureConfig()

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

    def capture_until_silence(self, pre_roll: bytes = b"") -> SpeechCaptureResult:
        chunks: list[bytes] = [pre_roll] if pre_roll else []
        speech_started = bool(pre_roll)
        silence_for = 0.0
        frame_seconds = self._config.block_frames / self._config.sample_rate
        grace_for = self._config.pre_roll_grace_seconds if pre_roll else 0.0
        max_iterations = int(self._config.max_seconds * self._config.sample_rate / self._config.block_frames)
        start_threshold = self._config.energy_threshold
        end_threshold = self._end_threshold(start_threshold)
        speech_frames = 0
        noise_floor: deque[float] = deque(maxlen=max(1, self._config.noise_floor_frames))

        try:
            with sd.RawInputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="int16",
                device=self._resolve_input_device(),
                blocksize=self._config.block_frames,
            ) as stream:
                for _ in range(max_iterations):
                    if self._stop_event.is_set():
                        return SpeechCaptureResult(
                            status="cancelled",
                            detail="Запись остановлена пользователем.",
                            raw_audio=b"".join(chunks),
                            speech_started=speech_started,
                        )

                    data, _overflowed = stream.read(self._config.block_frames)
                    raw = bytes(data)
                    chunks.append(raw)

                    energy = self._chunk_energy(raw)
                    if not speech_started:
                        if energy >= self._speech_gate(start_threshold):
                            speech_frames += 1
                            if speech_frames >= max(1, self._config.min_start_frames):
                                speech_started = True
                                silence_for = 0.0
                                grace_for = 0.0
                        else:
                            speech_frames = 0
                            noise_floor.append(energy)
                            start_threshold = self._adaptive_threshold(noise_floor)
                            end_threshold = self._end_threshold(start_threshold)
                    elif energy > end_threshold:
                        silence_for = 0.0
                        grace_for = 0.0
                    elif speech_started:
                        if grace_for > 0.0:
                            grace_for = max(0.0, grace_for - frame_seconds)
                            continue
                        silence_for += frame_seconds
                        if silence_for >= self._config.silence_seconds:
                            break
        except Exception as exc:
            return SpeechCaptureResult(status="mic_open_failed", detail=f"Не удалось открыть микрофон: {exc}")

        if not speech_started:
            return SpeechCaptureResult(status="no_speech", detail="Не удалось распознать речь.")

        raw_audio = b"".join(chunks)
        if not raw_audio:
            return SpeechCaptureResult(status="no_speech", detail="Не удалось распознать речь.")

        return SpeechCaptureResult(
            status="ok",
            detail="Запись получена.",
            raw_audio=raw_audio,
            speech_started=True,
            duration_seconds=len(raw_audio) / 2 / self._config.sample_rate,
        )

    def _chunk_energy(self, raw_bytes: bytes) -> float:
        if not raw_bytes:
            return 0.0
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples * samples)))

    def _adaptive_threshold(self, noise_floor: deque[float]) -> float:
        if not noise_floor:
            return self._config.energy_threshold
        ambient = float(np.percentile(np.asarray(noise_floor, dtype=np.float32), 75))
        adaptive = max(
            self._config.energy_threshold,
            ambient + self._config.noise_margin,
            ambient * self._config.noise_ratio,
        )
        return min(self._config.max_adaptive_threshold, adaptive)

    def _end_threshold(self, start_threshold: float) -> float:
        return max(
            self._config.energy_threshold * self._config.end_threshold_ratio,
            start_threshold * self._config.end_threshold_ratio,
        )

    def _speech_gate(self, start_threshold: float) -> float:
        return max(
            start_threshold,
            self._config.energy_threshold * self._config.speech_gate_ratio,
        )

from __future__ import annotations

import threading
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
        speech_started = bool(pre_roll and self._chunk_energy(pre_roll) > self._config.energy_threshold)
        silence_for = 0.0
        frame_seconds = self._config.block_frames / self._config.sample_rate
        grace_for = self._config.pre_roll_grace_seconds if pre_roll else 0.0
        max_iterations = int(self._config.max_seconds * self._config.sample_rate / self._config.block_frames)

        try:
            with sd.RawInputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="int16",
                device=self._resolve_input_device(),
                blocksize=self._config.block_frames,
                latency="low",
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
                    if energy > self._config.energy_threshold:
                        speech_started = True
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

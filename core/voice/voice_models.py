from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AudioEndpoint:
    id: str
    name: str
    raw_name: str
    index: int | None
    channels: int
    isDefault: bool
    hostapi: str


@dataclass(frozen=True)
class AudioDevice:
    id: str
    name: str
    kind: str
    hostapi: str
    channels: int
    isDefault: bool
    isUsable: bool
    roles: tuple[str, ...] = field(default_factory=tuple)
    inputEndpoints: tuple[AudioEndpoint, ...] = field(default_factory=tuple)
    outputEndpoints: tuple[AudioEndpoint, ...] = field(default_factory=tuple)
    preferredInputEndpointId: str = ""
    preferredOutputEndpointId: str = ""

    @property
    def displayName(self) -> str:
        return self.name

    def as_qml(self) -> dict[str, str | int | bool]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "hostapi": self.hostapi,
            "channels": self.channels,
            "isDefault": self.isDefault,
            "isUsable": self.isUsable,
        }

    def as_grouped_qml(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "displayName": self.displayName,
            "kind": self.kind,
            "hostapi": self.hostapi,
            "channels": self.channels,
            "isDefault": self.isDefault,
            "isUsable": self.isUsable,
            "roles": list(self.roles),
            "inputEndpoints": [
                {
                    "id": endpoint.id,
                    "name": endpoint.name,
                    "rawName": endpoint.raw_name,
                    "index": endpoint.index,
                    "channels": endpoint.channels,
                    "isDefault": endpoint.isDefault,
                    "hostapi": endpoint.hostapi,
                }
                for endpoint in self.inputEndpoints
            ],
            "outputEndpoints": [
                {
                    "id": endpoint.id,
                    "name": endpoint.name,
                    "rawName": endpoint.raw_name,
                    "index": endpoint.index,
                    "channels": endpoint.channels,
                    "isDefault": endpoint.isDefault,
                    "hostapi": endpoint.hostapi,
                }
                for endpoint in self.outputEndpoints
            ],
            "preferredInputEndpointId": self.preferredInputEndpointId,
            "preferredOutputEndpointId": self.preferredOutputEndpointId,
        }


@dataclass(frozen=True)
class SpeechCaptureResult:
    status: str
    detail: str = ""
    raw_audio: bytes = b""
    speech_started: bool = False
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class TranscriptionResult:
    status: str
    text: str = ""
    detail: str = ""
    engine: str = ""
    backend_trace: tuple[str, ...] = field(default_factory=tuple)
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class TTSResult:
    status: str
    message: str
    engine: str
    available: bool
    supports_output_device: bool

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class WakeSessionMetrics:
    session_id: str = ""
    phase: str = "idle"
    detail: str = ""
    wake_backend: str = ""
    stt_backend: str = ""
    backend_trace: tuple[str, ...] = field(default_factory=tuple)
    detected_at: float = 0.0
    capture_started_at: float = 0.0
    capture_finished_at: float = 0.0
    stt_started_at: float = 0.0
    stt_finished_at: float = 0.0
    route_handoff_at: float = 0.0
    pre_roll_bytes: int = 0
    captured_audio_bytes: int = 0
    captured_audio_seconds: float = 0.0
    transcript: str = ""
    final_status: str = ""
    failure_detail: str = ""

    def _diff_ms(self, started_at: float, finished_at: float) -> float:
        if started_at <= 0.0 or finished_at <= 0.0 or finished_at < started_at:
            return 0.0
        return round((finished_at - started_at) * 1000.0, 1)

    @property
    def wake_to_capture_ms(self) -> float:
        return self._diff_ms(self.detected_at, self.capture_started_at)

    @property
    def capture_ms(self) -> float:
        measured = self._diff_ms(self.capture_started_at, self.capture_finished_at)
        if measured > 0.0:
            return measured
        if self.captured_audio_seconds > 0.0:
            return round(self.captured_audio_seconds * 1000.0, 1)
        return 0.0

    @property
    def stt_ms(self) -> float:
        return self._diff_ms(self.stt_started_at, self.stt_finished_at)

    @property
    def stt_to_route_ms(self) -> float:
        return self._diff_ms(self.stt_finished_at, self.route_handoff_at)

    @property
    def total_ms(self) -> float:
        end_at = self.route_handoff_at or self.stt_finished_at or self.capture_finished_at
        return self._diff_ms(self.detected_at, end_at)

    @property
    def pre_roll_ms(self) -> float:
        if self.pre_roll_bytes <= 0:
            return 0.0
        return round(self.pre_roll_bytes / 2 / 16_000 * 1000.0, 1)

    def as_dict(self) -> dict[str, str | float | bool]:
        backend_trace = " -> ".join(self.backend_trace)
        return {
            "sessionId": self.session_id,
            "phase": self.phase,
            "detail": self.detail,
            "wakeBackend": self.wake_backend,
            "sttBackend": self.stt_backend,
            "backendTrace": backend_trace,
            "wakeToCaptureMs": self.wake_to_capture_ms,
            "captureMs": self.capture_ms,
            "sttMs": self.stt_ms,
            "sttToRouteMs": self.stt_to_route_ms,
            "totalMs": self.total_ms,
            "preRollMs": self.pre_roll_ms,
            "capturedAudioMs": round(self.captured_audio_seconds * 1000.0, 1) if self.captured_audio_seconds > 0 else 0.0,
            "transcript": self.transcript,
            "finalStatus": self.final_status,
            "failureDetail": self.failure_detail,
            "routeHookSeen": self.route_handoff_at > 0.0,
        }

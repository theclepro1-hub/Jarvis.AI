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

from __future__ import annotations

import array
import math
import shutil
import warnings
from contextlib import contextmanager
from typing import Dict, Iterable


FFMPEG_RUNTIME_TOOLS = ("ffmpeg", "ffprobe", "ffplay")
COMPRESSED_AUDIO_TOOLS = ("ffmpeg", "ffprobe", "avconv", "avprobe")


def _tool_status(names: Iterable[str]) -> Dict[str, str]:
    return {str(name): str(shutil.which(str(name)) or "").strip() for name in names}


def audio_rms_int16(raw: bytes) -> int:
    data = bytes(raw or b"")
    if len(data) < 2:
        return 0
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return 0
    try:
        samples = array.array("h")
        samples.frombytes(data[:usable])
    except Exception:
        return 0
    if not samples:
        return 0
    total = 0
    for sample in samples:
        total += int(sample) * int(sample)
    return int(math.sqrt(total / len(samples)))


def ffmpeg_runtime_status() -> Dict[str, object]:
    tools = _tool_status(FFMPEG_RUNTIME_TOOLS)
    found = {name: path for name, path in tools.items() if path}
    return {
        "tools": tools,
        "found": found,
        "has_ffmpeg": bool(tools.get("ffmpeg")),
        "has_ffprobe": bool(tools.get("ffprobe")),
        "has_ffplay": bool(tools.get("ffplay")),
    }


def compressed_audio_decoder_status() -> Dict[str, object]:
    tools = _tool_status(COMPRESSED_AUDIO_TOOLS)
    found = {name: path for name, path in tools.items() if path}
    return {
        "tools": tools,
        "found": found,
        "available": bool(found),
    }


def compressed_audio_decoder_available() -> bool:
    return bool(compressed_audio_decoder_status().get("available"))


def describe_ffmpeg_runtime(status: Dict[str, object] | None = None) -> str:
    info = status or ffmpeg_runtime_status()
    found = dict(info.get("found") or {})
    if not found:
        return "ffmpeg не найден"
    labels = []
    for tool in FFMPEG_RUNTIME_TOOLS:
        if found.get(tool):
            labels.append(tool)
    return ", ".join(labels)


@contextmanager
def suppress_pydub_ffmpeg_warnings():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work",
            category=RuntimeWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Couldn't find ffprobe or avprobe - defaulting to ffprobe, but may not work",
            category=RuntimeWarning,
        )
        yield


__all__ = [
    "COMPRESSED_AUDIO_TOOLS",
    "FFMPEG_RUNTIME_TOOLS",
    "audio_rms_int16",
    "compressed_audio_decoder_available",
    "compressed_audio_decoder_status",
    "describe_ffmpeg_runtime",
    "ffmpeg_runtime_status",
    "suppress_pydub_ffmpeg_warnings",
]

import struct

import jarvis_ai.audio_runtime as audio_runtime


def test_audio_rms_int16_handles_empty_bytes():
    assert audio_runtime.audio_rms_int16(b"") == 0


def test_audio_rms_int16_reads_pcm_signal():
    raw = struct.pack("<hhhh", 0, 1000, -1000, 1000)
    value = audio_runtime.audio_rms_int16(raw)
    assert 850 <= value <= 900


def test_ffmpeg_runtime_status_reports_partial_install(monkeypatch):
    known = {
        "ffmpeg": "C:/tools/ffmpeg.exe",
        "ffprobe": "",
        "ffplay": "",
    }
    monkeypatch.setattr(audio_runtime.shutil, "which", lambda name: known.get(name, ""))

    status = audio_runtime.ffmpeg_runtime_status()

    assert status["has_ffmpeg"] is True
    assert status["has_ffprobe"] is False
    assert status["has_ffplay"] is False
    assert audio_runtime.describe_ffmpeg_runtime(status) == "ffmpeg"

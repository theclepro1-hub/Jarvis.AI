from __future__ import annotations

import sys
import types
from array import array

import numpy as np

from core.voice.openwakeword_runtime import OpenWakeWordRuntime


def _pcm16_frame(value: int, frames: int = 1600) -> bytes:
    return array("h", [value] * frames).tobytes()


def test_openwakeword_runtime_is_safe_without_package(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("core.voice.openwakeword_runtime.importlib.util.find_spec", lambda _name: None)

    runtime = OpenWakeWordRuntime(tmp_path / "model.onnx")

    assert runtime.package_available() is False
    assert runtime.has_model() is False
    assert runtime.load() is False
    assert runtime.predict(_pcm16_frame(0)) is None
    assert list(runtime.predict_stream([_pcm16_frame(0)])) == []


def test_openwakeword_runtime_is_safe_without_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("core.voice.openwakeword_runtime.importlib.util.find_spec", lambda _name: object())

    runtime = OpenWakeWordRuntime(tmp_path / "missing.onnx")

    assert runtime.package_available() is True
    assert runtime.has_model() is False
    assert runtime.load() is False
    assert "model is unavailable" in runtime.last_error


def test_openwakeword_runtime_loads_and_streams_pcm16_frames(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("core.voice.openwakeword_runtime.importlib.util.find_spec", lambda _name: object())

    model_path = tmp_path / "wakeword.onnx"
    model_path.write_bytes(b"fake")
    captured: dict[str, object] = {}

    class FakeModel:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured["init"] = kwargs
            captured["frames"] = []

        def predict(self, audio):  # noqa: ANN001
            assert isinstance(audio, np.ndarray)
            assert audio.dtype == np.int16
            captured["frames"].append(audio.copy())
            return {"jarvis": float(int(np.max(np.abs(audio)))) / 32768.0}

    fake_module = types.ModuleType("openwakeword")
    fake_module.Model = FakeModel
    monkeypatch.setitem(sys.modules, "openwakeword", fake_module)

    runtime = OpenWakeWordRuntime(model_path)

    assert runtime.load() is True
    assert captured["init"]["wakeword_models"] == [str(model_path)]

    first = runtime.predict(_pcm16_frame(1024))
    stream = list(runtime.predict_stream([_pcm16_frame(2048), _pcm16_frame(0)]))

    assert first == {"jarvis": 0.03125}
    assert stream == [{"jarvis": 0.0625}, {"jarvis": 0.0}]
    assert len(captured["frames"]) == 3


def test_openwakeword_runtime_can_load_builtin_model_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("core.voice.openwakeword_runtime.importlib.util.find_spec", lambda _name: object())

    builtin_model = tmp_path / "hey_jarvis_v0.1.onnx"
    builtin_model.write_bytes(b"fake")
    captured: dict[str, object] = {}

    class FakeModel:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured["init"] = kwargs

        def predict(self, _audio):  # noqa: ANN001
            return {"hey_jarvis": 0.75}

    fake_module = types.ModuleType("openwakeword")
    fake_module.Model = FakeModel
    fake_module.MODELS = {"hey_jarvis": {"model_path": str(builtin_model)}}
    fake_module.get_pretrained_model_paths = lambda _framework: [str(builtin_model)]
    monkeypatch.setitem(sys.modules, "openwakeword", fake_module)

    runtime = OpenWakeWordRuntime(model_name="hey_jarvis")

    assert runtime.has_model() is True
    assert runtime.load() is True
    assert captured["init"]["wakeword_models"] == ["hey_jarvis"]
    assert captured["init"]["inference_framework"] == "onnx"

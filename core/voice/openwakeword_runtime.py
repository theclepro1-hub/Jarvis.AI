from __future__ import annotations

import importlib
import importlib.util
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np


OPENWAKEWORD_SAMPLE_RATE = 16_000
PCM16_SAMPLE_WIDTH_BYTES = 2
DEFAULT_OPENWAKEWORD_MODEL = "hey_jarvis"


def _existing_model_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    resolved = Path(path)
    if resolved.is_file():
        return resolved
    if resolved.is_dir():
        for child in resolved.iterdir():
            if child.is_file():
                return resolved
    return None


def _coerce_pcm16_frame(frame: bytes | bytearray | memoryview | np.ndarray | Iterable[int]) -> np.ndarray:
    if isinstance(frame, np.ndarray):
        array = frame
    elif isinstance(frame, (bytes, bytearray, memoryview)):
        array = np.frombuffer(frame, dtype=np.int16)
    else:
        array = np.asarray(list(frame), dtype=np.int16)

    if array.size == 0:
        return np.asarray([], dtype=np.int16)
    if array.dtype != np.int16:
        array = array.astype(np.int16, copy=False)
    return np.ascontiguousarray(array.reshape(-1))


def _normalize_prediction(result: Any) -> dict[str, float] | None:
    if result is None:
        return None
    if isinstance(result, dict):
        normalized: dict[str, float] = {}
        for key, value in result.items():
            try:
                normalized[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return normalized or None
    items = getattr(result, "items", None)
    if callable(items):
        try:
            return _normalize_prediction(dict(result))
        except Exception:
            return None
    return None


@dataclass(slots=True)
class OpenWakeWordRuntime:
    model_source: str | Path | None = None
    model_name: str = DEFAULT_OPENWAKEWORD_MODEL
    _model: Any = field(init=False, default=None, repr=False)
    _load_lock: threading.Lock = field(init=False, repr=False)
    _last_error: str = field(init=False, default="", repr=False)

    def __post_init__(self) -> None:
        self._load_lock = threading.Lock()

    @property
    def backend_name(self) -> str:
        return "openwakeword"

    @property
    def last_error(self) -> str:
        return self._last_error

    def package_available(self) -> bool:
        return importlib.util.find_spec("openwakeword") is not None

    def model_path(self) -> Path | None:
        if self.model_source is None:
            return None
        return Path(self.model_source)

    def has_model(self) -> bool:
        if _existing_model_path(self.model_path()) is not None:
            return True
        return self._pretrained_model_available()

    def load(self) -> bool:
        if self._model is not None:
            return True

        with self._load_lock:
            if self._model is not None:
                return True
            if not self.package_available():
                self._last_error = "openwakeword package is unavailable"
                return False

            model_path = _existing_model_path(self.model_path())
            wakeword_models = [str(model_path)] if model_path is not None else [self.model_name]
            model_kwargs: dict[str, object] = {
                "wakeword_models": wakeword_models,
                "inference_framework": "onnx",
            }
            if model_path is not None:
                feature_kwargs = self._feature_model_kwargs(model_path.parent)
                model_kwargs.update(feature_kwargs)
            if model_path is None and not self._pretrained_model_available():
                self._last_error = "openwakeword model is unavailable"
                return False

            try:
                module = importlib.import_module("openwakeword")
            except Exception as exc:  # pragma: no cover - defensive
                self._last_error = f"openwakeword import failed: {exc}"
                return False

            factory = getattr(module, "Model", None)
            if factory is None:
                try:
                    module = importlib.import_module("openwakeword.model")
                except Exception as exc:  # pragma: no cover - defensive
                    self._last_error = f"openwakeword Model class is unavailable: {exc}"
                    return False
                factory = getattr(module, "Model", None)
                if factory is None:
                    self._last_error = "openwakeword Model class is unavailable"
                    return False

            for kwargs in (
                model_kwargs,
                {"wakeword_models": wakeword_models},
                {"model_paths": wakeword_models},
            ):
                try:
                    self._model = factory(**kwargs)
                    self._last_error = ""
                    return True
                except TypeError:
                    continue
                except Exception as exc:
                    self._last_error = f"openwakeword load failed: {exc}"
                    return False

            try:
                self._model = factory(wakeword_models)
                self._last_error = ""
                return True
            except Exception as exc:
                self._last_error = f"openwakeword load failed: {exc}"
                return False

    def unload(self) -> None:
        with self._load_lock:
            self._model = None

    def predict(self, frame: bytes | bytearray | memoryview | np.ndarray | Iterable[int]) -> dict[str, float] | None:
        if not self.load():
            return None
        audio = _coerce_pcm16_frame(frame)
        if audio.size == 0:
            return None
        try:
            result = self._model.predict(audio)
        except Exception as exc:
            self._last_error = f"openwakeword predict failed: {exc}"
            return None
        return _normalize_prediction(result)

    def predict_stream(
        self,
        frames: Iterable[bytes | bytearray | memoryview | np.ndarray | Iterable[int]],
    ) -> Iterator[dict[str, float]]:
        if not self.load():
            return
        for frame in frames:
            result = self.predict(frame)
            if result is not None:
                yield result

    def reset(self) -> None:
        if self._model is None:
            return
        reset = getattr(self._model, "reset", None)
        if callable(reset):
            try:
                reset()
            except Exception:
                return

    def _feature_model_kwargs(self, model_dir: Path) -> dict[str, str]:
        melspec = model_dir / "melspectrogram.onnx"
        embedding = model_dir / "embedding_model.onnx"
        if not melspec.exists() or not embedding.exists():
            return {}
        return {
            "melspec_model_path": str(melspec),
            "embedding_model_path": str(embedding),
        }

    def _pretrained_model_available(self) -> bool:
        if self.model_source not in {None, ""}:
            return False
        if not self.package_available():
            return False
        try:
            module = importlib.import_module("openwakeword")
        except Exception:
            return False
        models = getattr(module, "MODELS", {}) or {}
        if self.model_name not in models:
            return False
        try:
            paths = list(module.get_pretrained_model_paths("onnx"))
        except Exception:
            paths = []
        normalized = self.model_name.replace(" ", "_")
        return any(normalized in Path(path).name and Path(path).exists() for path in paths)

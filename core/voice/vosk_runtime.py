from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vosk import KaldiRecognizer, Model


_MODEL_CACHE: dict[str, Model] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def _cache_key(path: Path) -> str:
    return str(path.expanduser().resolve())


def load_vosk_model(path: Path) -> Model:
    from vosk import Model

    key = _cache_key(path)
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = Model(key)
            _MODEL_CACHE[key] = model
        return model


def new_vosk_recognizer(path: Path, sample_rate: int, grammar: list[str] | None = None) -> KaldiRecognizer:
    from vosk import KaldiRecognizer

    model = load_vosk_model(path)
    if grammar:
        return KaldiRecognizer(model, sample_rate, json.dumps(grammar, ensure_ascii=False))
    return KaldiRecognizer(model, sample_rate)


def clear_vosk_model_cache() -> None:
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()

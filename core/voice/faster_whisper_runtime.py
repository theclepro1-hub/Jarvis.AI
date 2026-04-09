from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any


_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE: dict[tuple[str, str, str, str, int], Any] = {}


def clear_faster_whisper_model_cache() -> None:
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def load_faster_whisper_model(
    model_ref: str,
    download_root: Path,
    *,
    device: str = "cpu",
    compute_type: str = "int8",
    cpu_threads: int | None = None,
) -> Any:
    from faster_whisper import WhisperModel

    threads = max(1, cpu_threads or min(8, os.cpu_count() or 1))
    cache_key = (
        str(model_ref).strip(),
        str(device).strip(),
        str(compute_type).strip(),
        str(download_root.resolve()),
        threads,
    )

    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached

        download_root.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(
            model_ref,
            device=device,
            compute_type=compute_type,
            cpu_threads=threads,
            download_root=str(download_root),
        )
        _MODEL_CACHE[cache_key] = model
        return model

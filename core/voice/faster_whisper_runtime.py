from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any


_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE: dict[tuple[str, str, str, str, int], Any] = {}
_MODEL_MARKER_FILES = ("model.bin", "config.json", "tokenizer.json")
_CANONICAL_MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base": "Systran/faster-whisper-base",
    "base.en": "Systran/faster-whisper-base.en",
    "small": "Systran/faster-whisper-small",
    "small.en": "Systran/faster-whisper-small.en",
    "medium": "Systran/faster-whisper-medium",
    "medium.en": "Systran/faster-whisper-medium.en",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large": "Systran/faster-whisper-large-v3",
    "distil-large-v2": "Systran/faster-distil-whisper-large-v2",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
    "distil-medium.en": "Systran/faster-distil-whisper-medium.en",
    "distil-small.en": "Systran/faster-distil-whisper-small.en",
}


def clear_faster_whisper_model_cache() -> None:
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def resolve_local_faster_whisper_model(model_ref: str, download_root: Path) -> Path | None:
    normalized = str(model_ref or "").strip()
    if not normalized:
        return None

    direct_path = Path(normalized).expanduser()
    if _looks_like_local_model_path(direct_path):
        return direct_path
    if direct_path.is_absolute():
        candidate_path = direct_path
    elif normalized.startswith(".") or any(separator in normalized for separator in ("/", "\\")):
        candidate_path = download_root / direct_path
    else:
        candidate_path = None
    if candidate_path is not None and _looks_like_local_model_path(candidate_path):
        return candidate_path

    named_dir = download_root / normalized
    if _looks_like_local_model_path(named_dir):
        return named_dir

    repo_id = _canonical_model_repo(normalized)
    if repo_id is None:
        return None

    repo_root = download_root / f"models--{repo_id.replace('/', '--')}"
    snapshot_root = repo_root / "snapshots"
    if not snapshot_root.exists():
        return None

    refs_main = repo_root / "refs" / "main"
    if refs_main.exists():
        try:
            snapshot_name = refs_main.read_text(encoding="utf-8").strip()
        except OSError:
            snapshot_name = ""
        if snapshot_name:
            snapshot_path = snapshot_root / snapshot_name
            if _looks_like_local_model_path(snapshot_path):
                return snapshot_path

    try:
        snapshots = sorted(
            (candidate for candidate in snapshot_root.iterdir() if candidate.is_dir()),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    for snapshot in snapshots:
        if _looks_like_local_model_path(snapshot):
            return snapshot
    return None


def can_auto_download_faster_whisper_model(model_ref: str) -> bool:
    normalized = str(model_ref or "").strip()
    if not normalized:
        return False
    return _canonical_model_repo(normalized) is not None


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

    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached
        _MODEL_CACHE[cache_key] = model
        return model


def _canonical_model_repo(model_ref: str) -> str | None:
    normalized = str(model_ref or "").strip()
    if not normalized:
        return None
    if "/" in normalized:
        return normalized
    return _CANONICAL_MODEL_REPOS.get(normalized.casefold())


def _looks_like_local_model_path(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and any((path / marker).exists() for marker in _MODEL_MARKER_FILES)
    except OSError:
        return False

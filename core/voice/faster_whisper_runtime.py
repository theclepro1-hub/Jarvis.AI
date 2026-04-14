from __future__ import annotations

import os
import shutil
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


def find_existing_faster_whisper_model(model_ref: str, preferred_root: Path | None = None) -> Path | None:
    for root in _candidate_download_roots(preferred_root):
        resolved = resolve_local_faster_whisper_model(model_ref, root)
        if resolved is not None:
            return resolved
    return None


def preseed_faster_whisper_model(model_ref: str, target_root: Path, preferred_root: Path | None = None) -> Path | None:
    existing = resolve_local_faster_whisper_model(model_ref, target_root)
    if existing is not None:
        return existing

    source = find_existing_faster_whisper_model(model_ref, preferred_root)
    if source is None:
        return None

    repo_id = _canonical_model_repo(model_ref)
    if repo_id is None:
        destination = target_root / source.name
        return _copy_model_dir(source, destination)

    repo_root = target_root / f"models--{repo_id.replace('/', '--')}"
    snapshot_path = repo_root / "snapshots" / "preseed"
    copied = _copy_model_dir(source, snapshot_path)
    if copied is None:
        return None

    refs_dir = repo_root / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "main").write_text("preseed", encoding="utf-8")
    return resolve_local_faster_whisper_model(model_ref, target_root)


def copy_local_faster_whisper_model(
    model_ref: str,
    target_root: Path,
    preferred_root: Path | None = None,
) -> Path | None:
    return preseed_faster_whisper_model(model_ref, target_root, preferred_root)


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


def _candidate_download_roots(preferred_root: Path | None = None) -> tuple[Path, ...]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        candidate = path.expanduser()
        key = _path_key(candidate)
        if key in seen:
            return
        seen.add(key)
        roots.append(candidate)

    add(preferred_root)

    explicit_seed_root = str(os.environ.get("JARVIS_UNITY_FASTER_WHISPER_SEED_DIR", "") or "").strip()
    if explicit_seed_root:
        add(Path(explicit_seed_root))

    data_dir = str(os.environ.get("JARVIS_UNITY_DATA_DIR", "") or "").strip()
    if data_dir:
        add(Path(data_dir) / "models" / "faster-whisper")

    for env_name in ("LOCALAPPDATA", "APPDATA"):
        base = str(os.environ.get(env_name, "") or "").strip()
        if base:
            add(Path(base) / "JarvisAi_Unity" / "models" / "faster-whisper")

    program_files = str(os.environ.get("ProgramFiles", "") or "").strip()
    if program_files:
        add(Path(program_files) / "JARVIS Unity" / "assets" / "models" / "faster-whisper")

    hf_cache = str(
        os.environ.get("HF_HUB_CACHE")
        or os.environ.get("HUGGINGFACE_HUB_CACHE")
        or _huggingface_hub_cache()
        or ""
    ).strip()
    if hf_cache:
        add(Path(hf_cache))

    add(Path.home() / ".cache" / "huggingface" / "hub")
    return tuple(roots)


def _huggingface_hub_cache() -> str:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except Exception:
        return ""
    return str(HF_HUB_CACHE or "").strip()


def _copy_model_dir(source: Path, destination: Path) -> Path | None:
    if _same_path(source, destination):
        return source if _looks_like_local_model_path(source) else None

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination if _looks_like_local_model_path(destination) else None


def _looks_like_local_model_path(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and any((path / marker).exists() for marker in _MODEL_MARKER_FILES)
    except OSError:
        return False


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return False


def _path_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path)


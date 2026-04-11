from __future__ import annotations

import os
import sys
from pathlib import Path


MODEL_DIR_NAME = "vosk-model-small-ru-0.22"
REQUIRED_MODEL_FILES = (
    "am/final.mdl",
    "conf/model.conf",
    "graph/Gr.fst",
    "ivector/final.ie",
)


def resolve_vosk_runtime_model_path() -> Path:
    data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "models" / MODEL_DIR_NAME

    local_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
    return local_root / "JarvisAi_Unity" / "models" / MODEL_DIR_NAME


def resolve_vosk_bundled_model_path() -> Path:
    candidates = _bundled_model_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def resolve_vosk_build_cache_model_path() -> Path:
    return _repo_root() / "build" / "model_cache" / MODEL_DIR_NAME


def resolve_vosk_model_path() -> Path:
    candidates = _discovery_candidates()
    for candidate in candidates:
        if is_vosk_model_ready(candidate):
            return candidate
    return candidates[-1]


def is_vosk_model_ready(path: Path) -> bool:
    if not path.exists():
        return False
    return all((path / relative_path).exists() for relative_path in REQUIRED_MODEL_FILES)


def _discovery_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = list(_bundled_model_candidates())
    candidates.append(resolve_vosk_build_cache_model_path())
    candidates.append(resolve_vosk_runtime_model_path())
    return tuple(dict.fromkeys(candidates))


def _bundled_model_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "assets" / "models" / MODEL_DIR_NAME)

    candidates.append(_repo_root() / "assets" / "models" / MODEL_DIR_NAME)
    return tuple(candidates)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

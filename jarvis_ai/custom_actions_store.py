from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .custom_actions import _slugify
from .storage import custom_actions_path


def _normalize_aliases(values) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    seen = set()
    for raw in values:
        text = str(raw or "").strip()
        lowered = text.lower()
        if text and lowered not in seen:
            seen.add(lowered)
            normalized.append(text)
    return normalized


def _normalize_close_exes(values) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    seen = set()
    for raw in values:
        text = str(raw or "").strip()
        lowered = text.lower()
        if text and lowered not in seen:
            seen.add(lowered)
            normalized.append(text)
    return normalized


def normalize_manifest_actions(items) -> List[Dict[str, object]]:
    normalized = []
    seen = set()
    for index, item in enumerate(items or [], 1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        launch = str(item.get("launch", "") or "").strip()
        if not name or not launch:
            continue
        key = str(item.get("key", "") or "").strip().lower() or f"manifest_{_slugify(name)}_{index}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "key": key[:80],
                "name": name[:120],
                "launch": launch,
                "aliases": _normalize_aliases(item.get("aliases", [])),
                "close_exes": _normalize_close_exes(item.get("close_exes", [])),
                "source": "manifest",
            }
        )
    return normalized


def load_manifest_actions() -> List[Dict[str, object]]:
    path = Path(custom_actions_path())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception:
        return []
    items = payload if isinstance(payload, list) else payload.get("actions", []) if isinstance(payload, dict) else []
    return normalize_manifest_actions(items)


def save_manifest_actions(items) -> str:
    normalized = normalize_manifest_actions(items)
    path = Path(custom_actions_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"actions": normalized}, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def upsert_manifest_action(items, payload: Dict[str, object]) -> List[Dict[str, object]]:
    current = normalize_manifest_actions(items)
    candidates = normalize_manifest_actions([payload])
    if not candidates:
        return current
    item = candidates[0]
    for index, existing in enumerate(current):
        if existing.get("key") == item["key"]:
            current[index] = item
            return normalize_manifest_actions(current)
    current.append(item)
    return normalize_manifest_actions(current)


def remove_manifest_action(items, key: str) -> List[Dict[str, object]]:
    target = str(key or "").strip().lower()
    return normalize_manifest_actions([item for item in (items or []) if str(item.get("key", "")).strip().lower() != target])


__all__ = [
    "load_manifest_actions",
    "normalize_manifest_actions",
    "remove_manifest_action",
    "save_manifest_actions",
    "upsert_manifest_action",
]

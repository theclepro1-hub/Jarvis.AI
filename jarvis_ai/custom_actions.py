import json
import re
from typing import Dict, List

from .storage import custom_actions_path


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text or "custom_action"


def custom_actions_example() -> List[Dict[str, object]]:
    return [
        {
            "name": "GitHub Jarvis 2.0",
            "launch": "https://github.com/theclepro1-hub/JarvisAI-2.0",
            "aliases": ["гитхаб джарвис", "github jarvis"],
            "source": "manifest",
        }
    ]


def load_custom_action_entries() -> List[Dict[str, object]]:
    path = custom_actions_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return []
    except Exception:
        return []

    items = payload if isinstance(payload, list) else payload.get("actions", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []

    normalized = []
    seen = set()
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        launch = str(item.get("launch", "") or "").strip()
        if not name or not launch:
            continue
        key = str(item.get("key", "") or "").strip().lower() or f"manifest_{_slugify(name)}_{idx}"
        if key in seen:
            continue
        seen.add(key)
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        close_exes = item.get("close_exes", [])
        if not isinstance(close_exes, list):
            close_exes = []
        normalized.append(
            {
                "key": key,
                "name": name,
                "launch": launch,
                "aliases": [str(alias or "").strip() for alias in aliases if str(alias or "").strip()],
                "close_exes": [str(exe or "").strip() for exe in close_exes if str(exe or "").strip()],
                "source": str(item.get("source", "manifest") or "manifest").strip().lower(),
            }
        )
    return normalized


__all__ = ["custom_actions_example", "load_custom_action_entries"]

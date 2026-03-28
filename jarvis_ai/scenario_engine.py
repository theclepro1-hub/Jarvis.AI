import time
import uuid
from typing import Any, Dict, List, Optional

from .commands import normalize_text


SCENARIO_MUTABLE_KEYS = {
    "theme_mode",
    "ui_density",
    "focus_mode_enabled",
    "active_listening_enabled",
    "wake_word_boost",
    "tts_provider",
    "safe_mode_enabled",
    "background_self_check",
    "helper_guides_enabled",
}


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def normalize_scenarios(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        trigger_phrases = []
        for raw_phrase in (item.get("trigger_phrases") or []):
            phrase = str(raw_phrase or "").strip()
            if phrase and phrase.lower() not in {x.lower() for x in trigger_phrases}:
                trigger_phrases.append(phrase[:80])
        changes = {}
        for key, value in (item.get("changes") or {}).items():
            key_text = str(key or "").strip()
            if key_text in SCENARIO_MUTABLE_KEYS:
                changes[key_text] = value
        normalized.append(
            {
                "id": str(item.get("id", "") or uuid.uuid4().hex[:12]).strip()[:40],
                "name": name[:80],
                "summary": str(item.get("summary", "") or "").strip()[:200],
                "changes": changes,
                "trigger_phrases": trigger_phrases[:8],
                "enabled": bool(item.get("enabled", True)),
                "updated_at": str(item.get("updated_at", "") or _stamp()).strip()[:32],
            }
        )
    return normalized[-32:]


def upsert_scenario(items: List[Dict[str, Any]], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized = normalize_scenarios(items)
    candidate = normalize_scenarios([payload])
    if not candidate:
        return normalized
    item = candidate[0]
    for index, existing in enumerate(normalized):
        if existing.get("id") and existing.get("id") == item["id"]:
            normalized[index] = item
            return normalize_scenarios(normalized)
    normalized.append(item)
    return normalize_scenarios(normalized)


def remove_scenario(items: List[Dict[str, Any]], scenario_id: str) -> List[Dict[str, Any]]:
    target = str(scenario_id or "").strip().lower()
    return normalize_scenarios([item for item in (items or []) if str(item.get("id", "")).strip().lower() != target])


def find_matching_scenario(items: List[Dict[str, Any]], text: str) -> Optional[Dict[str, Any]]:
    norm = normalize_text(text)
    if not norm:
        return None
    for scenario in normalize_scenarios(items):
        if not scenario.get("enabled", True):
            continue
        name_norm = normalize_text(str(scenario.get("name", "") or ""))
        if name_norm and (name_norm in norm or norm in name_norm):
            if any(token in norm for token in ("режим", "сценар", "профиль", "включи", "активируй", "запусти")):
                return scenario
        for phrase in scenario.get("trigger_phrases", []) or []:
            phrase_norm = normalize_text(phrase)
            if phrase_norm and phrase_norm in norm:
                return scenario
    return None


def scenario_digest(items: List[Dict[str, Any]], limit: int = 6) -> str:
    rows = []
    for item in normalize_scenarios(items)[: max(1, int(limit or 1))]:
        rows.append(f"- {item.get('name')}: {item.get('summary')}")
    return "\n".join(rows)


def format_scenario_summary(item: Dict[str, Any]) -> str:
    name = str(item.get("name", "") or "").strip()
    summary = str(item.get("summary", "") or "").strip()
    changes = item.get("changes", {}) if isinstance(item.get("changes", {}), dict) else {}
    if not changes:
        return f"{name}: {summary or 'без изменений профиля'}"
    changed = ", ".join(sorted(changes.keys()))
    if summary:
        return f"{name}: {summary}. Меняет: {changed}."
    return f"{name}. Меняет: {changed}."


def apply_scenario_changes(app, scenario: Dict[str, Any]) -> str:
    cfg = getattr(app, "config_mgr", None)
    if cfg is None:
        return "Сценарий не применен: конфиг недоступен."

    changes = dict(scenario.get("changes", {}) or {})
    if not changes:
        cfg.set_current_scenario(str(scenario.get("name", "") or "").strip())
        return f"Сценарий «{scenario.get('name')}» активирован без дополнительных изменений."

    cfg.set_many(changes)
    cfg.set_current_scenario(str(scenario.get("name", "") or "").strip())
    try:
        if "theme_mode" in changes and hasattr(app, "apply_theme_runtime"):
            app.apply_theme_runtime()
        if ("ui_density" in changes or "focus_mode_enabled" in changes) and hasattr(app, "refresh_workspace_layout_mode"):
            app.refresh_workspace_layout_mode()
        if ("active_listening_enabled" in changes or "wake_word_boost" in changes or "tts_provider" in changes) and hasattr(app, "reload_services"):
            app.reload_services()
    except Exception:
        pass
    return f"Сценарий «{scenario.get('name')}» применен."


__all__ = [
    "SCENARIO_MUTABLE_KEYS",
    "apply_scenario_changes",
    "find_matching_scenario",
    "format_scenario_summary",
    "normalize_scenarios",
    "remove_scenario",
    "scenario_digest",
    "upsert_scenario",
]

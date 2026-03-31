import time
import uuid
from typing import Any, Dict, List, Optional

from .commands import normalize_text

try:
    import psutil
except Exception:
    psutil = None


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


def _normalize_conditions(value) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    process_any = []
    for item in (raw.get("process_any") or []):
        text = str(item or "").strip().lower()
        if text and text not in process_any:
            process_any.append(text[:64])
    return {
        "time_after": str(raw.get("time_after", "") or "").strip()[:5],
        "time_before": str(raw.get("time_before", "") or "").strip()[:5],
        "process_any": process_any[:8],
        "mic_contains": str(raw.get("mic_contains", "") or "").strip()[:64],
    }


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
                "conditions": _normalize_conditions(item.get("conditions", {})),
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
    conditions = _normalize_conditions(item.get("conditions", {}))
    condition_parts = []
    if conditions.get("time_after"):
        condition_parts.append("после " + str(conditions.get("time_after")))
    if conditions.get("time_before"):
        condition_parts.append("до " + str(conditions.get("time_before")))
    if conditions.get("process_any"):
        condition_parts.append("процессы: " + ", ".join(conditions.get("process_any")))
    if conditions.get("mic_contains"):
        condition_parts.append("микрофон: " + str(conditions.get("mic_contains")))
    if not changes:
        base = f"{name}: {summary or 'без изменений профиля'}"
        return base + (". Условия: " + "; ".join(condition_parts) if condition_parts else "")
    changed = ", ".join(sorted(changes.keys()))
    if summary:
        base = f"{name}: {summary}. Меняет: {changed}."
    else:
        base = f"{name}. Меняет: {changed}."
    if condition_parts:
        base += " Условия: " + "; ".join(condition_parts) + "."
    return base


def scenario_matches_conditions(app, scenario: Dict[str, Any]) -> bool:
    conditions = _normalize_conditions(scenario.get("conditions", {}))
    if not any(conditions.values()):
        return False

    now_hm = time.strftime("%H:%M")
    time_after = str(conditions.get("time_after", "") or "").strip()
    time_before = str(conditions.get("time_before", "") or "").strip()
    if time_after and now_hm < time_after:
        return False
    if time_before and now_hm > time_before:
        return False

    process_any = list(conditions.get("process_any") or [])
    if process_any:
        if psutil is None:
            return False
        running = set()
        try:
            for proc in psutil.process_iter(["name"]):
                name = str((proc.info or {}).get("name") or "").strip().lower()
                if name:
                    running.add(name)
        except Exception:
            return False
        if not any(process in running for process in process_any):
            return False

    mic_contains = normalize_text(str(conditions.get("mic_contains", "") or ""))
    if mic_contains:
        getter = getattr(app, "get_selected_microphone_name", None)
        current_mic = normalize_text(getter() if callable(getter) else "")
        if mic_contains not in current_mic:
            return False

    return True


def explain_scenario_conditions(app, scenario: Dict[str, Any]) -> str:
    items = normalize_scenarios([scenario or {}])
    current = items[0] if items else {}
    name = str(current.get("name", "") or "Сценарий").strip()
    summary = str(current.get("summary", "") or "").strip()
    conditions = _normalize_conditions(current.get("conditions", {}))
    if not any(conditions.values()):
        return (
            f"Сценарий «{name}» не содержит авто-условий.\n\n"
            "Он не должен включаться сам по себе: его можно запускать вручную или по фразе-триггеру."
        )

    lines = [f"Разбор сценария: {name}"]
    if summary:
        lines.append(f"Описание: {summary}")
    lines.append("")

    matched = True
    now_hm = time.strftime("%H:%M")
    time_after = str(conditions.get("time_after", "") or "").strip()
    time_before = str(conditions.get("time_before", "") or "").strip()
    if time_after:
        ok = now_hm >= time_after
        matched = matched and ok
        lines.append(f"Время после {time_after}: {'да' if ok else 'нет'} (сейчас {now_hm})")
    if time_before:
        ok = now_hm <= time_before
        matched = matched and ok
        lines.append(f"Время до {time_before}: {'да' if ok else 'нет'} (сейчас {now_hm})")

    process_any = list(conditions.get("process_any") or [])
    if process_any:
        if psutil is None:
            matched = False
            lines.append("Процессы: не удалось проверить, потому что psutil недоступен.")
        else:
            running = set()
            try:
                for proc in psutil.process_iter(["name"]):
                    proc_name = str((proc.info or {}).get("name") or "").strip().lower()
                    if proc_name:
                        running.add(proc_name)
            except Exception:
                running = set()
            found = [name for name in process_any if name in running]
            ok = bool(found)
            matched = matched and ok
            if ok:
                lines.append(f"Процессы: найдено совпадение ({', '.join(found)}).")
            else:
                lines.append(f"Процессы: совпадений нет. Ждали одно из: {', '.join(process_any)}.")

    mic_contains = normalize_text(str(conditions.get("mic_contains", "") or ""))
    if mic_contains:
        getter = getattr(app, "get_selected_microphone_name", None)
        current_mic_raw = getter() if callable(getter) else ""
        current_mic = normalize_text(current_mic_raw)
        ok = mic_contains in current_mic
        matched = matched and ok
        lines.append(
            f"Микрофон содержит «{conditions.get('mic_contains', '')}»: "
            f"{'да' if ok else 'нет'} (сейчас: {str(current_mic_raw or 'неизвестно').strip() or 'неизвестно'})."
        )

    lines.append("")
    if matched:
        lines.append("Итог: все условия выполнены. Такой сценарий должен сработать автоматически.")
    else:
        lines.append("Итог: не все условия выполнены. Сценарий не обязан срабатывать автоматически.")
    return "\n".join(lines).strip()


def find_auto_scenarios(app, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    matched = []
    for scenario in normalize_scenarios(items):
        if not scenario.get("enabled", True):
            continue
        if scenario_matches_conditions(app, scenario):
            matched.append(scenario)
    return matched


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
    "explain_scenario_conditions",
    "find_auto_scenarios",
    "find_matching_scenario",
    "format_scenario_summary",
    "normalize_scenarios",
    "remove_scenario",
    "scenario_matches_conditions",
    "scenario_digest",
    "upsert_scenario",
]

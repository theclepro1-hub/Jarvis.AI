import time
import uuid
from typing import Any, Dict, List, Optional

from .commands import normalize_text


MEMORY_SCOPES = {"personal", "temporary", "pinned"}


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def normalize_memory_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        value = str(item.get("value", "") or "").strip()
        if not title and not value:
            continue
        scope = str(item.get("scope", "personal") or "personal").strip().lower()
        if scope not in MEMORY_SCOPES:
            scope = "personal"
        tags: List[str] = []
        for raw_tag in (item.get("tags") or []):
            tag = str(raw_tag or "").strip()
            if tag and tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag[:24])
        normalized.append(
            {
                "id": str(item.get("id", "") or uuid.uuid4().hex[:12]).strip()[:40],
                "title": title[:80] or value[:80],
                "value": value[:400],
                "kind": str(item.get("kind", "note") or "note").strip().lower() or "note",
                "scope": scope,
                "pinned": bool(item.get("pinned", False) or scope == "pinned"),
                "tags": tags[:8],
                "why": str(item.get("why", "") or "").strip()[:220],
                "source": str(item.get("source", "") or "chat").strip()[:48],
                "created_at": str(item.get("created_at", "") or _stamp()).strip()[:32],
                "last_used_at": str(item.get("last_used_at", "") or "").strip()[:32],
            }
        )
    return normalized[-120:]


def upsert_memory_item(items: List[Dict[str, Any]], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized = normalize_memory_items(items)
    candidate = normalize_memory_items([payload])
    if not candidate:
        return normalized
    item = candidate[0]
    for index, existing in enumerate(normalized):
        if existing.get("id") and existing.get("id") == item["id"]:
            normalized[index] = item
            return normalize_memory_items(normalized)
    normalized.append(item)
    return normalize_memory_items(normalized)


def remove_memory_item(items: List[Dict[str, Any]], item_id: str) -> List[Dict[str, Any]]:
    target = str(item_id or "").strip().lower()
    return normalize_memory_items([item for item in (items or []) if str(item.get("id", "")).strip().lower() != target])


def find_memory_items(items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    q = normalize_text(query)
    if not q:
        return normalize_memory_items(items)
    matched = []
    for item in normalize_memory_items(items):
        hay = " ".join(
            [
                str(item.get("title", "")),
                str(item.get("value", "")),
                str(item.get("kind", "")),
                str(item.get("scope", "")),
                " ".join(item.get("tags", []) or []),
            ]
        )
        if q in normalize_text(hay):
            matched.append(item)
    return matched


def touch_memory_item(item: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(item or {})
    updated["last_used_at"] = _stamp()
    return updated


def memory_digest(items: List[Dict[str, Any]], limit: int = 8) -> str:
    rows = []
    for item in normalize_memory_items(items)[: max(1, int(limit or 1))]:
        scope = str(item.get("scope", "personal") or "personal").strip()
        title = str(item.get("title", "") or "").strip()
        value = str(item.get("value", "") or "").strip()
        rows.append(f"- {title} [{scope}]: {value}")
    return "\n".join(rows)


def parse_memory_command(text: str) -> Optional[Dict[str, Any]]:
    norm = normalize_text(text)
    if not norm:
        return None

    if any(phrase in norm for phrase in ("что ты помнишь", "покажи память", "моя память", "память джарвиса")):
        return {"intent": "show"}

    forget_prefixes = ("забудь", "удали из памяти", "сотри из памяти", "очисти память о")
    for prefix in forget_prefixes:
        if norm.startswith(prefix):
            return {"intent": "forget", "query": norm[len(prefix):].strip()}

    remember_prefixes = ("запомни что", "запомни", "помни что", "сохрани в память")
    for prefix in remember_prefixes:
        if norm.startswith(prefix):
            value = norm[len(prefix):].strip(" :,-")
            if not value:
                return None
            scope = "personal"
            if any(token in norm for token in ("временно", "ненадолго", "на время")):
                scope = "temporary"
            if any(token in norm for token in ("важно", "закрепи", "навсегда")):
                scope = "pinned"
            return {
                "intent": "remember",
                "title": value[:80],
                "value": value[:400],
                "scope": scope,
                "kind": "fact",
                "why": "Пользователь попросил запомнить это в чате.",
                "source": "chat",
            }
    return None


def format_memory_summary(items: List[Dict[str, Any]], query: str = "") -> str:
    selected = find_memory_items(items, query) if query else normalize_memory_items(items)
    if not selected:
        return "Память пока пустая."
    lines = []
    for item in selected[:8]:
        scope = {
            "personal": "личная",
            "temporary": "временная",
            "pinned": "закрепленная",
        }.get(str(item.get("scope", "personal") or "personal").strip(), "личная")
        lines.append(f"• {item.get('title')}: {item.get('value')} ({scope})")
    return "\n".join(lines)


__all__ = [
    "MEMORY_SCOPES",
    "find_memory_items",
    "format_memory_summary",
    "memory_digest",
    "normalize_memory_items",
    "parse_memory_command",
    "remove_memory_item",
    "touch_memory_item",
    "upsert_memory_item",
]

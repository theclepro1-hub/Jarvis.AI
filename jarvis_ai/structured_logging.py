from __future__ import annotations

import json
import logging
from typing import Any


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_value(val) for key, val in value.items()}
    return str(value)


def log_event(logger: logging.Logger, category: str, event: str, level: int = logging.INFO, **context: Any) -> None:
    payload = {
        "category": str(category or "app").strip().lower() or "app",
        "event": str(event or "event").strip().lower() or "event",
    }
    if context:
        payload["context"] = _normalize_value(context)
    logger.log(level, json.dumps(payload, ensure_ascii=False, sort_keys=True))


__all__ = ["log_event"]

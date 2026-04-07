from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReminderIntent:
    text: str
    due_at_utc: datetime
    delay_seconds: int
    source_text: str = ""


@dataclass(frozen=True, slots=True)
class ReminderParseResult:
    ok: bool
    intent: ReminderIntent | None = None
    error: str = ""


@dataclass(slots=True)
class ReminderRecord:
    id: str
    text: str
    due_at_utc: datetime
    created_at_utc: datetime
    status: str = "pending"
    source: str = "ui"
    telegram_chat_id: str = ""
    fired_at_utc: datetime | None = None
    error: str = ""


@dataclass(frozen=True, slots=True)
class ReminderCreateResult:
    ok: bool
    record: ReminderRecord | None = None
    message: str = ""
    error: str = ""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelegramUpdate:
    update_id: int
    chat_id: int
    user_id: int
    text: str
    message_id: int | None = None


@dataclass(frozen=True, slots=True)
class TelegramDispatchResult:
    update_id: int
    chat_id: int
    user_id: int
    authorized: bool
    handled: bool
    reply_text: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class TelegramStatusSnapshot:
    configured: bool
    connected: bool
    last_command: str = ""
    last_reply: str = ""
    last_error: str = ""
    last_poll_at_utc: datetime | None = None

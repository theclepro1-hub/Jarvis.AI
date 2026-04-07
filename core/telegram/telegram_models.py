from __future__ import annotations

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

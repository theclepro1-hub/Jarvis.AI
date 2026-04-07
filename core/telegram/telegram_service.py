from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Protocol

import httpx

from core.telegram.telegram_models import TelegramDispatchResult, TelegramUpdate


class TelegramTransport(Protocol):
    def get_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        raise NotImplementedError

    def send_message(self, chat_id: int, text: str) -> None:
        raise NotImplementedError


class TelegramOffsetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_offset(self) -> int | None:
        if not self.path.exists():
            return None
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None
        if isinstance(payload, dict):
            value = payload.get("offset")
            if isinstance(value, int) and value >= 0:
                return value
        return None

    def save_offset(self, offset: int) -> None:
        payload = {"offset": int(offset)}
        temp_path = self.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self.path)

    def _default_path(self) -> Path:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            base_dir = Path(data_dir)
        else:
            base_dir = Path(os.environ.get("APPDATA", Path.home())) / "JarvisAi_Unity"
        return base_dir / "telegram_state.json"


class HttpTelegramTransport:
    def __init__(self, bot_token: str, timeout_seconds: float = 12.0) -> None:
        self.bot_token = bot_token.strip()
        self.timeout_seconds = timeout_seconds
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def get_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        if not self.bot_token:
            return []
        params: dict[str, object] = {
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        }
        if offset is not None:
            params["offset"] = offset
        response = httpx.get(f"{self.base_url}/getUpdates", params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            return []
        updates: list[TelegramUpdate] = []
        for item in payload.get("result", []):
            message = item.get("message") or {}
            text = str(message.get("text") or "").strip()
            if not text:
                continue
            chat = message.get("chat") or {}
            user = message.get("from") or {}
            updates.append(
                TelegramUpdate(
                    update_id=int(item.get("update_id")),
                    chat_id=int(chat.get("id")),
                    user_id=int(user.get("id")),
                    text=text,
                    message_id=message.get("message_id"),
                )
            )
        return updates

    def send_message(self, chat_id: int, text: str) -> None:
        if not self.bot_token:
            return
        response = httpx.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()


class TelegramService:
    def __init__(
        self,
        settings: object,
        transport: TelegramTransport | None = None,
        offset_store: TelegramOffsetStore | None = None,
        handler: Callable[[str], str | None] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.offset_store = offset_store or TelegramOffsetStore()
        self.handler = handler
        self._offset: int | None = self.offset_store.load_offset()

    def telegram_user_id(self) -> str:
        registration = self._registration()
        return str(registration.get("telegram_user_id", "")).strip()

    def bot_token(self) -> str:
        registration = self._registration()
        return str(registration.get("telegram_bot_token", "")).strip()

    def is_configured(self) -> bool:
        return bool(self.telegram_user_id() and self.bot_token())

    def is_authorized(self, user_id: int | str) -> bool:
        configured = self.telegram_user_id()
        if not configured:
            return False
        return configured == str(user_id).strip()

    def load_offset(self) -> int | None:
        self._offset = self.offset_store.load_offset() if self.offset_store else None
        return self._offset

    def save_offset(self, offset: int) -> None:
        self._offset = int(offset)
        if self.offset_store is not None:
            self.offset_store.save_offset(self._offset)

    def poll_once(self) -> list[TelegramDispatchResult]:
        if self.transport is None:
            return []

        updates = self.transport.get_updates(self._offset)
        results: list[TelegramDispatchResult] = []
        next_offset = self._offset
        for update in updates:
            if self._offset is not None and update.update_id < self._offset:
                continue
            result = self.process_update(update)
            results.append(result)
            current_next = update.update_id + 1
            next_offset = current_next if next_offset is None else max(next_offset, current_next)
        if next_offset is not None and next_offset != self._offset:
            self.save_offset(next_offset)
        return results

    def process_update(self, update: TelegramUpdate) -> TelegramDispatchResult:
        authorized = self.is_authorized(update.user_id)
        if not authorized:
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=False,
                handled=False,
            )

        text = str(update.text or "").strip()
        if not text:
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=True,
                handled=False,
                error="empty_text",
            )

        if self.handler is None:
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=True,
                handled=False,
                error="no_handler",
            )

        try:
            reply = self.handler(text)
        except Exception as exc:
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=True,
                handled=False,
                error=type(exc).__name__,
            )

        reply_text = "" if reply is None else str(reply).strip()
        if reply_text and self.transport is not None:
            self.transport.send_message(update.chat_id, reply_text)

        return TelegramDispatchResult(
            update_id=update.update_id,
            chat_id=update.chat_id,
            user_id=update.user_id,
            authorized=True,
            handled=True,
            reply_text=reply_text,
        )

    def _registration(self) -> dict[str, object]:
        if hasattr(self.settings, "get_registration"):
            return dict(self.settings.get_registration())
        return {}

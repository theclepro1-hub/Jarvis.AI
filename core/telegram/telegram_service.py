from __future__ import annotations

from collections import deque
import inspect
import json
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

import httpx

from core.telegram.telegram_models import TelegramDispatchResult, TelegramStatusSnapshot, TelegramUpdate

DEFAULT_POLL_INTERVAL_MS = 1000
DEFAULT_LONG_POLL_TIMEOUT_SECONDS = 2.0
DEFAULT_DISPATCH_WORKERS = 4
DEFAULT_MAX_INFLIGHT_DISPATCHES = 24
DEFAULT_SEEN_UPDATE_IDS_LIMIT = 2048


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
            base_dir = (
                Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
                / "JarvisAi_Unity"
            )
        return base_dir / "telegram_state.json"


class HttpTelegramTransport:
    def __init__(
        self,
        bot_token: str,
        timeout_seconds: float = 12.0,
        poll_timeout_seconds: float = DEFAULT_LONG_POLL_TIMEOUT_SECONDS,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.timeout_seconds = timeout_seconds
        self.poll_timeout_seconds = max(0.0, float(poll_timeout_seconds))
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def get_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        if not self.bot_token:
            return []
        params: dict[str, object] = {
            "timeout": int(self.poll_timeout_seconds),
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
        self._configuration_signature = self._current_configuration_signature()
        self._connected = False
        self._last_command = ""
        self._last_reply = ""
        self._last_error = ""
        self._last_poll_at_utc: datetime | None = None
        self._state_lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._seen_lock = threading.Lock()
        self._seen_update_ids: deque[int] = deque()
        self._seen_update_ids_set: set[int] = set()
        self._inflight_dispatches = 0
        self._dispatch_pool = ThreadPoolExecutor(
            max_workers=DEFAULT_DISPATCH_WORKERS,
            thread_name_prefix="telegram-dispatch",
        )

    def telegram_user_id(self) -> str:
        registration = self._registration()
        return str(registration.get("telegram_user_id", "")).strip()

    def bot_token(self) -> str:
        registration = self._registration()
        return str(registration.get("telegram_bot_token", "")).strip()

    def is_configured(self) -> bool:
        return bool(self.telegram_user_id() and self.bot_token())

    def poll_interval_ms(self) -> int:
        return DEFAULT_POLL_INTERVAL_MS

    def status_snapshot(self) -> TelegramStatusSnapshot:
        with self._state_lock:
            connected = self._connected
            last_command = self._last_command
            last_reply = self._last_reply
            last_error = self._last_error
            last_poll_at_utc = self._last_poll_at_utc
        return TelegramStatusSnapshot(
            configured=self.is_configured(),
            connected=connected,
            last_command=last_command,
            last_reply=last_reply,
            last_error=last_error,
            last_poll_at_utc=last_poll_at_utc,
        )

    def last_command(self) -> str:
        with self._state_lock:
            return self._last_command

    def last_reply(self) -> str:
        with self._state_lock:
            return self._last_reply

    def last_error(self) -> str:
        with self._state_lock:
            return self._last_error

    def last_poll_at_utc(self) -> datetime | None:
        with self._state_lock:
            return self._last_poll_at_utc

    def is_connected(self) -> bool:
        with self._state_lock:
            return self._connected

    def pending_dispatches(self) -> int:
        with self._dispatch_lock:
            return self._inflight_dispatches

    def can_poll_now(self) -> bool:
        return self.pending_dispatches() < DEFAULT_MAX_INFLIGHT_DISPATCHES

    def refresh_configuration(self) -> bool:
        next_signature = self._current_configuration_signature()
        if next_signature == self._configuration_signature:
            if self.transport is None and self.is_configured():
                self._refresh_http_transport(next_signature[0])
                return True
            return False

        previous_token = self._configuration_signature[0]
        next_token = next_signature[0]
        self._configuration_signature = next_signature
        if previous_token != next_token:
            self._connected = False
            self._refresh_http_transport(next_token)
        return True

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

    def poll_once(self, *, async_dispatch: bool = False) -> list[TelegramDispatchResult]:
        if self.transport is None:
            with self._state_lock:
                self._connected = False
            return []

        try:
            updates = self.transport.get_updates(self._offset)
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._connected = False
                self._last_error = self._format_error(exc)
                self._last_poll_at_utc = datetime.now(timezone.utc)
            return []

        with self._state_lock:
            self._connected = True
            self._last_error = ""
            self._last_poll_at_utc = datetime.now(timezone.utc)
        filtered_updates: list[TelegramUpdate] = []
        next_offset = self._offset
        for update in updates:
            if self._offset is not None and update.update_id < self._offset:
                continue
            if self._is_seen_update(update.update_id):
                continue
            self._remember_seen_update(update.update_id)
            filtered_updates.append(update)
            current_next = update.update_id + 1
            next_offset = current_next if next_offset is None else max(next_offset, current_next)
        if next_offset is not None and next_offset != self._offset:
            self.save_offset(next_offset)

        if async_dispatch:
            for update in filtered_updates:
                self._submit_dispatch(update)
            return [
                TelegramDispatchResult(
                    update_id=update.update_id,
                    chat_id=update.chat_id,
                    user_id=update.user_id,
                    authorized=self.is_authorized(update.user_id),
                    handled=False,
                    error="queued",
                )
                for update in filtered_updates
            ]

        results: list[TelegramDispatchResult] = []
        for update in filtered_updates:
            results.append(self._process_update_safe(update))
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

        with self._state_lock:
            self._last_command = text
        try:
            reply = self._call_handler(text, update.chat_id)
        except Exception as exc:
            with self._state_lock:
                self._connected = False
                self._last_error = self._format_error(exc)
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=True,
                handled=False,
                error=self.last_error(),
            )

        reply_text = "" if reply is None else str(reply).strip()
        if not reply_text:
            reply_text = "Не понял запрос. Уточните, что сделать."

        if self.transport is not None:
            if not self.send_message(update.chat_id, reply_text):
                return TelegramDispatchResult(
                    update_id=update.update_id,
                    chat_id=update.chat_id,
                    user_id=update.user_id,
                    authorized=True,
                    handled=False,
                    reply_text=reply_text,
                    error=self.last_error() or "send_failed",
                )
            with self._state_lock:
                self._last_reply = reply_text
                self._last_error = ""
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=True,
                handled=True,
                reply_text=reply_text,
            )

        return TelegramDispatchResult(
            update_id=update.update_id,
            chat_id=update.chat_id,
            user_id=update.user_id,
            authorized=True,
            handled=True,
            reply_text=reply_text,
        )

    def send_message(self, chat_id: int | str, text: str) -> bool:
        if self.transport is None:
            with self._state_lock:
                self._connected = False
                self._last_error = "no_transport"
            return False

        try:
            normalized_chat_id = int(str(chat_id).strip())
        except (TypeError, ValueError):
            with self._state_lock:
                self._connected = False
                self._last_error = "invalid_chat_id"
            return False

        payload = str(text or "").strip()
        if not payload:
            with self._state_lock:
                self._connected = False
                self._last_error = "empty_text"
            return False

        try:
            self.transport.send_message(normalized_chat_id, payload)
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._connected = False
                self._last_error = self._format_error(exc)
            return False

        with self._state_lock:
            self._connected = True
            self._last_reply = payload
            self._last_error = ""
        return True

    def send_test_message(
        self,
        chat_id: int | str | None = None,
        text: str = "Тестовое сообщение JARVIS Unity",
    ) -> bool:
        self.refresh_configuration()
        target_chat_id = chat_id if chat_id is not None else self.telegram_user_id()
        return self.send_message(target_chat_id, text)

    def _call_handler(self, text: str, chat_id: int) -> str | None:
        if self.handler is None:
            return None
        try:
            parameter_count = len(inspect.signature(self.handler).parameters)
        except (TypeError, ValueError):
            parameter_count = 1
        if parameter_count >= 2:
            return self.handler(text, str(chat_id))
        return self.handler(text)

    def _registration(self) -> dict[str, object]:
        if hasattr(self.settings, "get_registration"):
            return dict(self.settings.get_registration())
        return {}

    def _current_configuration_signature(self) -> tuple[str, str]:
        return (self.bot_token(), self.telegram_user_id())

    def _refresh_http_transport(self, token: str) -> None:
        if self.transport is not None and not isinstance(self.transport, HttpTelegramTransport):
            return
        self.transport = self._create_http_transport(token)
        self.load_offset()

    def _create_http_transport(self, token: str) -> HttpTelegramTransport | None:
        token = str(token or "").strip()
        if not token:
            return None
        network = {}
        if hasattr(self.settings, "get"):
            network = self.settings.get("network", {}) or {}
        timeout = float(network.get("timeout_seconds", 12.0)) if isinstance(network, dict) else 12.0
        return HttpTelegramTransport(token, timeout_seconds=timeout)

    def _format_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return f"{type(exc).__name__}: {message}"
        return type(exc).__name__

    def _is_seen_update(self, update_id: int) -> bool:
        with self._seen_lock:
            return update_id in self._seen_update_ids_set

    def _remember_seen_update(self, update_id: int) -> None:
        with self._seen_lock:
            if update_id in self._seen_update_ids_set:
                return
            if len(self._seen_update_ids) >= DEFAULT_SEEN_UPDATE_IDS_LIMIT:
                old_update_id = self._seen_update_ids.popleft()
                self._seen_update_ids_set.discard(old_update_id)
            self._seen_update_ids.append(update_id)
            self._seen_update_ids_set.add(update_id)

    def _submit_dispatch(self, update: TelegramUpdate) -> None:
        with self._dispatch_lock:
            self._inflight_dispatches += 1
        future = self._dispatch_pool.submit(self._process_update_safe, update)
        future.add_done_callback(self._dispatch_done)

    def _dispatch_done(self, future: Future[TelegramDispatchResult]) -> None:
        try:
            future.result()
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._connected = False
                self._last_error = self._format_error(exc)
        finally:
            with self._dispatch_lock:
                self._inflight_dispatches = max(0, self._inflight_dispatches - 1)

    def _process_update_safe(self, update: TelegramUpdate) -> TelegramDispatchResult:
        try:
            return self.process_update(update)
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._connected = False
                self._last_error = self._format_error(exc)
                error = self._last_error
            return TelegramDispatchResult(
                update_id=update.update_id,
                chat_id=update.chat_id,
                user_id=update.user_id,
                authorized=self.is_authorized(update.user_id),
                handled=False,
                error=error,
            )

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.reminders.reminder_models import ReminderIntent, ReminderRecord


class ReminderStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def add(self, intent: ReminderIntent, source: str = "ui", telegram_chat_id: str = "") -> ReminderRecord:
        record = ReminderRecord(
            id=uuid4().hex,
            text=intent.text,
            due_at_utc=self._ensure_utc(intent.due_at_utc),
            created_at_utc=datetime.now(timezone.utc),
            status="pending",
            source=source,
            telegram_chat_id=str(telegram_chat_id or "").strip(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reminders (
                    id, text, due_at_utc, created_at_utc, status, source, telegram_chat_id, fired_at_utc, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._row_values(record),
            )
        return record

    def get(self, reminder_id: str) -> ReminderRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list_pending(self) -> list[ReminderRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status = 'pending' ORDER BY due_at_utc ASC"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_due(self, now: datetime | None = None) -> list[ReminderRecord]:
        now_utc = self._ensure_utc(now or datetime.now(timezone.utc))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'pending' AND due_at_utc <= ?
                ORDER BY due_at_utc ASC
                """,
                (self._serialize_datetime(now_utc),),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def mark_fired(self, reminder_id: str, fired_at_utc: datetime | None = None) -> None:
        fired_at = self._ensure_utc(fired_at_utc or datetime.now(timezone.utc))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'fired', fired_at_utc = ?, error = ''
                WHERE id = ?
                """,
                (self._serialize_datetime(fired_at), reminder_id),
            )

    def mark_failed(self, reminder_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'failed', error = ?
                WHERE id = ?
                """,
                (str(error), reminder_id),
            )

    def cancel(self, reminder_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE reminders
                SET status = 'cancelled'
                WHERE id = ? AND status = 'pending'
                """,
                (reminder_id,),
            )
            return cursor.rowcount > 0

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    due_at_utc TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    telegram_chat_id TEXT NOT NULL DEFAULT '',
                    fired_at_utc TEXT,
                    error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reminders_due_status
                ON reminders(status, due_at_utc)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_values(self, record: ReminderRecord) -> tuple[object, ...]:
        return (
            record.id,
            record.text,
            self._serialize_datetime(record.due_at_utc),
            self._serialize_datetime(record.created_at_utc),
            record.status,
            record.source,
            record.telegram_chat_id,
            self._serialize_datetime(record.fired_at_utc) if record.fired_at_utc else None,
            record.error,
        )

    def _row_to_record(self, row: sqlite3.Row | None) -> ReminderRecord:
        if row is None:
            raise ValueError("row is required")
        return ReminderRecord(
            id=str(row["id"]),
            text=str(row["text"]),
            due_at_utc=self._parse_datetime(str(row["due_at_utc"])),
            created_at_utc=self._parse_datetime(str(row["created_at_utc"])),
            status=str(row["status"]),
            source=str(row["source"]),
            telegram_chat_id=str(row["telegram_chat_id"] or ""),
            fired_at_utc=self._parse_datetime(str(row["fired_at_utc"])) if row["fired_at_utc"] else None,
            error=str(row["error"] or ""),
        )

    def _serialize_datetime(self, value: datetime) -> str:
        return self._ensure_utc(value).isoformat()

    def _parse_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return self._ensure_utc(parsed)

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _default_path(self) -> Path:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            base_dir = Path(data_dir)
        else:
            base_dir = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home())) / "JarvisAi_Unity"
        return base_dir / "reminders.sqlite3"

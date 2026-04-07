from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from core.reminders.reminder_models import (
    ReminderCreateResult,
    ReminderIntent,
    ReminderParseResult,
    ReminderRecord,
)
from core.reminders.reminder_parser import ReminderIntentService, ReminderParser
from core.reminders.reminder_store import ReminderStore


class ReminderService:
    def __init__(
        self,
        store: ReminderStore | None = None,
        intent_service: ReminderIntentService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store or ReminderStore()
        self.intent_service = intent_service or ReminderIntentService(ReminderParser())
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self, text: str, now: datetime | None = None) -> ReminderParseResult:
        return self.intent_service.parse(text, now=now or self.clock())

    def create_from_text(
        self,
        text: str,
        source: str = "ui",
        telegram_chat_id: str = "",
        now: datetime | None = None,
    ) -> ReminderCreateResult:
        parsed = self.preview(text, now=now)
        if not parsed.ok or parsed.intent is None:
            return ReminderCreateResult(False, error=parsed.error or "parse_failed")

        record = self.store.add(parsed.intent, source=source, telegram_chat_id=telegram_chat_id)
        return ReminderCreateResult(
            True,
            record=record,
            message=self._confirmation_message(parsed.intent),
        )

    def due(self, now: datetime | None = None) -> list[ReminderRecord]:
        return self.store.list_due(now or self.clock())

    def recover_due(self, now: datetime | None = None) -> list[ReminderRecord]:
        return self.due(now=now)

    def fire_due(
        self,
        notifier: Callable[[ReminderRecord], None],
        now: datetime | None = None,
    ) -> list[ReminderRecord]:
        due = self.due(now=now)
        fired: list[ReminderRecord] = []
        for record in due:
            try:
                notifier(record)
            except Exception as exc:  # noqa: BLE001
                self.store.mark_failed(record.id, type(exc).__name__)
                continue
            self.store.mark_fired(record.id, fired_at_utc=now or self.clock())
            fired.append(self.store.get(record.id) or record)
        return fired

    def cancel(self, reminder_id: str) -> bool:
        return self.store.cancel(reminder_id)

    def reminder_intent(self, text: str, now: datetime | None = None) -> ReminderParseResult:
        return self.preview(text, now=now)

    def _confirmation_message(self, intent: ReminderIntent) -> str:
        minutes = intent.delay_seconds // 60
        if intent.delay_seconds % 86400 == 0:
            units = f"{intent.delay_seconds // 86400} дн."
        elif intent.delay_seconds % 3600 == 0:
            units = f"{intent.delay_seconds // 3600} ч."
        elif minutes > 0:
            units = f"{minutes} мин."
        else:
            units = f"{intent.delay_seconds} сек."
        return f"Напомню через {units}: {intent.text}"

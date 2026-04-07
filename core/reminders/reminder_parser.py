from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.reminders.reminder_models import ReminderIntent, ReminderParseResult


@dataclass(slots=True)
class ReminderParser:
    patterns: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"^напомни(?: мне)?\s+(?P<text>.+?)\s+через\s+(?P<amount>\d+)\s*(?P<unit>[^\s]+)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^напомни(?: мне)?\s+через\s+(?P<amount>\d+)\s*(?P<unit>[^\s]+)\s+(?P<text>.+?)\s*$",
            re.IGNORECASE,
        ),
    )

    def parse(self, text: str, now: datetime | None = None) -> ReminderParseResult:
        clean = " ".join(str(text or "").split()).strip()
        if not clean:
            return ReminderParseResult(False, error="empty_text")

        now_utc = self._ensure_utc(now or datetime.now(timezone.utc))

        for pattern in self.patterns:
            match = pattern.match(clean)
            if not match:
                continue
            amount = self._parse_amount(match.group("amount"))
            if amount is None or amount <= 0:
                return ReminderParseResult(False, error="bad_delay")
            multiplier = self._unit_multiplier(match.group("unit"))
            if multiplier is None:
                return ReminderParseResult(False, error="bad_unit")
            reminder_text = " ".join(str(match.group("text") or "").split()).strip(" .,!?:;")
            if not reminder_text:
                return ReminderParseResult(False, error="missing_text")
            delay_seconds = amount * multiplier
            intent = ReminderIntent(
                text=reminder_text,
                due_at_utc=now_utc + timedelta(seconds=delay_seconds),
                delay_seconds=delay_seconds,
                source_text=clean,
            )
            return ReminderParseResult(True, intent=intent)

        return ReminderParseResult(False, error="not_a_reminder")

    def _parse_amount(self, raw_amount: str) -> int | None:
        try:
            return int(raw_amount)
        except (TypeError, ValueError):
            return None

    def _unit_multiplier(self, unit: str) -> int | None:
        normalized = self._normalize_unit(unit)
        if normalized.startswith("сек"):
            return 1
        if normalized.startswith("мин"):
            return 60
        if normalized.startswith("час"):
            return 3600
        if normalized.startswith("д"):
            return 86400
        return None

    def _normalize_unit(self, unit: str) -> str:
        clean = unit.casefold().strip()
        clean = re.sub(r"[^\wа-яё]+", "", clean)
        return clean

    def _ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


@dataclass(slots=True)
class ReminderIntentService:
    parser: ReminderParser

    def parse(self, text: str, now: datetime | None = None) -> ReminderParseResult:
        return self.parser.parse(text, now=now)

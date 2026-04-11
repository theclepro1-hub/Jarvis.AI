from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.reminders.reminder_models import ReminderRecord
from core.reminders.reminder_parser import ReminderParser
from core.reminders.reminder_service import ReminderService
from core.reminders.reminder_store import ReminderStore


def test_reminder_parser_extracts_text_and_due_time() -> None:
    now = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    parser = ReminderParser()

    result = parser.parse("напомни мне покакать через 1 минуту", now=now)

    assert result.ok is True
    assert result.intent is not None
    assert result.intent.text == "покакать"
    assert result.intent.delay_seconds == 60
    assert result.intent.due_at_utc == now + timedelta(minutes=1)


def test_reminder_service_creates_fires_and_recovers_after_restart(tmp_path) -> None:
    store_path = tmp_path / "reminders.sqlite3"
    base = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    service = ReminderService(store=ReminderStore(store_path), clock=lambda: base)

    create_result = service.create_from_text("напомни мне покакать через 1 минуту", now=base)

    assert create_result.ok is True
    assert create_result.record is not None
    assert create_result.record.status == "pending"
    assert "Напомню через 1 мин." in create_result.message

    restarted = ReminderService(store=ReminderStore(store_path), clock=lambda: base + timedelta(minutes=2))
    recovered = restarted.recover_due()

    assert len(recovered) == 1
    assert recovered[0].text == "покакать"

    fired: list[ReminderRecord] = []
    fired_results = restarted.fire_due(lambda record: fired.append(record))

    assert fired_results[0].status == "fired"
    assert fired[0].text == "покакать"
    assert restarted.store.list_pending() == []


def test_reminder_service_does_not_fake_confirm_when_parse_fails(tmp_path) -> None:
    service = ReminderService(store=ReminderStore(tmp_path / "reminders.sqlite3"))

    result = service.create_from_text("напомни мне", now=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc))

    assert result.ok is False
    assert result.record is None
    assert result.error in {"not_a_reminder", "missing_text", "parse_failed"}
    assert service.store.list_pending() == []


def test_reminder_service_keeps_due_reminders_pending_on_transient_failure(tmp_path) -> None:
    base = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    service = ReminderService(store=ReminderStore(tmp_path / "reminders.sqlite3"), clock=lambda: base)
    create_result = service.create_from_text("напомни мне чай через 1 минуту", now=base)

    assert create_result.ok is True
    assert create_result.record is not None

    def boom(_record: ReminderRecord) -> None:
        raise RuntimeError("boom")

    failed = service.fire_due(boom, now=base + timedelta(minutes=2))

    assert failed == []
    pending = service.store.list_pending()
    assert len(pending) == 1
    assert pending[0].id == create_result.record.id

    stored = service.store.get(create_result.record.id)
    assert stored is not None
    assert stored.status == "pending"

    recovered = service.recover_due(now=base + timedelta(minutes=3))
    assert len(recovered) == 1
    assert recovered[0].id == create_result.record.id

    fired: list[ReminderRecord] = []
    fired_results = service.fire_due(lambda record: fired.append(record), now=base + timedelta(minutes=3))

    assert len(fired_results) == 1
    assert fired[0].id == create_result.record.id
    assert service.store.list_pending() == []


def test_reminder_service_can_cancel_pending_reminder(tmp_path) -> None:
    base = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    service = ReminderService(store=ReminderStore(tmp_path / "reminders.sqlite3"), clock=lambda: base)
    create_result = service.create_from_text("напомни мне чай через 1 минуту", now=base)

    assert create_result.ok is True
    assert create_result.record is not None

    assert service.cancel(create_result.record.id) is True
    stored = service.store.get(create_result.record.id)
    assert stored is not None
    assert stored.status == "cancelled"
    assert service.store.list_pending() == []

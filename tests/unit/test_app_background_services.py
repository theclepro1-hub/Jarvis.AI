from __future__ import annotations

from threading import Event
from types import SimpleNamespace

from app.app import JarvisUnityApplication


class FakeReminderService:
    def __init__(self, record) -> None:  # noqa: ANN001
        self.record = record
        self.fired = False

    def fire_due(self, notifier):  # noqa: ANN001, ANN201
        self.fired = True
        notifier(self.record)
        return [self.record]


class FakeChatBridge:
    def __init__(self) -> None:
        self.notes: list[str] = []

    def appendAssistantNote(self, text: str) -> None:
        self.notes.append(text)


class FakeTelegramTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.event = Event()

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))
        self.event.set()


class FakeTelegram:
    def __init__(self, transport: FakeTelegramTransport) -> None:
        self.transport = transport
        self.refreshes = 0
        self.send_calls: list[tuple[str, str]] = []

    def refresh_configuration(self) -> bool:
        self.refreshes += 1
        return False

    def telegram_user_id(self) -> str:
        return "123456789"

    def send_message(self, chat_id: str | int, text: str) -> bool:
        self.send_calls.append((str(chat_id), text))
        self.transport.send_message(int(chat_id), text)
        return True


class FakeRuntime:
    def __init__(self, record, transport: FakeTelegramTransport) -> None:  # noqa: ANN001
        self.services = SimpleNamespace(
            reminders=FakeReminderService(record),
            telegram=FakeTelegram(transport),
        )
        self.chat_bridge = FakeChatBridge()

    def _send_telegram_note_async(self, record, message: str) -> None:  # noqa: ANN001
        JarvisUnityApplication._send_telegram_note_async(self, record, message)


def test_due_reminder_posts_to_chat_and_telegram() -> None:
    transport = FakeTelegramTransport()
    record = SimpleNamespace(text="чай", telegram_chat_id="777")
    runtime = FakeRuntime(record, transport)

    JarvisUnityApplication._fire_due_reminders(runtime)

    assert runtime.services.reminders.fired is True
    assert runtime.chat_bridge.notes == ["Напоминание: чай"]
    assert runtime.services.telegram.refreshes == 1
    assert transport.event.wait(2)
    assert transport.sent == [(777, "Напоминание: чай")]


def test_due_reminder_uses_configured_telegram_user_when_record_has_no_chat_id() -> None:
    transport = FakeTelegramTransport()
    record = SimpleNamespace(text="встать", telegram_chat_id="")
    runtime = FakeRuntime(record, transport)

    JarvisUnityApplication._fire_due_reminders(runtime)

    assert runtime.chat_bridge.notes == ["Напоминание: встать"]
    assert transport.event.wait(2)
    assert transport.sent == [(123456789, "Напоминание: встать")]

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.telegram.telegram_models import TelegramUpdate
from core.telegram.telegram_service import TelegramService


class FakeSettings:
    def __init__(self, telegram_user_id: str = "123456789", telegram_bot_token: str = "bot_token") -> None:
        self._registration = {
            "telegram_user_id": telegram_user_id,
            "telegram_bot_token": telegram_bot_token,
        }

    def get_registration(self) -> dict[str, str]:
        return dict(self._registration)


class FakeOffsetStore:
    def __init__(self, offset: int | None = None) -> None:
        self.offset = offset
        self.saved: list[int] = []

    def load_offset(self) -> int | None:
        return self.offset

    def save_offset(self, offset: int) -> None:
        self.offset = offset
        self.saved.append(offset)


@dataclass
class FakeTransport:
    updates: list[TelegramUpdate]

    def __post_init__(self) -> None:
        self.requested_offsets: list[int | None] = []
        self.sent_messages: list[tuple[int, str]] = []

    def get_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        self.requested_offsets.append(offset)
        if offset is None:
            return list(self.updates)
        return [update for update in self.updates if update.update_id >= offset]

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


def test_authorized_telegram_command_routes_through_handler(tmp_path: Path) -> None:
    updates = [TelegramUpdate(update_id=10, chat_id=777, user_id=123456789, text="открой ютуб")]
    transport = FakeTransport(updates)
    offset_store = FakeOffsetStore(offset=10)
    received: list[str] = []

    def handler(text: str) -> str:
        received.append(text)
        return "Открываю YouTube"

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=handler,
    )

    results = service.poll_once()

    assert received == ["открой ютуб"]
    assert transport.sent_messages == [(777, "Открываю YouTube")]
    assert offset_store.saved[-1] == 11
    assert results[0].authorized is True
    assert results[0].handled is True


def test_unauthorized_user_is_ignored_but_offset_advances() -> None:
    updates = [TelegramUpdate(update_id=5, chat_id=777, user_id=42, text="открой ютуб")]
    transport = FakeTransport(updates)
    offset_store = FakeOffsetStore(offset=5)
    received: list[str] = []

    def handler(text: str) -> str:
        received.append(text)
        return "Открываю YouTube"

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=handler,
    )

    results = service.poll_once()

    assert received == []
    assert transport.sent_messages == []
    assert offset_store.saved[-1] == 6
    assert results[0].authorized is False
    assert results[0].handled is False


def test_offset_persistence_is_loaded_before_polling() -> None:
    updates = [TelegramUpdate(update_id=14, chat_id=777, user_id=123456789, text="привет")]
    transport = FakeTransport(updates)
    offset_store = FakeOffsetStore(offset=14)

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=lambda text: "ok",
    )

    service.poll_once()

    assert transport.requested_offsets == [14]
    assert offset_store.saved[-1] == 15

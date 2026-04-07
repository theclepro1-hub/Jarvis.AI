from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.telegram.telegram_models import TelegramUpdate
from core.telegram.telegram_service import DEFAULT_POLL_INTERVAL_MS, HttpTelegramTransport, TelegramService


class FakeSettings:
    def __init__(self, telegram_user_id: str = "123456789", telegram_bot_token: str = "bot_token") -> None:
        self._registration = {
            "telegram_user_id": telegram_user_id,
            "telegram_bot_token": telegram_bot_token,
        }
        self._settings = {"network": {"timeout_seconds": 12.0}}

    def get_registration(self) -> dict[str, str]:
        return dict(self._registration)

    def get(self, key: str, default=None):  # noqa: ANN001, ANN201
        return self._settings.get(key, default)

    def set_registration(self, telegram_user_id: str, telegram_bot_token: str) -> None:
        self._registration["telegram_user_id"] = telegram_user_id
        self._registration["telegram_bot_token"] = telegram_bot_token


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
    fail_get_updates: Exception | None = None
    fail_send_message: Exception | None = None

    def __post_init__(self) -> None:
        self.requested_offsets: list[int | None] = []
        self.sent_messages: list[tuple[int, str]] = []

    def get_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        self.requested_offsets.append(offset)
        if self.fail_get_updates is not None:
            raise self.fail_get_updates
        if offset is None:
            return list(self.updates)
        return [update for update in self.updates if update.update_id >= offset]

    def send_message(self, chat_id: int, text: str) -> None:
        if self.fail_send_message is not None:
            raise self.fail_send_message
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


def test_authorized_telegram_command_can_pass_chat_id_to_handler() -> None:
    updates = [TelegramUpdate(update_id=11, chat_id=777, user_id=123456789, text="напомни мне чай через 1 минуту")]
    transport = FakeTransport(updates)
    received: list[tuple[str, str]] = []

    def handler(text: str, chat_id: str) -> str:
        received.append((text, chat_id))
        return "Напомню через 1 мин.: чай"

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=11),
        handler=handler,
    )

    service.poll_once()

    assert received == [("напомни мне чай через 1 минуту", "777")]
    assert transport.sent_messages == [(777, "Напомню через 1 мин.: чай")]


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


def test_telegram_poll_interval_contract_is_fast_without_busy_loop() -> None:
    service = TelegramService(FakeSettings(), transport=FakeTransport([]), offset_store=FakeOffsetStore())

    assert 750 <= service.poll_interval_ms() <= DEFAULT_POLL_INTERVAL_MS


def test_http_transport_uses_short_long_poll_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "result": []}

    def fake_get(url, params, timeout):  # noqa: ANN001, ANN202
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("core.telegram.telegram_service.httpx.get", fake_get)
    transport = HttpTelegramTransport("bot_secret", timeout_seconds=12.0, poll_timeout_seconds=2.0)

    assert transport.get_updates(offset=40) == []

    assert captured["params"]["timeout"] == 2
    assert captured["params"]["offset"] == 40
    assert captured["timeout"] == 12.0
    assert "bot_secret" in captured["url"]


def test_refresh_configuration_rebuilds_http_transport_without_restart() -> None:
    settings = FakeSettings(telegram_user_id="123", telegram_bot_token="old_token")
    service = TelegramService(
        settings,
        transport=HttpTelegramTransport("old_token"),
        offset_store=FakeOffsetStore(offset=7),
    )

    settings.set_registration("456", "new_token")

    assert service.refresh_configuration() is True
    assert isinstance(service.transport, HttpTelegramTransport)
    assert service.transport.bot_token == "new_token"
    assert service.is_authorized("456") is True
    assert service.is_authorized("123") is False


def test_telegram_status_snapshot_tracks_last_command_reply_and_poll() -> None:
    updates = [TelegramUpdate(update_id=21, chat_id=777, user_id=123456789, text="привет")]
    transport = FakeTransport(updates)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=21),
        handler=lambda text: f"ok:{text}",
    )

    results = service.poll_once()
    snapshot = service.status_snapshot()

    assert results[0].reply_text == "ok:привет"
    assert snapshot.configured is True
    assert snapshot.connected is True
    assert snapshot.last_command == "привет"
    assert snapshot.last_reply == "ok:привет"
    assert snapshot.last_error == ""
    assert snapshot.last_poll_at_utc is not None


def test_telegram_service_exposes_failure_status_and_can_send_test_message() -> None:
    transport = FakeTransport([], fail_get_updates=RuntimeError("network down"), fail_send_message=RuntimeError("send down"))
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=0),
        handler=lambda text: f"ok:{text}",
    )

    results = service.poll_once()
    assert results == []
    assert service.is_connected() is False
    assert "RuntimeError" in service.last_error()

    assert service.send_test_message("777", "проверка telegram") is False
    assert "RuntimeError" in service.last_error()


def test_telegram_service_send_test_message_uses_configured_user_id() -> None:
    transport = FakeTransport([])
    service = TelegramService(
        FakeSettings(telegram_user_id="987654321", telegram_bot_token="bot_token"),
        transport=transport,
        offset_store=FakeOffsetStore(offset=0),
    )

    assert service.send_test_message() is True
    assert transport.sent_messages == [(987654321, "Тестовое сообщение JARVIS Unity")]

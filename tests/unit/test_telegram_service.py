from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import Future
from pathlib import Path
import time
import threading
from types import SimpleNamespace

from core.telegram.telegram_models import TelegramDispatchResult, TelegramUpdate
from core.telegram.telegram_service import DEFAULT_POLL_INTERVAL_MS, HttpTelegramTransport, TelegramService
from core.services.service_container import ServiceContainer


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
        self.sent_chat_actions: list[tuple[int, str]] = []
        self.closed = False

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

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        self.sent_chat_actions.append((chat_id, action))

    def close(self) -> None:
        self.closed = True


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


def test_http_transport_uses_persistent_client_and_short_long_poll_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "result": []}

    class FakeClient:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            captured["client_kwargs"] = kwargs
            captured["client_inits"] = int(captured.get("client_inits", 0)) + 1

        def get(self, url, params=None):  # noqa: ANN001, ANN202
            captured["get_url"] = url
            captured["get_params"] = params
            captured["get_client_id"] = id(self)
            return Response()

        def post(self, url, json=None):  # noqa: ANN001, ANN202
            captured.setdefault("posts", []).append((id(self), url, json))
            return Response()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("core.telegram.telegram_service.httpx.Client", FakeClient)
    transport = HttpTelegramTransport(
        "bot_secret",
        timeout_seconds=12.0,
        poll_timeout_seconds=2.0,
        proxy_mode="manual",
        proxy_url="http://127.0.0.1:8080",
    )

    assert transport.get_updates(offset=40) == []
    transport.send_message(777, "ok")
    transport.send_chat_action(777)
    transport.close()

    assert captured["client_inits"] == 1
    assert captured["get_params"]["timeout"] == 2
    assert captured["get_params"]["offset"] == 40
    assert "bot_secret" in captured["get_url"]
    assert len(captured["posts"]) == 2
    assert all(post[0] == captured["get_client_id"] for post in captured["posts"])
    assert captured["client_kwargs"]["proxy"] == "http://127.0.0.1:8080"
    assert captured["client_kwargs"]["trust_env"] is False
    assert captured["closed"] is True


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


def test_refresh_configuration_rebuilds_http_transport_when_network_changes() -> None:
    settings = FakeSettings(telegram_user_id="123", telegram_bot_token="stable_token")
    service = TelegramService(
        settings,
        transport=HttpTelegramTransport("stable_token", proxy_mode="off"),
        offset_store=FakeOffsetStore(offset=7),
    )
    previous_transport = service.transport
    settings._settings["network"] = {
        "timeout_seconds": 25.0,
        "proxy_mode": "manual",
        "proxy_url": "http://127.0.0.1:8080",
    }

    assert service.refresh_configuration() is True
    assert service.transport is not previous_transport
    assert isinstance(service.transport, HttpTelegramTransport)
    assert service.transport.timeout_seconds == 25.0
    assert service.transport.proxy_mode == "manual"
    assert service.transport.proxy_url == "http://127.0.0.1:8080"


def test_async_dispatch_uses_ai_lane_when_classifier_marks_update() -> None:
    updates = [TelegramUpdate(update_id=71, chat_id=777, user_id=123456789, text="explain this")]
    transport = FakeTransport(updates)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=71),
        handler=lambda text: f"ok:{text}",
        classifier=lambda text, chat_id: "ai",
    )
    submitted: list[tuple[int, str]] = []

    service._submit_dispatch = lambda update, lane="fast": submitted.append((update.update_id, lane))  # type: ignore[method-assign]  # noqa: SLF001,E731

    queued = service.poll_once(async_dispatch=True)

    assert queued[0].error == "queued"
    assert submitted == [(71, "ai")]


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


def test_handler_status_callback_throttles_typing_chat_action(monkeypatch) -> None:
    updates = [TelegramUpdate(update_id=22, chat_id=777, user_id=123456789, text="привет")]
    transport = FakeTransport(updates)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=22),
        handler=lambda text, chat_id, status_callback: (
            status_callback("thinking"),
            status_callback("still-thinking"),
            "ok",
        )[-1],
    )
    ticks = iter((100.0, 101.0))

    monkeypatch.setattr("core.telegram.telegram_service.time.monotonic", lambda: next(ticks))

    results = service.poll_once()

    assert results[0].handled is True
    assert transport.sent_chat_actions == [(777, "typing")]
    assert transport.sent_messages == [(777, "ok")]


def test_pause_for_reset_closes_transport_and_blocks_offset_persistence() -> None:
    transport = FakeTransport([])
    offset_store = FakeOffsetStore(offset=500)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=lambda text: f"ok:{text}",
    )
    service._pending_update_ids_set.add(500)  # noqa: SLF001
    service.pause_for_reset()

    service._finalize_dispatch_result(  # noqa: SLF001
        TelegramDispatchResult(
            update_id=500,
            chat_id=777,
            user_id=123456789,
            authorized=True,
            handled=True,
            reply_text="ok",
        )
    )

    assert transport.closed is True
    assert offset_store.saved == []
    assert service.poll_once(async_dispatch=False) == []


def test_telegram_service_send_test_message_uses_configured_user_id() -> None:
    transport = FakeTransport([])
    service = TelegramService(
        FakeSettings(telegram_user_id="987654321", telegram_bot_token="bot_token"),
        transport=transport,
        offset_store=FakeOffsetStore(offset=0),
    )

    assert service.send_test_message() is True
    assert transport.sent_messages == [(987654321, "Тестовое сообщение JARVIS Unity")]


def test_telegram_service_routes_plain_conversation_through_service_container_ai() -> None:
    route = SimpleNamespace(
        kind="ai",
        commands=["как дела?"],
        assistant_lines=[],
        queue_items=["как дела?"],
        execution_result=None,
    )
    updates = [TelegramUpdate(update_id=31, chat_id=777, user_id=123456789, text="как дела?")]
    transport = FakeTransport(updates)

    class Router:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def handle(self, text: str, *, source: str = "ui", telegram_chat_id: str = ""):  # noqa: ANN201
            self.calls.append((text, source, telegram_chat_id))
            return route

    class Ai:
        def __init__(self) -> None:
            self.received: list[tuple[str, list[dict[str, str]]]] = []

        def generate_reply_result(self, text: str, history: list[dict[str, str]], *, status_callback=None):  # noqa: ANN001, ANN201
            self.received.append((text, history))
            if "отвечай полностью по-русски" in text.casefold():
                return SimpleNamespace(text="Как дела? Всё нормально.")
            return SimpleNamespace(text="Как дела? how?")

    runtime = ServiceContainer.__new__(ServiceContainer)
    runtime._command_router = Router()
    runtime._ai = Ai()
    runtime._telegram_history_lock = threading.RLock()
    runtime._telegram_history_by_chat_id = {}
    runtime._telegram_history_limit = 12

    def external_handler(text: str, chat_id: str) -> str:
        return ServiceContainer.handle_external_command(runtime, text, telegram_chat_id=chat_id)

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=31),
        handler=external_handler,
    )

    results = service.poll_once()

    assert results[0].handled is True
    assert results[0].reply_text == "Как дела? Всё нормально."
    assert runtime._command_router.calls == [("как дела?", "telegram", "777")]
    assert runtime._ai.received[0][0].startswith("Ты отвечаешь в Telegram как JARVIS.")
    assert "Если пользователь пишет по-русски, отвечай полностью по-русски." in runtime._ai.received[0][0]
    assert transport.sent_messages == [(777, "Как дела? Всё нормально.")]


def test_empty_handler_reply_uses_fallback_text_instead_of_silent_drop() -> None:
    updates = [TelegramUpdate(update_id=60, chat_id=777, user_id=123456789, text="hello")]
    transport = FakeTransport(updates)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=60),
        handler=lambda _text: "",
    )

    results = service.poll_once()

    assert results[0].authorized is True
    assert results[0].handled is True
    assert results[0].reply_text
    assert transport.sent_messages == [(777, results[0].reply_text)]


def test_send_failure_is_not_reported_as_success() -> None:
    updates = [TelegramUpdate(update_id=61, chat_id=777, user_id=123456789, text="open music")]
    transport = FakeTransport(updates, fail_send_message=RuntimeError("send down"))
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=61),
        handler=lambda _text: "done",
    )

    results = service.poll_once()

    assert results[0].authorized is True
    assert results[0].handled is False
    assert "RuntimeError" in (results[0].error or "")
    assert transport.sent_messages == []


def test_async_dispatch_does_not_silently_drop_later_updates() -> None:
    updates = [
        TelegramUpdate(update_id=100 + idx, chat_id=777, user_id=123456789, text=f"cmd {idx}")
        for idx in range(20)
    ]
    transport = FakeTransport(updates)

    def slow_handler(text: str) -> str:
        time.sleep(0.08)
        return f"ok:{text}"

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=100),
        handler=slow_handler,
    )

    started_at = time.perf_counter()
    queued = service.poll_once(async_dispatch=True)
    elapsed = time.perf_counter() - started_at

    assert len(queued) == 20
    assert all(item.error == "queued" for item in queued)
    assert elapsed < 0.5
    assert service.pending_dispatches() > 0

    deadline = time.perf_counter() + 6.0
    while time.perf_counter() < deadline and service.pending_dispatches() > 0:
        time.sleep(0.03)

    assert service.pending_dispatches() == 0
    assert service.can_poll_now() is True
    assert len(transport.sent_messages) == 20


def test_async_dispatch_retries_failed_update_before_acknowledging_it() -> None:
    updates = [TelegramUpdate(update_id=300, chat_id=777, user_id=123456789, text="cmd retry")]
    transport = FakeTransport(updates, fail_send_message=RuntimeError("send down"))
    offset_store = FakeOffsetStore(offset=300)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=lambda text: f"ok:{text}",
    )

    queued = service.poll_once(async_dispatch=True)
    assert queued[0].error == "queued"

    deadline = time.perf_counter() + 3.0
    while time.perf_counter() < deadline and service.pending_dispatches() > 0:
        time.sleep(0.01)

    assert service.pending_dispatches() == 0
    assert transport.sent_messages == []
    assert offset_store.saved == []
    assert transport.requested_offsets == [300]

    transport.fail_send_message = None

    results = service.poll_once(async_dispatch=False)

    assert results[0].handled is True
    assert transport.sent_messages == [(777, "ok:cmd retry")]
    assert offset_store.saved[-1] == 301
    assert transport.requested_offsets == [300, 300]


def test_telegram_service_bootstraps_missing_offset_without_replaying_backlog() -> None:
    backlog = [
        TelegramUpdate(update_id=40, chat_id=777, user_id=123456789, text="old 1"),
        TelegramUpdate(update_id=41, chat_id=777, user_id=123456789, text="old 2"),
    ]
    transport = FakeTransport(backlog)
    offset_store = FakeOffsetStore(offset=None)
    received: list[str] = []

    def handler(text: str) -> str:
        received.append(text)
        return f"ok:{text}"

    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=handler,
    )

    first_results = service.poll_once()

    assert first_results == []
    assert received == []
    assert transport.sent_messages == []
    assert offset_store.saved == [42]
    assert transport.requested_offsets == [None]

    transport.updates = [TelegramUpdate(update_id=42, chat_id=777, user_id=123456789, text="fresh")]

    second_results = service.poll_once()

    assert received == ["fresh"]
    assert second_results[0].handled is True
    assert transport.sent_messages == [(777, "ok:fresh")]
    assert offset_store.saved[-1] == 43
    assert transport.requested_offsets == [None, 42]


def test_async_dispatch_exception_releases_pending_update_and_does_not_ack() -> None:
    transport = FakeTransport([])
    offset_store = FakeOffsetStore(offset=400)
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=offset_store,
        handler=lambda text: f"ok:{text}",
    )
    service._pending_update_ids_set.add(401)  # noqa: SLF001
    service._inflight_dispatches = 1  # noqa: SLF001
    service._offset = 400  # noqa: SLF001

    future: Future[TelegramDispatchResult] = Future()
    future.set_exception(RuntimeError("boom"))

    service._dispatch_done(future, 401)  # noqa: SLF001

    assert service.pending_dispatches() == 0
    assert 401 not in service._pending_update_ids_set  # noqa: SLF001
    assert offset_store.saved == []
    assert "RuntimeError" in service.last_error()


def test_http_transport_timeout_falls_back_on_invalid_network_setting() -> None:
    class Settings:
        def get_registration(self) -> dict[str, str]:
            return {"telegram_user_id": "123456789", "telegram_bot_token": "bot_token"}

        def get(self, key: str, default=None):  # noqa: ANN001, ANN201
            if key == "network":
                return {"timeout_seconds": "bad"}
            return default

    service = TelegramService(
        Settings(),
        transport=None,
        offset_store=FakeOffsetStore(offset=0),
    )

    transport = service._create_http_transport("bot_token")  # noqa: SLF001

    assert transport is not None
    assert transport.timeout_seconds == 12.0


def test_duplicate_update_ids_are_deduped_before_dispatch() -> None:
    updates = [
        TelegramUpdate(update_id=500, chat_id=777, user_id=123456789, text="open youtube"),
        TelegramUpdate(update_id=500, chat_id=777, user_id=123456789, text="open youtube"),
    ]
    transport = FakeTransport(updates)
    handled: list[str] = []
    service = TelegramService(
        FakeSettings(),
        transport=transport,
        offset_store=FakeOffsetStore(offset=500),
        handler=lambda text: handled.append(text) or "ok",
    )

    results = service.poll_once()

    assert len(results) == 1
    assert handled == ["open youtube"]
    assert transport.sent_messages == [(777, "ok")]

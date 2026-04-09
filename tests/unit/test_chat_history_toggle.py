from __future__ import annotations

import json
from types import SimpleNamespace

from core.settings.settings_store import DEFAULT_SETTINGS
from ui.bridge.chat_bridge import ChatBridge


class InMemorySettings:
    def __init__(self) -> None:
        self.payload = json.loads(json.dumps(DEFAULT_SETTINGS))

    def get(self, key: str, default=None):  # noqa: ANN001
        return self.payload.get(key, default)

    def set(self, key: str, value):  # noqa: ANN001
        self.payload[key] = value


class HistoryStore:
    def __init__(self) -> None:
        self.saved: list[list[dict[str, object]]] = []
        self.cleared = 0

    def load(self) -> list[dict[str, object]]:
        return []

    def save(self, messages: list[dict[str, object]]) -> None:
        self.saved.append(list(messages))

    def clear(self) -> None:
        self.cleared += 1


class Services:
    def __init__(self) -> None:
        self.settings = InMemorySettings()
        self.chat_history = HistoryStore()
        self.command_router = SimpleNamespace(
            handle=lambda text: SimpleNamespace(kind="local", commands=[text], assistant_lines=["ok"], queue_items=[text], execution_result=None)
        )
        self.actions = SimpleNamespace(quick_actions=lambda: [], app_catalog=lambda: [])
        self.ai = SimpleNamespace(generate_reply=lambda text, history: "ok")
        self.voice = SimpleNamespace(voice_response_enabled=lambda: False, speak=lambda text, force=False: "ok")


def test_chat_history_toggle_prevents_new_writes() -> None:
    services = Services()
    bridge = ChatBridge(SimpleNamespace(status="Готов"), services, app_bridge=None)

    bridge.saveHistoryEnabled = False
    bridge.sendMessage("привет")

    assert bridge.saveHistoryEnabled is False
    assert services.chat_history.saved == []
    assert [message["role"] for message in bridge.messages][-2:] == ["user", "assistant"]

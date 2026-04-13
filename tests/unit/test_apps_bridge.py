from __future__ import annotations

from types import SimpleNamespace

from ui.bridge.apps_bridge import AppsBridge


class _Actions:
    def __init__(self) -> None:
        self.catalog_calls = 0
        self.pinned_calls = 0

    def app_catalog(self) -> list[dict[str, str]]:
        self.catalog_calls += 1
        return []

    def pinned_commands(self) -> list[dict[str, str]]:
        self.pinned_calls += 1
        return []


class _ChatBridge:
    def __init__(self) -> None:
        self.refreshes = 0

    def refreshCatalog(self) -> None:
        self.refreshes += 1


def test_apps_bridge_prewarm_touches_catalog_without_refreshing_chat() -> None:
    actions = _Actions()
    services = SimpleNamespace(actions=actions)
    bridge = AppsBridge(services=services, chat_bridge=_ChatBridge())

    bridge.prewarm()

    assert actions.catalog_calls == 1
    assert actions.pinned_calls == 1


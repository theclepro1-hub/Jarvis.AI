from __future__ import annotations

from types import SimpleNamespace

from core.version import DEFAULT_VERSION
from ui.bridge.app_bridge import AppBridge


class _Signal:
    def connect(self, _slot) -> None:  # noqa: ANN001
        return None


class _Registration:
    def load(self):  # noqa: ANN201
        return SimpleNamespace(is_complete=True, skipped=False)


class _LockedRegistration:
    def load(self):  # noqa: ANN201
        return SimpleNamespace(is_complete=False, skipped=False)


class _RaisingUpdates:
    @property
    def current_version(self) -> str:
        raise AssertionError("updates service must not be touched for version/title rendering")


class _State:
    def __init__(self) -> None:
        self.currentScreen = "chat"
        self.status = "Готов"
        self.registrationRequired = False
        self.currentScreenChanged = _Signal()
        self.statusChanged = _Signal()
        self.registrationRequiredChanged = _Signal()


class _Services:
    def __init__(self) -> None:
        self.registration = _Registration()
        self.updates = _RaisingUpdates()


class _LockedServices:
    def __init__(self) -> None:
        self.registration = _LockedRegistration()
        self.updates = _RaisingUpdates()


def test_app_bridge_version_is_constant_and_does_not_touch_updates() -> None:
    bridge = AppBridge(_State(), _Services())

    assert bridge.version == DEFAULT_VERSION
    assert bridge.currentScreen == "chat"


def test_app_bridge_navigation_is_noop_for_voice_and_apps_when_registration_required() -> None:
    state = _State()
    bridge = AppBridge(state, _LockedServices())

    assert bridge.registrationRequired is True
    assert bridge.currentScreen == "registration"

    bridge.navigate("voice")
    assert bridge.currentScreen == "registration"

    bridge.navigate("apps")
    assert bridge.currentScreen == "registration"

    bridge.navigate("settings")
    assert bridge.currentScreen == "settings"

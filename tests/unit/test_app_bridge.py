from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

from core.version import DEFAULT_VERSION, DISPLAY_VERSION, UPDATE_VERSION
from ui.bridge.app_bridge import AppBridge


class _Signal:
    def connect(self, _slot) -> None:  # noqa: ANN001
        return None


class _Registration:
    def load(self):  # noqa: ANN201
        return SimpleNamespace(is_complete=True, skipped=False)

    def is_complete(self, registration) -> bool:  # noqa: ANN001
        return bool(getattr(registration, "is_complete", False))


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


def test_app_bridge_version_is_constant_and_does_not_touch_updates() -> None:
    bridge = AppBridge(_State(), _Services())

    assert bridge.version == DISPLAY_VERSION == DEFAULT_VERSION
    assert bridge.currentScreen == "chat"


def test_app_version_bridge_uses_display_version_alias() -> None:
    from core.app_identity import WINDOWS_APP_VERSION

    assert DISPLAY_VERSION == DEFAULT_VERSION
    assert UPDATE_VERSION != DISPLAY_VERSION
    assert WINDOWS_APP_VERSION == DISPLAY_VERSION


def test_app_module_import_defers_heavy_startup_dependencies() -> None:
    for module_name in [
        "app.app",
        "core.services.service_container",
        "PySide6.QtGui",
        "PySide6.QtQml",
        "PySide6.QtWidgets",
    ]:
        sys.modules.pop(module_name, None)

    importlib.import_module("app.app")

    assert "core.services.service_container" not in sys.modules
    assert "PySide6.QtGui" not in sys.modules
    assert "PySide6.QtQml" not in sys.modules
    assert "PySide6.QtWidgets" not in sys.modules


def test_chat_bridge_module_import_defers_ai_policy_dependencies() -> None:
    for module_name in [
        "core.ai.reply_text",
        "core.policy.assistant_mode",
        "ui.bridge.chat_bridge",
    ]:
        sys.modules.pop(module_name, None)

    importlib.import_module("ui.bridge.chat_bridge")

    assert "core.ai.reply_text" not in sys.modules
    assert "core.policy.assistant_mode" not in sys.modules

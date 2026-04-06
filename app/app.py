from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine

from core.services.service_container import ServiceContainer
from core.state.app_state import AppState
from ui.bridge.app_bridge import AppBridge
from ui.bridge.apps_bridge import AppsBridge
from ui.bridge.chat_bridge import ChatBridge
from ui.bridge.registration_bridge import RegistrationBridge
from ui.bridge.settings_bridge import SettingsBridge
from ui.bridge.voice_bridge import VoiceBridge


def _boot_log(message: str) -> None:
    if os.environ.get("JARVIS_UNITY_BOOT_LOG") != "1":
        return
    try:
        log_path = Path.home() / "AppData" / "Local" / "JarvisAi_Unity" / "bootstrap.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def _load_embedded_fonts() -> None:
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    if not fonts_dir.exists():
        return
    for font_path in fonts_dir.glob("*.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _boot_log(f"app:font-loaded:{font_path.name}:{','.join(families)}")


class JarvisUnityApplication:
    def __init__(self, qapp) -> None:
        _boot_log("app:init:begin")
        self.qapp = qapp
        _load_embedded_fonts()
        _boot_log("app:init:fonts")
        self.services = ServiceContainer()
        _boot_log("app:init:services")
        self.state = AppState()
        _boot_log("app:init:state")
        self.engine = QQmlApplicationEngine()
        _boot_log("app:init:engine")

        self.app_bridge = AppBridge(self.state, self.services)
        _boot_log("app:init:app-bridge")
        self.chat_bridge = ChatBridge(self.state, self.services, self.app_bridge)
        _boot_log("app:init:chat-bridge")
        self.apps_bridge = AppsBridge(self.services, self.chat_bridge)
        _boot_log("app:init:apps-bridge")
        self.voice_bridge = VoiceBridge(self.state, self.services, self.chat_bridge)
        _boot_log("app:init:voice-bridge")
        self.settings_bridge = SettingsBridge(self.state, self.services, self.app_bridge)
        _boot_log("app:init:settings-bridge")
        self.registration_bridge = RegistrationBridge(self.state, self.services, self.app_bridge)
        _boot_log("app:init:registration-bridge")

    def start(self) -> None:
        _boot_log("app:start:begin")
        self.qapp.aboutToQuit.connect(self.voice_bridge.shutdown)
        root_context = self.engine.rootContext()
        _boot_log("app:start:root-context")
        root_context.setContextProperty("appBridge", self.app_bridge)
        root_context.setContextProperty("appsBridge", self.apps_bridge)
        root_context.setContextProperty("chatBridge", self.chat_bridge)
        root_context.setContextProperty("voiceBridge", self.voice_bridge)
        root_context.setContextProperty("settingsBridge", self.settings_bridge)
        root_context.setContextProperty("registrationBridge", self.registration_bridge)
        _boot_log("app:start:context-properties")

        app_qml = Path(__file__).resolve().parents[1] / "ui" / "qml" / "App.qml"
        _boot_log(f"app:start:load:{app_qml}")
        self.engine.load(QUrl.fromLocalFile(str(app_qml)))
        _boot_log("app:start:after-load")
        if not self.engine.rootObjects():
            raise RuntimeError("Failed to load App.qml")
        _boot_log("app:start:root-objects")
        if os.environ.get("JARVIS_UNITY_DISABLE_WAKE") != "1":
            QTimer.singleShot(250, self.voice_bridge.startWakeRuntime)
            _boot_log("app:start:wake-scheduled")

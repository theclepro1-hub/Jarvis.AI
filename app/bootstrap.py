from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon

from app.app import JarvisUnityApplication


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


def bootstrap() -> int:
    _boot_log("bootstrap:begin")
    QGuiApplication.setOrganizationName("theclepro1")
    QGuiApplication.setOrganizationDomain("jarvisai.unity")
    QGuiApplication.setApplicationName("JarvisAi Unity")
    _boot_log("bootstrap:before-app")
    application = QGuiApplication(sys.argv)
    _boot_log("bootstrap:after-app")
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "icons" / "jarvis_unity.ico"
    if icon_path.exists():
        _boot_log(f"bootstrap:icon:{icon_path}")
        application.setWindowIcon(QIcon(str(icon_path)))
    runtime = JarvisUnityApplication(application)
    _boot_log("bootstrap:after-runtime-init")
    runtime.start()
    _boot_log("bootstrap:after-runtime-start")
    return application.exec()

from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from app.app import JarvisUnityApplication
from core.services.single_instance import SingleInstanceService

WINDOWS_APP_USER_MODEL_ID = "theclepro1.JarvisAiUnity"


def _boot_log(message: str) -> None:
    if os.environ.get("JARVIS_UNITY_BOOT_LOG") != "1":
        return
    try:
        start_ns = int(os.environ.get("JARVIS_UNITY_BOOT_T0_NS", "0") or "0")
        elapsed_ms = 0.0
        if start_ns > 0:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        log_path = Path.home() / "AppData" / "Local" / "JarvisAi_Unity" / "bootstrap.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{elapsed_ms:9.2f} ms] {message}\n")
    except Exception:
        pass


def _set_windows_app_user_model_id() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_USER_MODEL_ID)
        _boot_log(f"bootstrap:appusermodelid:{WINDOWS_APP_USER_MODEL_ID}")
    except Exception as exc:  # noqa: BLE001
        _boot_log(f"bootstrap:appusermodelid-failed:{exc!r}")


def bootstrap() -> int:
    os.environ.setdefault("JARVIS_UNITY_BOOT_T0_NS", str(time.perf_counter_ns()))
    _boot_log("bootstrap:begin")
    QGuiApplication.setOrganizationName("theclepro1")
    QGuiApplication.setOrganizationDomain("jarvisai.unity")
    QGuiApplication.setApplicationName("JarvisAi Unity")
    _set_windows_app_user_model_id()
    _boot_log("bootstrap:before-app")
    application = QApplication(sys.argv)
    application.setQuitOnLastWindowClosed(False)
    _boot_log("bootstrap:after-app")
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "icons" / "jarvis_unity.ico"
    if icon_path.exists():
        _boot_log(f"bootstrap:icon:{icon_path}")
        application.setWindowIcon(QIcon(str(icon_path)))
    start_minimized = any(arg in {"--minimized", "--start-minimized", "--tray"} for arg in sys.argv[1:])
    single_instance = SingleInstanceService()
    if not single_instance.ensure_primary_instance():
        _boot_log("bootstrap:second-instance")
        return 0
    runtime = JarvisUnityApplication(application, start_minimized=start_minimized, single_instance=single_instance)
    _boot_log("bootstrap:after-runtime-init")
    runtime.start()
    _boot_log("bootstrap:after-runtime-start")
    return application.exec()

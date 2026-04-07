from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path


class StartupManager:
    KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    VALUE_NAME = "JarvisAi_Unity"

    def is_enabled(self) -> bool:
        if os.environ.get("JARVIS_UNITY_DISABLE_STARTUP_REGISTRY") == "1":
            return False
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY_PATH, 0, winreg.KEY_READ) as key:
            try:
                value, _value_type = winreg.QueryValueEx(key, self.VALUE_NAME)
            except FileNotFoundError:
                return False
        return bool(str(value).strip())

    def set_enabled(self, enabled: bool, *, minimized: bool = True) -> None:
        if os.environ.get("JARVIS_UNITY_DISABLE_STARTUP_REGISTRY") == "1":
            return
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, self.VALUE_NAME, 0, winreg.REG_SZ, self._command(minimized=minimized))
                return
            try:
                winreg.DeleteValue(key, self.VALUE_NAME)
            except FileNotFoundError:
                return

    def _command(self, *, minimized: bool = True) -> str:
        suffix = " --minimized" if minimized else ""
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable)}"{suffix}'

        interpreter = Path(sys.executable)
        pythonw = interpreter.with_name("pythonw.exe")
        if pythonw.exists():
            interpreter = pythonw
        main_py = Path(__file__).resolve().parents[2] / "app" / "main.py"
        return f'"{interpreter}" "{main_py}"{suffix}'

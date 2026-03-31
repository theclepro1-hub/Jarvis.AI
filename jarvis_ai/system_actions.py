from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

from .branding import APP_LOGGER_NAME
from .commands import find_dynamic_entry, get_dynamic_entry_by_key
from .state import CONFIG, LOCAL_APPDATA, ROAMING_APPDATA, USER_PROFILE
from .structured_logging import log_event


logger = logging.getLogger(APP_LOGGER_NAME)
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyautogui
except ImportError:
    pyautogui = None


def open_browser(url: str) -> None:
    target = str(url or "").strip()
    if not target:
        return
    if sys.platform == "win32":
        try:
            os.startfile(target)
            return
        except OSError as exc:
            log_event(logger, "actions", "os_startfile_failed", level=logging.WARNING, target=target, error=str(exc))
        try:
            subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=CREATE_NO_WINDOW)
            return
        except OSError as exc:
            log_event(logger, "actions", "cmd_start_failed", level=logging.WARNING, target=target, error=str(exc))
    webbrowser.open(target, new=2)


def open_url_search(query: str) -> None:
    q = str(query or "").strip()
    open_browser("https://www.google.com/search?q=" + quote_plus(q) if q else "https://www.google.com")


def maybe_press(key: str, presses: int = 1, interval: float = 0.02) -> bool:
    if pyautogui is None:
        return False
    try:
        pyautogui.press(key, presses=max(1, int(presses)), interval=max(0.0, float(interval)))
    except TypeError:
        for _ in range(max(1, int(presses))):
            pyautogui.press(key)
            if interval:
                time.sleep(interval)
    return True


def get_time_text() -> str:
    return datetime.now().strftime("%H:%M")


def get_date_text() -> str:
    return datetime.now().strftime("%d.%m.%Y")


def _first_existing_path(candidates) -> Optional[str]:
    seen = set()
    for raw in candidates or []:
        raw_text = str(raw or "").strip().strip('"')
        if not raw_text:
            continue
        path = os.path.normpath(raw_text)
        if not path or path == ".":
            continue
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        if os.path.exists(path):
            return path
    return None


def _query_windows_app_path(exe_name: str) -> Optional[str]:
    name = str(exe_name or "").strip()
    if not name:
        return None
    try:
        import winreg
    except ImportError:
        return None

    subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}"
    views = [0]
    for view_flag in (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
        if view_flag and view_flag not in views:
            views.append(view_flag)

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in views:
            try:
                key = winreg.OpenKey(winreg.ConnectRegistry(None, root), subkey, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            try:
                direct = str(winreg.QueryValueEx(key, "")[0] or "").strip()
            except OSError:
                direct = ""
            try:
                base_dir = str(winreg.QueryValueEx(key, "Path")[0] or "").strip()
            except OSError:
                base_dir = ""
            try:
                winreg.CloseKey(key)
            except OSError:
                pass
            resolved = _first_existing_path(
                [
                    direct,
                    os.path.join(base_dir, name) if base_dir else "",
                ]
            )
            if resolved:
                return resolved
    return None


def _find_latest_localapp_exe(root_dir: str, exe_name: str) -> Optional[str]:
    base = str(root_dir or "").strip()
    name = str(exe_name or "").strip()
    if not base or not name:
        return None
    pattern = os.path.join(base, "app-*", name)
    candidates = sorted(glob.glob(pattern), reverse=True)
    return _first_existing_path(candidates)


@lru_cache(maxsize=32)
def find_steam_path():
    candidates = []
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        candidates.append(winreg.QueryValueEx(key, "SteamExe")[0])
        winreg.CloseKey(key)
    except (ImportError, OSError):
        pass
    candidates.extend(
        [
            _query_windows_app_path("Steam.exe"),
            CONFIG.get("steam_path", ""),
            r"C:\Program Files (x86)\Steam\Steam.exe",
            r"C:\Program Files\Steam\Steam.exe",
        ]
    )
    return _first_existing_path(candidates) or CONFIG["steam_path"]


@lru_cache(maxsize=32)
def find_discord_path():
    candidates = [
        _query_windows_app_path("Discord.exe"),
        _find_latest_localapp_exe(os.path.join(LOCAL_APPDATA, "Discord"), "Discord.exe"),
    ]
    candidates.extend(CONFIG.get("discord_candidates", []))
    candidates.append(os.path.join(LOCAL_APPDATA, r"Discord\Discord.exe"))
    return _first_existing_path(candidates)


@lru_cache(maxsize=32)
def find_fortnite_launcher():
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Fortnite")
        path = winreg.QueryValueEx(key, "InstallLocation")[0]
        launcher = os.path.join(path, "FortniteLauncher.exe")
        if os.path.exists(launcher):
            return launcher
    except (ImportError, OSError):
        pass
    for root in CONFIG["fortnite_roots"]:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.lower() == "fortnitelauncher.exe":
                    return os.path.join(dirpath, filename)
    epic = CONFIG["epic_launcher_path"]
    if epic and os.path.exists(epic):
        return epic
    default = os.path.join(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        "Epic Games",
        "Launcher",
        "Portal",
        "Binaries",
        "Win64",
        "EpicGamesLauncher.exe",
    )
    return default if os.path.exists(default) else None


@lru_cache(maxsize=32)
def find_telegram_path():
    candidates = []
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Telegram Desktop")
        candidates.append(winreg.QueryValueEx(key, "DisplayIcon")[0])
        winreg.CloseKey(key)
    except (ImportError, OSError):
        pass
    candidates.extend(
        [
            _query_windows_app_path("Telegram.exe"),
            CONFIG.get("telegram_desktop_path", ""),
            os.path.join(ROAMING_APPDATA, r"Telegram Desktop\Telegram.exe"),
            os.path.join(LOCAL_APPDATA, r"Telegram Desktop\Telegram.exe"),
        ]
    )
    return _first_existing_path(candidates) or CONFIG["telegram_desktop_path"]


def refresh_known_app_launchers():
    global STEAM_PATH, DISCORD_PATH, FORTNITE_LAUNCHER, TELEGRAM_PATH

    for finder in (find_steam_path, find_discord_path, find_fortnite_launcher, find_telegram_path):
        try:
            finder.cache_clear()
        except AttributeError:
            pass
    STEAM_PATH = find_steam_path()
    DISCORD_PATH = find_discord_path()
    FORTNITE_LAUNCHER = find_fortnite_launcher()
    TELEGRAM_PATH = find_telegram_path()


def _repair_missing_launch_target(target: str) -> Optional[str]:
    raw = str(target or "").strip().strip('"')
    if not raw:
        return None
    if os.path.exists(raw):
        return raw

    basename = os.path.basename(raw) or raw
    lowered = basename.lower()
    if lowered == "steam.exe":
        return find_steam_path()
    if lowered == "discord.exe":
        return find_discord_path()
    if lowered == "telegram.exe":
        return find_telegram_path()
    if lowered in {"fortnitelauncher.exe", "epicgameslauncher.exe"}:
        return find_fortnite_launcher()

    direct = _query_windows_app_path(basename)
    if direct:
        return direct

    which_hit = shutil.which(raw) or shutil.which(basename)
    if which_hit and os.path.exists(which_hit):
        return which_hit
    return None


def launch_target(target, is_uri=False):
    try:
        if is_uri:
            if re.match(r"^[a-z0-9_\-\.]+$", str(target or ""), re.I):
                subprocess.Popen([target], creationflags=CREATE_NO_WINDOW)
            else:
                os.startfile(target)
            return True
        resolved_target = _repair_missing_launch_target(target)
        if resolved_target and os.path.exists(resolved_target):
            subprocess.Popen([resolved_target], creationflags=CREATE_NO_WINDOW)
            return True
        log_event(logger, "actions", "launch_target_missing", level=logging.WARNING, target=str(target or ""))
        return False
    except Exception as exc:
        log_event(logger, "actions", "launch_target_failed", level=logging.ERROR, target=str(target or ""), error=str(exc))
        return False


def launch_dynamic_entry(entry: Dict[str, Any]) -> bool:
    if not isinstance(entry, dict):
        return False
    target = str(entry.get("launch", "")).strip()
    if not target:
        return False
    if re.match(r"^[a-z][a-z0-9+\-.]*://", target, re.I):
        return launch_target(target, is_uri=True)
    return launch_target(target, is_uri=False)


def open_music():
    if launch_target(CONFIG["yandex_music_path"]):
        time.sleep(1.2)
        if pyautogui:
            pyautogui.press("space")
    else:
        raise FileNotFoundError("Yandex Music not found")


def open_steam():
    if not launch_target(STEAM_PATH):
        launch_target("steam://open/main", is_uri=True)


def open_discord():
    if DISCORD_PATH:
        launch_target(DISCORD_PATH)
    else:
        launch_target("discord://", is_uri=True)


def open_fortnite():
    if FORTNITE_LAUNCHER:
        if "EpicGamesLauncher.exe" in FORTNITE_LAUNCHER:
            subprocess.Popen([FORTNITE_LAUNCHER, "-launch", "Fortnite"], creationflags=CREATE_NO_WINDOW)
        else:
            subprocess.Popen([FORTNITE_LAUNCHER], creationflags=CREATE_NO_WINDOW)
    else:
        launch_target("com.epicgames.launcher://apps/Fortnite?action=launch", is_uri=True)


def open_telegram():
    if not launch_target(TELEGRAM_PATH):
        launch_target("tg://", is_uri=True)


def close_app(key: str):
    exes = list(APP_CLOSE_EXES.get(key, []))
    if not exes:
        dynamic_entry = get_dynamic_entry_by_key(key) or find_dynamic_entry(str(key))
        if dynamic_entry:
            exes = list(dynamic_entry.get("close_exes", []) or [])
            if not exes:
                launch_target_path = str(dynamic_entry.get("launch", "")).strip()
                if launch_target_path and "://" not in launch_target_path:
                    exes = [os.path.basename(launch_target_path)]
    if not exes:
        return False
    if psutil is None:
        for exe in exes:
            try:
                subprocess.Popen(["taskkill", "/f", "/im", exe], creationflags=CREATE_NO_WINDOW)
            except OSError as exc:
                log_event(logger, "actions", "taskkill_failed", level=logging.WARNING, exe=exe, error=str(exc))
        return bool(exes)
    lower_exes = [exe.lower() for exe in exes]
    killed = False
    for proc in psutil.process_iter(["name", "status"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() in lower_exes and proc.info["status"] != psutil.STATUS_ZOMBIE:
                proc.kill()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def open_dbd():
    launch_target("steam://rungameid/381210", is_uri=True)


def open_cs2():
    launch_target("steam://rungameid/730", is_uri=True)


def open_deadlock():
    launch_target("steam://rungameid/1422450", is_uri=True)


def open_settings():
    launch_target("ms-settings:", is_uri=True)


def open_notepad():
    launch_target("notepad", is_uri=True)


def open_calc():
    launch_target("calc", is_uri=True)


def open_taskmgr():
    launch_target("taskmgr", is_uri=True)


def open_explorer():
    launch_target("explorer.exe", is_uri=True)


def open_downloads():
    subprocess.Popen(["explorer.exe", os.path.join(USER_PROFILE, "Downloads")], creationflags=CREATE_NO_WINDOW)


def open_documents():
    subprocess.Popen(["explorer.exe", os.path.join(USER_PROFILE, "Documents")], creationflags=CREATE_NO_WINDOW)


def open_desktop():
    subprocess.Popen(["explorer.exe", os.path.join(USER_PROFILE, "Desktop")], creationflags=CREATE_NO_WINDOW)


def lock_pc():
    subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], creationflags=CREATE_NO_WINDOW)


def restart_explorer():
    subprocess.Popen(["taskkill", "/f", "/im", "explorer.exe"], creationflags=CREATE_NO_WINDOW)
    time.sleep(0.7)
    subprocess.Popen(["explorer.exe"], creationflags=CREATE_NO_WINDOW)


def restart_pc():
    subprocess.Popen(["shutdown", "/r", "/t", "5", "/f"], creationflags=CREATE_NO_WINDOW)


def shutdown_pc():
    subprocess.Popen(["shutdown", "/s", "/t", "5", "/f"], creationflags=CREATE_NO_WINDOW)


def open_youtube():
    open_browser("https://youtube.com")


def open_ozon():
    open_browser("https://ozon.ru")


def open_wildberries():
    open_browser("https://www.wildberries.ru")


def open_twitch():
    open_browser("https://www.twitch.tv/")


def open_roblox():
    if not launch_target("roblox://", is_uri=True):
        open_browser("https://www.roblox.com/")


def open_weather():
    open_browser("https://yandex.ru/pogoda/")


APP_CLOSE_EXES = {
    "music": ["YandexMusic.exe", "YandexMusic"],
    "browser": ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe"],
    "steam": ["steam.exe", "steamwebhelper.exe"],
    "discord": ["Discord.exe", "Update.exe"],
    "telegram": ["Telegram.exe"],
    "notepad": ["notepad.exe"],
    "calc": ["CalculatorApp.exe", "calc.exe"],
    "taskmgr": ["Taskmgr.exe", "taskmgr.exe"],
    "explorer": ["explorer.exe"],
    "fortnite": ["FortniteLauncher.exe", "EpicGamesLauncher.exe"],
}

APP_OPEN_FUNCS = {
    "music": open_music,
    "youtube": open_youtube,
    "ozon": open_ozon,
    "wildberries": open_wildberries,
    "browser": lambda: open_browser("https://www.google.com"),
    "cs2": open_cs2,
    "fortnite": open_fortnite,
    "dbd": open_dbd,
    "deadlock": open_deadlock,
    "steam": open_steam,
    "settings": open_settings,
    "twitch": open_twitch,
    "roblox": open_roblox,
    "discord": open_discord,
    "notepad": open_notepad,
    "calc": open_calc,
    "taskmgr": open_taskmgr,
    "explorer": open_explorer,
    "downloads": open_downloads,
    "documents": open_documents,
    "desktop": open_desktop,
    "restart_explorer": restart_explorer,
    "telegram": open_telegram,
}


refresh_known_app_launchers()


__all__ = [
    "APP_CLOSE_EXES",
    "APP_OPEN_FUNCS",
    "CREATE_NO_WINDOW",
    "close_app",
    "get_date_text",
    "get_time_text",
    "launch_dynamic_entry",
    "launch_target",
    "lock_pc",
    "maybe_press",
    "open_browser",
    "open_url_search",
    "open_weather",
    "refresh_known_app_launchers",
    "restart_pc",
    "shutdown_pc",
]

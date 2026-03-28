import ctypes
import os
import re
import sys

from .branding import APP_WINDOWS_APP_ID

_RUNTIME_ROOT_SENTINELS = (
    ("jarvis_ai", "branding.py"),
    ("publish_tools",),
    ("scripts",),
    ("updates.json",),
)


def _candidate_runtime_roots():
    candidates = []

    def _add(path: str):
        full = os.path.abspath(path)
        if full not in candidates:
            candidates.append(full)

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        _add(exe_dir)
        _add(os.path.dirname(exe_dir))

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        _add(meipass)
        _add(os.path.dirname(os.path.abspath(meipass)))

    module_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _add(module_root)
    _add(os.path.dirname(module_root))

    if not getattr(sys, "frozen", False):
        script_dir = os.path.abspath(os.path.dirname(sys.argv[0])) if sys.argv and sys.argv[0] else module_root
        _add(script_dir)
        _add(os.path.dirname(script_dir))

    return candidates


def _looks_like_runtime_root(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    return all(os.path.exists(os.path.join(path, *parts)) for parts in _RUNTIME_ROOT_SENTINELS)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)


def runtime_root_path(*parts):
    base_path = None
    for candidate in _candidate_runtime_roots():
        if _looks_like_runtime_root(candidate):
            base_path = candidate
            break
    if base_path is None:
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not parts:
        return base_path
    return os.path.join(base_path, *parts)


def set_windows_app_id(app_id: str = APP_WINDOWS_APP_ID):
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id or APP_WINDOWS_APP_ID))
    except Exception:
        pass


def parse_geometry(geom: str):
    match = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", (geom or "").strip())
    if not match:
        return None
    return tuple(map(int, match.groups()))

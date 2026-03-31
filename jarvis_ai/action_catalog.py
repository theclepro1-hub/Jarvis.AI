from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    kind: str = "system"
    permission_category: str | None = None
    takes_argument: bool = False


ACTION_SPECS = (
    ActionSpec("music", "запуск приложения (music)", kind="launch", permission_category="launch"),
    ActionSpec("youtube", "открытие сайта (youtube)", kind="web", permission_category="links"),
    ActionSpec("ozon", "открытие сайта (ozon)", kind="web", permission_category="links"),
    ActionSpec("wildberries", "открытие сайта (wildberries)", kind="web", permission_category="links"),
    ActionSpec("browser", "открытие сайта (browser)", kind="web", permission_category="links"),
    ActionSpec("cs2", "запуск приложения (cs2)", kind="launch", permission_category="launch"),
    ActionSpec("fortnite", "запуск приложения (fortnite)", kind="launch", permission_category="launch"),
    ActionSpec("dbd", "запуск приложения (dbd)", kind="launch", permission_category="launch"),
    ActionSpec("deadlock", "запуск приложения (deadlock)", kind="launch", permission_category="launch"),
    ActionSpec("steam", "запуск приложения (steam)", kind="launch", permission_category="launch"),
    ActionSpec("settings", "запуск приложения (settings)", kind="launch", permission_category="launch"),
    ActionSpec("twitch", "открытие сайта (twitch)", kind="web", permission_category="links"),
    ActionSpec("roblox", "запуск приложения (roblox)", kind="launch", permission_category="launch"),
    ActionSpec("discord", "запуск приложения (discord)", kind="launch", permission_category="launch"),
    ActionSpec("notepad", "запуск приложения (notepad)", kind="launch", permission_category="launch"),
    ActionSpec("calc", "запуск приложения (calc)", kind="launch", permission_category="launch"),
    ActionSpec("taskmgr", "запуск приложения (taskmgr)", kind="launch", permission_category="launch"),
    ActionSpec("explorer", "запуск приложения (explorer)", kind="launch", permission_category="launch"),
    ActionSpec("downloads", "запуск приложения (downloads)", kind="launch", permission_category="launch"),
    ActionSpec("documents", "запуск приложения (documents)", kind="launch", permission_category="launch"),
    ActionSpec("desktop", "запуск приложения (desktop)", kind="launch", permission_category="launch"),
    ActionSpec("restart_explorer", "запуск приложения (restart_explorer)", kind="launch", permission_category="launch"),
    ActionSpec("telegram", "запуск приложения (telegram)", kind="launch", permission_category="launch"),
    ActionSpec("open_dynamic_app", "запуск пользовательского действия", kind="launch", permission_category="launch", takes_argument=True),
    ActionSpec("close_app", "закрытие приложения", kind="launch", permission_category="launch", takes_argument=True),
    ActionSpec("shutdown", "выключение ПК", permission_category="power"),
    ActionSpec("restart_pc", "перезагрузка ПК", permission_category="power"),
    ActionSpec("lock", "блокировка экрана", permission_category="power"),
    ActionSpec("media_pause", "пауза воспроизведения", permission_category="input"),
    ActionSpec("media_play", "продолжение воспроизведения", permission_category="input"),
    ActionSpec("media_next", "следующий трек", permission_category="input"),
    ActionSpec("media_prev", "предыдущий трек", permission_category="input"),
    ActionSpec("volume_up", "увеличение громкости", permission_category="input"),
    ActionSpec("volume_down", "уменьшение громкости", permission_category="input"),
    ActionSpec("weather", "открытие погоды в браузере", kind="web", permission_category="links"),
    ActionSpec("search", "поиск в интернете", kind="web", permission_category="links", takes_argument=True),
    ActionSpec("time", "время"),
    ActionSpec("date", "дата"),
    ActionSpec("reminder", "напоминание", takes_argument=True),
    ActionSpec("history", "история"),
    ActionSpec("repeat", "повтор"),
    ActionSpec("timur_son", "timur_son"),
)

ACTION_SPEC_BY_KEY = {spec.key: spec for spec in ACTION_SPECS}
SUPPORTED_ACTION_KEYS = frozenset(ACTION_SPEC_BY_KEY)
WEB_ACTION_KEYS = frozenset(spec.key for spec in ACTION_SPECS if spec.kind == "web")
LAUNCH_ACTION_KEYS = frozenset(spec.key for spec in ACTION_SPECS if spec.permission_category == "launch")


def get_action_spec(action: str) -> ActionSpec | None:
    return ACTION_SPEC_BY_KEY.get(str(action or "").strip().lower())


__all__ = [
    "ACTION_SPECS",
    "ACTION_SPEC_BY_KEY",
    "ActionSpec",
    "LAUNCH_ACTION_KEYS",
    "SUPPORTED_ACTION_KEYS",
    "WEB_ACTION_KEYS",
    "get_action_spec",
]

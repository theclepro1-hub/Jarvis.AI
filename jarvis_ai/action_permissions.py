from __future__ import annotations

from tkinter import messagebox

from .action_catalog import get_action_spec
from .branding import app_brand_name


PERMISSION_CATEGORIES = ("power", "input", "links", "launch", "scripts")
PERMISSION_MODES = ("always", "ask_once", "trust")
DEFAULT_PERMISSION_MODES = {
    "power": "always",
    "input": "ask_once",
    "links": "ask_once",
    "launch": "ask_once",
    "scripts": "always",
}


def normalize_permission_modes(value) -> dict:
    raw = value if isinstance(value, dict) else {}
    normalized = {}
    for category in PERMISSION_CATEGORIES:
        mode = str(raw.get(category, DEFAULT_PERMISSION_MODES[category]) or DEFAULT_PERMISSION_MODES[category]).strip().lower()
        if mode in {"always_run", "always_execute", "always_perform"}:
            mode = "trust"
        if mode not in PERMISSION_MODES:
            mode = DEFAULT_PERMISSION_MODES[category]
        normalized[category] = mode
    return normalized


def category_label(category: str) -> str:
    return {
        "power": "Питание и блокировка",
        "input": "Эмуляция клавиш",
        "links": "Ссылки и браузер",
        "launch": "Запуск приложений",
        "scripts": "Скрипты и внешние проверки",
    }.get(str(category or "").strip().lower(), "Действия")


def category_description(category: str) -> str:
    return {
        "power": "Выключение, перезагрузка и блокировка Windows.",
        "input": "Медиа-клавиши, громкость и другие симулированные нажатия.",
        "links": "Открытие сайтов, поиск в интернете и внешние ссылки.",
        "launch": "Запуск или закрытие локальных приложений и ярлыков.",
        "scripts": "Служебные сценарии, внешние проверки и системные команды.",
    }.get(str(category or "").strip().lower(), "Потенциально опасные действия.")


def permission_action_label(action: str, arg=None) -> str:
    action_text = str(action or "").strip().lower()
    spec = get_action_spec(action_text)
    base = spec.label if spec else (action_text or "действие")
    arg_text = str(arg or "").strip()
    if arg_text and action_text in {"search", "open_dynamic_app", "close_app"}:
        return f"{base}: {arg_text}"
    return base


def permission_category_for_action(action: str) -> str | None:
    spec = get_action_spec(action)
    return spec.permission_category if spec else None


def permission_mode_for_action(config_mgr, action: str) -> str:
    category = permission_category_for_action(action)
    if not category:
        return "trust"
    modes = normalize_permission_modes(getattr(config_mgr, "get_dangerous_action_modes", lambda: {})())
    return modes.get(category, DEFAULT_PERMISSION_MODES[category])


def _ensure_session_allowances(app):
    if not hasattr(app, "_permission_session_allowances"):
        app._permission_session_allowances = set()
    return app._permission_session_allowances


def _ask_permission_with_ui(app, action: str, arg=None, *, category: str, origin: str) -> bool:
    label = permission_action_label(action, arg)
    confirm_in_chat = getattr(app, "request_action_confirmation", None)
    if callable(confirm_in_chat):
        try:
            return bool(
                confirm_in_chat(
                    action=action,
                    arg=arg,
                    label=label,
                    category=category,
                    origin=origin,
                    description=category_description(category),
                )
            )
        except Exception:
            pass

    message = (
        f"Разрешить действие: {label}?\n\n"
        f"Категория: {category_label(category)}\n"
        f"Источник: {origin}\n\n"
        f"{category_description(category)}"
    )
    return bool(messagebox.askyesno(app_brand_name(), message, parent=getattr(app, "root", None)))


def ask_permission(app, action: str, arg=None, *, category: str | None = None, origin: str = "command") -> bool:
    target_category = category or permission_category_for_action(action)
    if not target_category:
        return True
    mode = permission_mode_for_action(app._cfg(), action)
    if mode == "trust":
        return True

    key = f"{target_category}:{str(action or '').strip().lower()}"
    session_allowances = _ensure_session_allowances(app)
    if mode == "ask_once" and key in session_allowances:
        return True

    label = permission_action_label(action, arg)
    allowed = _ask_permission_with_ui(app, action, arg, category=target_category, origin=raw_text(origin))
    if allowed and mode == "ask_once":
        session_allowances.add(key)
    elif not allowed and hasattr(app, "_record_human_log"):
        try:
            app._record_human_log(
                "Действие заблокировано",
                f"JARVIS не выполнил {label}, потому что подтверждение не было выдано.",
                fix="Откройте Система -> Опасные действия и включите режим «Всегда выполнять», если это действие должно выполняться без подтверждения.",
                level="warn",
            )
        except Exception:
            pass
    return allowed


def raw_text(value) -> str:
    text = str(value or "").strip()
    return text or "голос или чат"


__all__ = [
    "DEFAULT_PERMISSION_MODES",
    "PERMISSION_CATEGORIES",
    "PERMISSION_MODES",
    "ask_permission",
    "category_description",
    "category_label",
    "normalize_permission_modes",
    "permission_action_label",
    "permission_category_for_action",
    "permission_mode_for_action",
]

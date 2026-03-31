import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .action_permissions import category_label, permission_mode_for_action
from .commands import find_dynamic_entry, get_dynamic_entry_by_key


def _source_label(source: str) -> str:
    key = str(source or "").strip().lower()
    return {
        "manifest": "манифест custom actions",
        "custom": "пользовательский ярлык",
        "launcher": "список приложений",
        "game": "игровой ярлык",
    }.get(key, key or "локальная запись")


def _launch_target_kind(target: str) -> str:
    value = str(target or "").strip()
    if not value:
        return "неизвестная цель"
    if re.match(r"^[a-z][a-z0-9+\-.]*://", value, re.I):
        scheme = str(urlparse(value).scheme or "").strip().lower()
        if scheme in {"http", "https"}:
            return "сайт в браузере"
        if scheme in {"steam", "discord", "tg", "ms-settings", "mailto"}:
            return "системный URI-вызов"
        return "внешний URI-вызов"
    if os.path.isdir(value):
        return "папка"
    suffix = Path(value).suffix.lower()
    if suffix in {".exe", ".bat", ".cmd", ".ps1", ".lnk"}:
        return "локальная программа или скрипт"
    if "\\" in value or ":" in value or "/" in value:
        return "локальный файл или путь"
    return "системная команда"


def build_action_dry_run_lines(app, *, action: str, arg=None, category: str = "", origin: str = "") -> list[str]:
    action_key = str(action or "").strip().lower()
    target_category = str(category or "").strip().lower()
    lines = ["Сейчас ничего не выполняется. Это только предварительный показ."]

    if action_key == "shutdown":
        lines.extend(
            [
                "После подтверждения будет отправлена системная команда выключения Windows.",
                "Это завершит работу текущего ПК и может закрыть приложения без сохранения данных.",
            ]
        )
    elif action_key == "restart_pc":
        lines.extend(
            [
                "После подтверждения будет отправлена системная команда перезагрузки Windows.",
                "Открытые программы останутся на ответственности Windows и могут закрыться без сохранения.",
            ]
        )
    elif action_key == "lock":
        lines.extend(
            [
                "После подтверждения будет заблокирована текущая сессия Windows.",
                "Приложения не закроются, но экран перейдёт на окно входа.",
            ]
        )
    elif action_key in {"media_pause", "media_play", "media_next", "media_prev"}:
        labels = {
            "media_pause": "Play/Pause",
            "media_play": "Play/Pause",
            "media_next": "Next Track",
            "media_prev": "Previous Track",
        }
        lines.extend(
            [
                f"После подтверждения JARVIS отправит системную медиа-клавишу: {labels.get(action_key, action_key)}.",
                "Это повлияет только на активный медиаплеер или системный аудиостек Windows.",
            ]
        )
    elif action_key in {"volume_up", "volume_down"}:
        direction = "увеличения" if action_key == "volume_up" else "уменьшения"
        lines.extend(
            [
                f"После подтверждения JARVIS отправит серию системных нажатий {direction} громкости.",
                "Меняется только системный уровень звука текущего ПК.",
            ]
        )
    elif action_key == "search":
        query = str(arg or "").strip() or "пустой запрос"
        lines.extend(
            [
                f"После подтверждения откроется браузер и будет выполнен поиск: {query}",
                "Внешний запрос уйдёт в браузер, а не внутрь чата.",
            ]
        )
    elif action_key == "weather":
        lines.extend(
            [
                "После подтверждения откроется страница погоды в браузере.",
                "Сам чат ничего дополнительно не запускает, кроме браузера.",
            ]
        )
    elif action_key == "open_dynamic_app":
        entry = get_dynamic_entry_by_key(str(arg or "")) or find_dynamic_entry(str(arg or ""))
        if entry:
            target = str(entry.get("launch", "") or "").strip()
            lines.extend(
                [
                    f"Найдено пользовательское действие: {str(entry.get('name', '') or '').strip() or str(arg or '').strip()}",
                    f"Источник записи: {_source_label(entry.get('source', 'custom'))}.",
                    f"Цель запуска: {target or 'не указана'}",
                    f"Тип запуска: {_launch_target_kind(target)}.",
                ]
            )
            close_exes = [str(item or "").strip() for item in (entry.get("close_exes", []) or []) if str(item or "").strip()]
            if close_exes:
                lines.append("Для последующего закрытия будут использованы процессы: " + ", ".join(close_exes))
        else:
            lines.append("Пользовательское действие пока не найдено. Если запись пропала, запуск не состоится даже после подтверждения.")
    elif action_key == "close_app":
        entry = get_dynamic_entry_by_key(str(arg or "")) or find_dynamic_entry(str(arg or ""))
        close_targets = []
        if entry:
            close_targets = [str(item or "").strip() for item in (entry.get("close_exes", []) or []) if str(item or "").strip()]
            if not close_targets:
                launch_target = str(entry.get("launch", "") or "").strip()
                if launch_target and "://" not in launch_target:
                    close_targets = [os.path.basename(launch_target)]
        if close_targets:
            lines.extend(
                [
                    "После подтверждения JARVIS попытается завершить процессы: " + ", ".join(close_targets),
                    "Если процессы не найдутся, принудительного закрытия не произойдёт.",
                ]
            )
        else:
            lines.extend(
                [
                    f"После подтверждения JARVIS попытается закрыть: {str(arg or '').strip() or 'неизвестное приложение'}",
                    "Если список процессов для закрытия не определён, команда завершится без эффекта.",
                ]
            )
    else:
        label = str(action_key or "действие").strip()
        if arg not in (None, ""):
            label = f"{label}: {arg}"
        lines.append(f"После подтверждения будет выполнено действие: {label}")

    if target_category:
        lines.append(f"Контур безопасности: {category_label(target_category)}.")

    try:
        mode = permission_mode_for_action(app._cfg(), action_key)
    except Exception:
        mode = ""
    if mode == "ask_once":
        lines.append("Разрешение будет запомнено до конца текущего запуска приложения.")
    elif mode == "always":
        lines.append("Подтверждение для этого типа действия требуется каждый раз.")

    if origin:
        lines.append(f"Источник команды: {str(origin or '').strip()}.")
    return [line for line in lines if str(line or "").strip()]


def _merge_dry_run_description(base_description: str, preview_lines: list[str]) -> str:
    parts = []
    description = str(base_description or "").strip()
    if description:
        parts.append(description)
    if preview_lines:
        preview_block = "Сухой прогон:\n" + "\n".join(f"• {line}" for line in preview_lines)
        parts.append(preview_block)
    return "\n\n".join(parts).strip()


def _request_action_confirmation_with_dry_run(self, *, action: str, arg=None, label: str, category: str, origin: str, description: str = "") -> bool:
    preview_lines = build_action_dry_run_lines(
        self,
        action=action,
        arg=arg,
        category=category,
        origin=origin,
    )
    try:
        self._last_dry_run_preview = "\n".join(preview_lines)
    except Exception:
        pass
    return type(self)._base_request_action_confirmation_dry_run(
        self,
        action=action,
        arg=arg,
        label=label,
        category=category,
        origin=origin,
        description=_merge_dry_run_description(description, preview_lines),
    )


def apply_dry_run_runtime(app_cls):
    if getattr(app_cls, "_dry_run_runtime_applied", False):
        return
    app_cls._dry_run_runtime_applied = True
    app_cls._base_request_action_confirmation_dry_run = app_cls.request_action_confirmation
    app_cls.build_action_dry_run_lines = build_action_dry_run_lines
    app_cls.request_action_confirmation = _request_action_confirmation_with_dry_run


__all__ = ["apply_dry_run_runtime", "build_action_dry_run_lines"]

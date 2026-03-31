import json
import os
import threading
from datetime import datetime

from .branding import APP_VERSION
from .storage import app_data_dir
from .theme import Theme
from .utils import short_exc


_RECOVERY_LOCK = threading.RLock()


def session_recovery_path(base_dir: str | None = None) -> str:
    root = str(base_dir or app_data_dir()).strip()
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "recovery_state.json")


def load_recovery_session_state(path: str | None = None):
    target = str(path or session_recovery_path()).strip()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_recovery_session_state(payload: dict, path: str | None = None) -> str:
    target = str(path or session_recovery_path()).strip()
    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload or {}, fh, ensure_ascii=False, indent=2)
    return target


def clear_recovery_session_state(path: str | None = None) -> None:
    target = str(path or session_recovery_path()).strip()
    try:
        os.remove(target)
    except FileNotFoundError:
        pass


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _session_snapshot(app) -> dict:
    return {
        "status": "running",
        "version": APP_VERSION,
        "started_at": _now_text(),
        "updated_at": _now_text(),
        "pid": os.getpid(),
        "safe_mode": bool(getattr(app, "safe_mode", False)),
        "last_query": "",
        "last_error": "",
    }


def _update_recovery_state(self, **updates):
    path = str(getattr(self, "_recovery_state_path", "") or session_recovery_path()).strip()
    if not path:
        return
    with _RECOVERY_LOCK:
        payload = load_recovery_session_state(path) or _session_snapshot(self)
        payload.update({key: value for key, value in updates.items()})
        payload["updated_at"] = _now_text()
        write_recovery_session_state(payload, path)


def _show_recovery_prompt(self):
    if getattr(self, "_crash_recovery_prompted", False):
        return
    state = getattr(self, "_crash_recovery_state", None)
    if not isinstance(state, dict):
        return
    if bool(getattr(self, "_startup_gate_setup", False)):
        try:
            self.root.after(1200, self._show_recovery_prompt)
        except Exception:
            pass
        return
    if not hasattr(self, "_render_chat_prompt_card"):
        return

    self._crash_recovery_prompted = True
    last_query = str(state.get("last_query", "") or "").strip()
    last_error = str(state.get("last_error", "") or "").strip()
    started_at = str(state.get("started_at", "") or "").strip()
    version = str(state.get("version", "") or "").strip()

    lines = [
        "Предыдущий запуск завершился нештатно. JARVIS открыл отдельный режим восстановления.",
    ]
    if started_at:
        lines.append(f"Проблемная сессия началась: {started_at}")
    if version:
        lines.append(f"Версия проблемной сессии: {version}")
    if last_query:
        lines.append(f"Последняя команда перед сбоем: {last_query}")
    if last_error:
        lines.append(f"Последняя ошибка: {last_error}")
    lines.append("Можно сразу открыть диагностику, собрать пакет поддержки или включить безопасный старт на следующий запуск.")

    def _open_diagnostics():
        self._dismiss_recovery_prompt("Открываю диагностику после сбоя.")
        try:
            self.open_full_settings_view("diagnostics")
        except Exception:
            pass

    def _export_bundle():
        self._dismiss_recovery_prompt("Собираю пакет поддержки после сбоя.")
        try:
            self.export_diagnostics_bundle_action()
        except Exception:
            pass

    def _enable_safe_mode():
        self._dismiss_recovery_prompt("Безопасный режим будет включён на следующий запуск.")
        try:
            self._cfg().set_safe_mode_enabled(True)
        except Exception:
            pass
        try:
            self.add_msg("Безопасный режим включён на следующий старт. Перезапустите приложение, если хотите зайти в щадящем режиме.", "bot")
        except Exception:
            pass

    def _continue_normal():
        self._dismiss_recovery_prompt("Продолжаю обычный запуск.")

    _card_wrap, _card, buttons = self._render_chat_prompt_card(
        title="Восстановление после сбоя",
        lines=lines,
        actions=[
            {"text": "Диагностика", "command": _open_diagnostics, "bg": Theme.ACCENT},
            {"text": "Пакет поддержки", "command": _export_bundle},
            {"text": "Safe mode", "command": _enable_safe_mode},
            {"text": "Продолжить", "command": _continue_normal},
        ],
        tone="error",
    )
    self._recovery_prompt_buttons = buttons
    if hasattr(self, "_human_log_summary_var"):
        try:
            self._human_log_summary_var.set("Обнаружен прошлый нештатный выход. Recovery-flow открыт в чате.")
        except Exception:
            pass


def _dismiss_recovery_prompt(self, status_text: str = ""):
    for button in list(getattr(self, "_recovery_prompt_buttons", []) or []):
        try:
            button.configure(state="disabled")
        except Exception:
            pass
    self._recovery_prompt_buttons = []
    if status_text:
        try:
            self.set_status_temp(status_text, "warn", duration_ms=4200)
        except Exception:
            pass


def _init_with_recovery(self, root, *args, **kwargs):
    self._recovery_state_path = session_recovery_path()
    self._crash_recovery_state = None
    self._crash_recovery_prompted = False
    self._recovery_prompt_buttons = []
    previous = load_recovery_session_state(self._recovery_state_path)
    if isinstance(previous, dict) and str(previous.get("status", "")).strip().lower() == "running":
        self._crash_recovery_state = previous
    try:
        result = type(self)._base_init_recovery(self, root, *args, **kwargs)
    except Exception as exc:
        try:
            write_recovery_session_state(
                {
                    "status": "running",
                    "version": APP_VERSION,
                    "started_at": previous.get("started_at") if isinstance(previous, dict) else _now_text(),
                    "updated_at": _now_text(),
                    "pid": os.getpid(),
                    "safe_mode": bool(getattr(self, "safe_mode", False)),
                    "last_query": str(getattr(self, "_last_user_query", "") or "").strip(),
                    "last_error": short_exc(exc),
                },
                self._recovery_state_path,
            )
        except Exception:
            pass
        raise
    _update_recovery_state(self, **_session_snapshot(self))
    try:
        self.root.after(900, self._show_recovery_prompt)
    except Exception:
        pass
    return result


def _shutdown_with_recovery(self):
    if not getattr(self, "_recovery_state_path", None):
        return type(self)._base_shutdown_recovery(self)
    result = type(self)._base_shutdown_recovery(self)
    try:
        clear_recovery_session_state(self._recovery_state_path)
    except Exception:
        pass
    return result


def _process_query_with_recovery(self, query: str, reply_callback=None):
    text = str(query or "").strip()
    if text:
        try:
            self._update_recovery_state(last_query=text[:280])
        except Exception:
            pass
    return type(self)._base_process_query_recovery(self, query, reply_callback=reply_callback)


def _report_error_with_recovery(self, context, exc, speak=True):
    details = short_exc(exc)
    try:
        self._update_recovery_state(last_error=f"{str(context or '').strip()}: {details}"[:360])
    except Exception:
        pass
    return type(self)._base_report_error_recovery(self, context, exc, speak=speak)


def apply_recovery_runtime(app_cls):
    if getattr(app_cls, "_recovery_runtime_applied", False):
        return
    app_cls._recovery_runtime_applied = True
    app_cls._base_init_recovery = app_cls.__init__
    app_cls._base_shutdown_recovery = app_cls.shutdown
    app_cls._base_process_query_recovery = app_cls.process_query
    app_cls._base_report_error_recovery = app_cls.report_error
    app_cls._update_recovery_state = _update_recovery_state
    app_cls._show_recovery_prompt = _show_recovery_prompt
    app_cls._dismiss_recovery_prompt = _dismiss_recovery_prompt
    app_cls.__init__ = _init_with_recovery
    app_cls.shutdown = _shutdown_with_recovery
    app_cls.process_query = _process_query_with_recovery
    app_cls.report_error = _report_error_with_recovery


__all__ = [
    "apply_recovery_runtime",
    "clear_recovery_session_state",
    "load_recovery_session_state",
    "session_recovery_path",
    "write_recovery_session_state",
]

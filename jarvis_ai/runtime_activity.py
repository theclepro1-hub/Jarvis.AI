from __future__ import annotations

import logging
import threading
import time
import uuid
import tkinter as tk
from tkinter import ttk

from .branding import APP_LOGGER_NAME
from .branding import app_dialog_title
from .theme import Theme
from .ui_factory import bind_dynamic_wrap
from .utils import short_exc

logger = logging.getLogger(APP_LOGGER_NAME)


def _now_stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_action_entries(entries):
    normalized = []
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        summary = str(item.get("summary", "") or "").strip()
        if not title and not summary:
            continue
        undo = item.get("undo")
        if not isinstance(undo, dict):
            undo = None
        normalized.append(
            {
                "id": str(item.get("id", "") or uuid.uuid4().hex[:12]).strip()[:40],
                "at": str(item.get("at", "") or _now_stamp()).strip()[:32],
                "title": title[:120] or summary[:120],
                "summary": summary[:300] or title[:300],
                "raw_cmd": str(item.get("raw_cmd", "") or "").strip()[:240],
                "route": str(item.get("route", "") or "").strip()[:32],
                "undo": undo,
            }
        )
    return normalized[-80:]


def _normalize_log_entries(entries):
    normalized = []
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        detail = str(item.get("detail", "") or "").strip()
        if not title and not detail:
            continue
        level = str(item.get("level", "info") or "info").strip().lower()
        if level not in {"info", "warn", "error"}:
            level = "info"
        normalized.append(
            {
                "id": str(item.get("id", "") or uuid.uuid4().hex[:12]).strip()[:40],
                "at": str(item.get("at", "") or _now_stamp()).strip()[:32],
                "level": level,
                "title": title[:120] or detail[:120],
                "detail": detail[:500],
                "fix": str(item.get("fix", "") or "").strip()[:420],
            }
        )
    return normalized[-120:]


def _ensure_activity_state(self):
    if not hasattr(self, "_action_history_entries"):
        self._action_history_entries = _normalize_action_entries(self._cfg().get_action_history_entries())
    if not hasattr(self, "_human_log_entries"):
        self._human_log_entries = _normalize_log_entries(self._cfg().get_human_log_entries())
    if not hasattr(self, "_last_action_card_var"):
        self._last_action_card_var = tk.StringVar(value="Последнее действие появится здесь.")
    if not hasattr(self, "_last_action_can_undo"):
        self._last_action_can_undo = tk.BooleanVar(value=False)
    if not hasattr(self, "_human_log_summary_var"):
        self._human_log_summary_var = tk.StringVar(value="Сбоев не зафиксировано.")


def _persist_activity_state(self):
    try:
        self._cfg().set_action_history_entries(_normalize_action_entries(getattr(self, "_action_history_entries", [])))
    except Exception:
        pass
    try:
        self._cfg().set_human_log_entries(_normalize_log_entries(getattr(self, "_human_log_entries", [])))
    except Exception:
        pass


def _refresh_activity_widgets(self):
    _ensure_activity_state(self)
    actions = list(getattr(self, "_action_history_entries", []))
    logs = list(getattr(self, "_human_log_entries", []))

    last_action = actions[-1] if actions else None
    if last_action:
        text = f"{last_action.get('title')} • {last_action.get('summary')}"
        self._last_action_card_var.set(text[:220])
        self._last_action_can_undo.set(bool(last_action.get("undo")))
    else:
        self._last_action_card_var.set("Последнее действие появится здесь.")
        self._last_action_can_undo.set(False)

    if logs:
        last_log = logs[-1]
        prefix = {"error": "Ошибка", "warn": "Предупреждение", "info": "Журнал"}.get(last_log.get("level"), "Журнал")
        self._human_log_summary_var.set(f"{prefix}: {last_log.get('title')}")
    else:
        self._human_log_summary_var.set("Сбоев не зафиксировано.")

    history_listbox = getattr(self, "_action_history_listbox", None)
    if history_listbox is not None:
        try:
            history_listbox.delete(0, tk.END)
            for item in reversed(actions):
                marker = "↩" if item.get("undo") else "•"
                history_listbox.insert(tk.END, f"{item.get('at', '')[:16]} {marker} {item.get('title')}")
            if not actions:
                history_listbox.insert(tk.END, "Пока нет действий.")
        except Exception:
            pass

    log_listbox = getattr(self, "_human_log_listbox", None)
    if log_listbox is not None:
        try:
            log_listbox.delete(0, tk.END)
            for item in reversed(logs):
                marker = {"error": "✖", "warn": "!", "info": "•"}.get(item.get("level"), "•")
                log_listbox.insert(tk.END, f"{item.get('at', '')[:16]} {marker} {item.get('title')}")
            if not logs:
                log_listbox.insert(tk.END, "Журнал чист.")
        except Exception:
            pass

    action_btn = getattr(self, "_last_action_undo_btn", None)
    if action_btn is not None:
        try:
            action_btn.configure(state="normal" if self._last_action_can_undo.get() else "disabled")
        except Exception:
            pass


def _schedule_activity_refresh(self):
    try:
        if threading.current_thread() is threading.main_thread():
            _refresh_activity_widgets(self)
        else:
            self.root.after(0, lambda: _refresh_activity_widgets(self))
    except Exception:
        pass


def _record_action_entry(self, title: str, summary: str, raw_cmd: str = "", route: str = "", undo=None):
    _ensure_activity_state(self)
    entries = list(getattr(self, "_action_history_entries", []))
    entries.append(
        {
            "id": uuid.uuid4().hex[:12],
            "at": _now_stamp(),
            "title": str(title or "").strip()[:120],
            "summary": str(summary or "").strip()[:300],
            "raw_cmd": str(raw_cmd or "").strip()[:240],
            "route": str(route or "").strip()[:32],
            "undo": undo if isinstance(undo, dict) else None,
        }
    )
    self._action_history_entries = _normalize_action_entries(entries)
    _persist_activity_state(self)
    _schedule_activity_refresh(self)


def _record_human_log(self, title: str, detail: str, fix: str = "", level: str = "info"):
    _ensure_activity_state(self)
    entries = list(getattr(self, "_human_log_entries", []))
    entries.append(
        {
            "id": uuid.uuid4().hex[:12],
            "at": _now_stamp(),
            "level": str(level or "info").strip().lower(),
            "title": str(title or "").strip()[:120],
            "detail": str(detail or "").strip()[:500],
            "fix": str(fix or "").strip()[:420],
        }
    )
    self._human_log_entries = _normalize_log_entries(entries)
    _persist_activity_state(self)
    _schedule_activity_refresh(self)


def _friendly_fix_for_error(context: str, exc) -> str:
    low = f"{context} {short_exc(exc)}".lower()
    if "api key" in low or "authentication" in low or "invalid api key" in low:
        return "Откройте control center -> ИИ и профиль и вставьте актуальный Groq API ключ."
    if "timeout" in low or "connection" in low or "network" in low or "proxy" in low:
        return "Проверьте интернет, VPN/Proxy и затем повторите действие."
    if "microphone" in low or "mic" in low or "audio" in low or "speech" in low:
        return "Откройте центр голоса, выберите микрофон и прогоните тестовую запись."
    if "repository not found" in low or "git push" in low or "remote" in low:
        return "Проверьте адрес GitHub репозитория в publish_tools и убедитесь, что репозиторий существует."
    if "file not found" in low or "not found" in low:
        return "Проверьте путь или раздел «Приложения и игры», затем повторите запуск."
    return "Откройте раздел «Система» -> «Журнал» и посмотрите подробности последней ошибки."


def _friendly_error_message(context: str, exc) -> str:
    issue = short_exc(exc)
    return f"{context}. {issue}".strip()


def _infer_undo_payload(action: str, arg, result: str = ""):
    action_text = str(action or "").strip().lower()
    undo_map = {
        "volume_up": {"action": "volume_down", "arg": "", "label": "Вернуть громкость назад"},
        "volume_down": {"action": "volume_up", "arg": "", "label": "Вернуть громкость назад"},
        "media_pause": {"action": "media_play", "arg": "", "label": "Возобновить воспроизведение"},
        "media_play": {"action": "media_pause", "arg": "", "label": "Поставить на паузу"},
        "media_next": {"action": "media_prev", "arg": "", "label": "Вернуть предыдущий трек"},
        "media_prev": {"action": "media_next", "arg": "", "label": "Вернуть следующий трек"},
    }
    if action_text in undo_map:
        return dict(undo_map[action_text])
    if action_text in {"youtube", "steam", "discord", "telegram", "music"}:
        return {"action": "close_app", "arg": action_text, "label": "Закрыть открытое приложение"}
    return None


def _action_title(action: str, arg=None) -> str:
    action_text = str(action or "").strip().lower()
    labels = {
        "close_app": "Закрытие приложения",
        "open_dynamic_app": "Запуск пользовательского приложения",
        "search": "Поиск в браузере",
        "reminder": "Создание напоминания",
        "history": "Открытие истории",
        "repeat": "Повтор последнего ответа",
        "time": "Показ времени",
        "date": "Показ даты",
        "weather": "Открытие погоды",
        "media_pause": "Пауза",
        "media_play": "Продолжение",
        "media_next": "Следующий трек",
        "media_prev": "Предыдущий трек",
        "volume_up": "Увеличение громкости",
        "volume_down": "Уменьшение громкости",
        "shutdown": "Выключение ПК",
        "restart_pc": "Перезагрузка ПК",
        "lock": "Блокировка экрана",
        "youtube": "Открытие YouTube",
        "steam": "Открытие Steam",
        "discord": "Открытие Discord",
        "telegram": "Открытие Telegram",
        "music": "Открытие Яндекс Музыки",
    }
    base = labels.get(action_text, action_text or "Действие")
    arg_text = str(arg or "").strip()
    if arg_text and action_text in {"search", "open_dynamic_app", "close_app"}:
        return f"{base}: {arg_text}"
    return base


def _patched_report_error(self, context, exc, speak=True):
    _ensure_activity_state(self)
    friendly_text = _friendly_error_message(context, exc)
    fix = _friendly_fix_for_error(context, exc)
    chat_text = friendly_text
    if fix:
        chat_text += "\nЧто сделать: " + fix
    self.root.after(0, lambda t=chat_text: self.add_msg(t))
    if speak:
        try:
            self.say(friendly_text)
        except Exception:
            pass
    self.set_status("Ошибка", "error")
    try:
        logger.error(f"{context}: {short_exc(exc)}", exc_info=exc)
    except Exception:
        pass
    _record_human_log(self, str(context or "Ошибка"), friendly_text, fix=fix, level="error")
    return friendly_text


def _patched_execute_action(self, action: str, arg=None, raw_cmd: str = "", speak: bool = True, reply_callback=None):
    result = type(self)._base_execute_action_activity(self, action, arg, raw_cmd, speak, reply_callback)
    if getattr(self, "_activity_undo_in_progress", False):
        return result
    undo = _infer_undo_payload(action, arg, result)
    title = _action_title(action, arg)
    summary = str(result or "Действие выполнено.").strip()
    _record_action_entry(self, title, summary, raw_cmd=raw_cmd, route="command", undo=undo)
    return result


def _patched_handle_memory_route(self, route, raw_text: str = ""):
    result = type(self)._base_handle_memory_route_activity(self, route, raw_text)
    intent = str((route or {}).get("intent", "") or "").strip().lower()
    labels = {
        "remember": "Обновление памяти",
        "forget": "Очистка памяти",
        "show": "Просмотр памяти",
    }
    _record_action_entry(self, labels.get(intent, "Память"), result, raw_cmd=raw_text, route="memory")
    return result


def _patched_handle_scenario_route(self, route):
    result = type(self)._base_handle_scenario_route_activity(self, route)
    scenario = (route or {}).get("scenario") or {}
    name = str(scenario.get("name", "") or "Сценарий").strip()
    _record_action_entry(self, f"Сценарий: {name}", result, route="scenario")
    return result


def _selected_action_entry(self):
    lb = getattr(self, "_action_history_listbox", None)
    entries = list(getattr(self, "_action_history_entries", []))
    if lb is None:
        return None
    try:
        selection = lb.curselection()
    except Exception:
        selection = ()
    if not selection or not entries:
        return None
    index = int(selection[0])
    ordered = list(reversed(entries))
    return ordered[index] if 0 <= index < len(ordered) else None


def _selected_log_entry(self):
    lb = getattr(self, "_human_log_listbox", None)
    entries = list(getattr(self, "_human_log_entries", []))
    if lb is None:
        return None
    try:
        selection = lb.curselection()
    except Exception:
        selection = ()
    if not selection or not entries:
        return None
    index = int(selection[0])
    ordered = list(reversed(entries))
    return ordered[index] if 0 <= index < len(ordered) else None


def undo_last_action(self):
    _ensure_activity_state(self)
    actions = list(getattr(self, "_action_history_entries", []))
    target = next((item for item in reversed(actions) if isinstance(item.get("undo"), dict)), None)
    if target is None:
        self.set_status_temp("Откатывать нечего", "warn")
        return
    self.undo_action_entry(target)


def undo_action_entry(self, entry):
    undo = entry.get("undo") if isinstance(entry, dict) else None
    if not isinstance(undo, dict):
        self.set_status_temp("Для этого действия нет отката", "warn")
        return
    self._activity_undo_in_progress = True
    try:
        result = type(self)._base_execute_action_activity(
            self,
            undo.get("action"),
            undo.get("arg"),
            f"undo:{entry.get('title', '')}",
            True,
            None,
        )
    finally:
        self._activity_undo_in_progress = False
    summary = str(result or undo.get("label") or "Откат выполнен").strip()
    _record_action_entry(self, "Откат действия", summary, route="undo")
    self.set_status_temp(summary, "ok")


def _sync_action_detail(self, *_args):
    item = _selected_action_entry(self)
    var = getattr(self, "_action_history_detail_var", None)
    if var is None:
        return
    if item is None:
        var.set("Выберите действие, чтобы увидеть, что понял ИИ и можно ли это отменить.")
        return
    pieces = [
        item.get("title", ""),
        item.get("summary", ""),
    ]
    raw_cmd = str(item.get("raw_cmd", "") or "").strip()
    if raw_cmd:
        pieces.append("Исходная команда: " + raw_cmd)
    undo = item.get("undo")
    if isinstance(undo, dict):
        pieces.append("Откат доступен: " + str(undo.get("label") or "да"))
    else:
        pieces.append("Откат недоступен.")
    var.set("\n".join(piece for piece in pieces if piece))


def _sync_log_detail(self, *_args):
    item = _selected_log_entry(self)
    var = getattr(self, "_human_log_detail_var", None)
    if var is None:
        return
    if item is None:
        var.set("Здесь появится объяснение ошибки человеческим языком.")
        return
    pieces = [item.get("title", ""), item.get("detail", "")]
    fix = str(item.get("fix", "") or "").strip()
    if fix:
        pieces.append("Что сделать: " + fix)
    var.set("\n".join(piece for piece in pieces if piece))


def show_history(self):
    _ensure_activity_state(self)
    win = getattr(self, "_activity_window", None)
    if win is not None:
        try:
            if win.winfo_exists():
                win.lift()
                return
        except Exception:
            pass

    win = tk.Toplevel(self.root)
    self._activity_window = win
    win.title(app_dialog_title("Журнал"))
    win.geometry("760x620")
    win.configure(bg=Theme.BG)

    outer = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    outer.pack(fill="both", expand=True, padx=12, pady=12)

    tk.Label(outer, text="Журнал JARVIS", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 14)).pack(
        anchor="w", padx=16, pady=(16, 4)
    )
    note = tk.Label(
        outer,
        text="Здесь видно, что JARVIS понял, что выполнил и можно ли это откатить. Ошибки переведены в человеческий вид с подсказкой, что нажать дальше.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=("Segoe UI", 10),
    )
    note.pack(fill="x", padx=16, pady=(0, 12))
    bind_dynamic_wrap(note, outer, padding=32, minimum=260)

    notebook = ttk.Notebook(outer, style="Jarvis.TNotebook")
    notebook.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    actions_tab = tk.Frame(notebook, bg=Theme.BG_LIGHT)
    logs_tab = tk.Frame(notebook, bg=Theme.BG_LIGHT)
    notebook.add(actions_tab, text="Действия")
    notebook.add(logs_tab, text="Логи")

    actions_card = tk.Frame(actions_tab, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    actions_card.pack(fill="both", expand=True)
    actions_list_wrap = tk.Frame(actions_card, bg=Theme.CARD_BG)
    actions_list_wrap.pack(fill="both", expand=True, padx=14, pady=(14, 10))
    actions_scroll = ttk.Scrollbar(actions_list_wrap, style="Jarvis.Vertical.TScrollbar")
    actions_scroll.pack(side="right", fill="y")
    self._action_history_listbox = tk.Listbox(
        actions_list_wrap,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        selectbackground=Theme.ACCENT,
        selectforeground=Theme.FG,
        relief="flat",
        bd=0,
        highlightthickness=0,
        activestyle="none",
        font=("Segoe UI", 10),
        yscrollcommand=actions_scroll.set,
    )
    self._action_history_listbox.pack(side="left", fill="both", expand=True)
    actions_scroll.configure(command=self._action_history_listbox.yview)

    self._action_history_detail_var = tk.StringVar(value="")
    action_detail = tk.Label(
        actions_card,
        textvariable=self._action_history_detail_var,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=("Segoe UI", 10),
    )
    action_detail.pack(fill="x", padx=14, pady=(0, 10))
    bind_dynamic_wrap(action_detail, actions_card, padding=32, minimum=260)
    self._action_history_listbox.bind("<<ListboxSelect>>", self._sync_action_detail, add="+")

    actions_footer = tk.Frame(actions_card, bg=Theme.CARD_BG)
    actions_footer.pack(fill="x", padx=14, pady=(0, 14))
    tk.Button(
        actions_footer,
        text="Отменить выбранное",
        command=lambda: self.undo_action_entry(_selected_action_entry(self)),
        bg=Theme.ACCENT,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
    ).pack(side="right")
    tk.Button(
        actions_footer,
        text="Отменить последнее",
        command=self.undo_last_action,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
    ).pack(side="right", padx=(0, 8))

    logs_card = tk.Frame(logs_tab, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    logs_card.pack(fill="both", expand=True)
    logs_list_wrap = tk.Frame(logs_card, bg=Theme.CARD_BG)
    logs_list_wrap.pack(fill="both", expand=True, padx=14, pady=(14, 10))
    logs_scroll = ttk.Scrollbar(logs_list_wrap, style="Jarvis.Vertical.TScrollbar")
    logs_scroll.pack(side="right", fill="y")
    self._human_log_listbox = tk.Listbox(
        logs_list_wrap,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        selectbackground=Theme.ACCENT,
        selectforeground=Theme.FG,
        relief="flat",
        bd=0,
        highlightthickness=0,
        activestyle="none",
        font=("Segoe UI", 10),
        yscrollcommand=logs_scroll.set,
    )
    self._human_log_listbox.pack(side="left", fill="both", expand=True)
    logs_scroll.configure(command=self._human_log_listbox.yview)

    self._human_log_detail_var = tk.StringVar(value="")
    log_detail = tk.Label(
        logs_card,
        textvariable=self._human_log_detail_var,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=("Segoe UI", 10),
    )
    log_detail.pack(fill="x", padx=14, pady=(0, 10))
    bind_dynamic_wrap(log_detail, logs_card, padding=32, minimum=260)
    self._human_log_listbox.bind("<<ListboxSelect>>", self._sync_log_detail, add="+")

    logs_footer = tk.Frame(logs_card, bg=Theme.CARD_BG)
    logs_footer.pack(fill="x", padx=14, pady=(0, 14))
    tk.Button(
        logs_footer,
        text="Очистить логи",
        command=lambda: (_clear_logs(self)),
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
    ).pack(side="right")

    def _close():
        self._activity_window = None
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _close)
    _refresh_activity_widgets(self)
    self._sync_action_detail()
    self._sync_log_detail()


def _clear_logs(self):
    self._human_log_entries = []
    _persist_activity_state(self)
    _refresh_activity_widgets(self)
    self._sync_log_detail()
    self.set_status_temp("Журнал очищен", "ok")


def register_activity_runtime(app_cls):
    if not hasattr(app_cls, "_base_execute_action_activity"):
        app_cls._base_execute_action_activity = app_cls.execute_action
    if not hasattr(app_cls, "_base_handle_memory_route_activity"):
        app_cls._base_handle_memory_route_activity = app_cls._handle_memory_route
    if not hasattr(app_cls, "_base_handle_scenario_route_activity"):
        app_cls._base_handle_scenario_route_activity = app_cls._handle_scenario_route

    app_cls._ensure_activity_state = _ensure_activity_state
    app_cls._persist_activity_state = _persist_activity_state
    app_cls._refresh_activity_widgets = _refresh_activity_widgets
    app_cls._schedule_activity_refresh = _schedule_activity_refresh
    app_cls._record_action_entry = _record_action_entry
    app_cls._record_human_log = _record_human_log
    app_cls._sync_action_detail = _sync_action_detail
    app_cls._sync_log_detail = _sync_log_detail
    app_cls.execute_action = _patched_execute_action
    app_cls._handle_memory_route = _patched_handle_memory_route
    app_cls._handle_scenario_route = _patched_handle_scenario_route
    app_cls.report_error = _patched_report_error
    app_cls.show_history = show_history
    app_cls.undo_last_action = undo_last_action
    app_cls.undo_action_entry = undo_action_entry


__all__ = ["register_activity_runtime"]

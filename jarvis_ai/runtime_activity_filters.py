import tkinter as tk
from tkinter import ttk

from . import runtime_activity as activity_mod
from .branding import app_dialog_title
from .theme import Theme
from .ui_factory import bind_dynamic_wrap


ACTION_ROUTE_FILTERS = (
    ("Все действия", "*"),
    ("Команды", "command"),
    ("Сценарии", "scenario"),
    ("Память", "memory"),
    ("Откаты", "undo"),
)

LOG_LEVEL_FILTERS = (
    ("Все события", "*"),
    ("Ошибки", "error"),
    ("Предупреждения", "warn"),
    ("Инфо", "info"),
)


def _filter_code_from_label(label: str, variants) -> str:
    current = str(label or "").strip()
    for title, code in variants:
        if current == title:
            return code
    return "*"


def _ensure_activity_state_with_filters(self):
    base = getattr(type(self), "_base_ensure_activity_state_with_filters", None)
    if callable(base):
        base(self)
    if not hasattr(self, "_activity_filter_query_var"):
        self._activity_filter_query_var = tk.StringVar(value="")
    if not hasattr(self, "_activity_filter_route_var"):
        self._activity_filter_route_var = tk.StringVar(value=ACTION_ROUTE_FILTERS[0][0])
    if not hasattr(self, "_log_filter_query_var"):
        self._log_filter_query_var = tk.StringVar(value="")
    if not hasattr(self, "_log_filter_level_var"):
        self._log_filter_level_var = tk.StringVar(value=LOG_LEVEL_FILTERS[0][0])
    if getattr(self, "_activity_filter_traces_bound", False):
        return
    for var in (
        self._activity_filter_query_var,
        self._activity_filter_route_var,
        self._log_filter_query_var,
        self._log_filter_level_var,
    ):
        try:
            var.trace_add("write", lambda *_args: self._schedule_activity_filter_refresh())
        except Exception:
            pass
    self._activity_filter_traces_bound = True


def _filtered_action_entries(self):
    entries = list(getattr(self, "_action_history_entries", []))
    query = str(getattr(self, "_activity_filter_query_var", None).get() if hasattr(self, "_activity_filter_query_var") else "").strip().lower()
    route_code = _filter_code_from_label(
        str(getattr(self, "_activity_filter_route_var", None).get() if hasattr(self, "_activity_filter_route_var") else ""),
        ACTION_ROUTE_FILTERS,
    )
    filtered = []
    for item in entries:
        route = str(item.get("route", "") or "").strip().lower()
        if route_code != "*" and route != route_code:
            continue
        haystack = " ".join(
            str(item.get(key, "") or "").strip().lower()
            for key in ("title", "summary", "raw_cmd", "route", "at")
        )
        if query and query not in haystack:
            continue
        filtered.append(item)
    return filtered


def _filtered_log_entries(self):
    entries = list(getattr(self, "_human_log_entries", []))
    query = str(getattr(self, "_log_filter_query_var", None).get() if hasattr(self, "_log_filter_query_var") else "").strip().lower()
    level_code = _filter_code_from_label(
        str(getattr(self, "_log_filter_level_var", None).get() if hasattr(self, "_log_filter_level_var") else ""),
        LOG_LEVEL_FILTERS,
    )
    filtered = []
    for item in entries:
        level = str(item.get("level", "") or "").strip().lower()
        if level_code != "*" and level != level_code:
            continue
        haystack = " ".join(
            str(item.get(key, "") or "").strip().lower()
            for key in ("title", "detail", "fix", "level", "at")
        )
        if query and query not in haystack:
            continue
        filtered.append(item)
    return filtered


def _selected_action_entry_filtered(self):
    lb = getattr(self, "_action_history_listbox", None)
    entries = _filtered_action_entries(self)
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


def _selected_log_entry_filtered(self):
    lb = getattr(self, "_human_log_listbox", None)
    entries = _filtered_log_entries(self)
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


def _refresh_activity_widgets_with_filters(self):
    _ensure_activity_state_with_filters(self)
    all_actions = list(getattr(self, "_action_history_entries", []))
    all_logs = list(getattr(self, "_human_log_entries", []))
    actions = _filtered_action_entries(self)
    logs = _filtered_log_entries(self)

    last_action = all_actions[-1] if all_actions else None
    if last_action:
        text = f"{last_action.get('title')} • {last_action.get('summary')}"
        self._last_action_card_var.set(text[:220])
        self._last_action_can_undo.set(bool(last_action.get("undo")))
    else:
        self._last_action_card_var.set("Последнее действие появится здесь.")
        self._last_action_can_undo.set(False)

    if all_logs:
        last_log = all_logs[-1]
        prefix = {"error": "Ошибка", "warn": "Предупреждение", "info": "Журнал"}.get(last_log.get("level"), "Журнал")
        self._human_log_summary_var.set(f"{prefix}: {last_log.get('title')}")
    else:
        self._human_log_summary_var.set("Сбоев не зафиксировано.")

    story_var = getattr(self, "_session_story_var", None)
    if story_var is not None:
        if all_actions:
            recent_titles = [str(item.get("title", "") or "").strip() for item in all_actions[-3:] if str(item.get("title", "") or "").strip()]
            story = " -> ".join(recent_titles)
            if all_logs and str(all_logs[-1].get("level", "") or "").strip().lower() == "error":
                story += " • требует внимания"
            story_var.set(f"За сессию: {story[:240]}")
        else:
            story_var.set("За сессию пока нет действий.")

    history_listbox = getattr(self, "_action_history_listbox", None)
    if history_listbox is not None:
        try:
            history_listbox.delete(0, tk.END)
            for item in reversed(actions):
                marker = "↩" if item.get("undo") else "•"
                history_listbox.insert(tk.END, f"{item.get('at', '')[:16]} {marker} {item.get('title')}")
            if not actions:
                history_listbox.insert(tk.END, "По выбранному фильтру действий нет." if all_actions else "Пока нет действий.")
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
                log_listbox.insert(tk.END, "По выбранному фильтру записей нет." if all_logs else "Журнал чист.")
        except Exception:
            pass

    action_btn = getattr(self, "_last_action_undo_btn", None)
    if action_btn is not None:
        try:
            action_btn.configure(state="normal" if self._last_action_can_undo.get() else "disabled")
        except Exception:
            pass


def _schedule_activity_filter_refresh(self):
    try:
        _refresh_activity_widgets_with_filters(self)
        self._sync_action_detail()
        self._sync_log_detail()
    except Exception:
        try:
            self.root.after(
                0,
                lambda: (
                    _refresh_activity_widgets_with_filters(self),
                    self._sync_action_detail(),
                    self._sync_log_detail(),
                ),
            )
        except Exception:
            pass


def _show_history_with_filters(self):
    _ensure_activity_state_with_filters(self)
    win = getattr(self, "_activity_window", None)
    if win is not None:
        try:
            if win.winfo_exists():
                _refresh_activity_widgets_with_filters(self)
                self._sync_action_detail()
                self._sync_log_detail()
                win.lift()
                return
        except Exception:
            pass

    win = tk.Toplevel(self.root)
    self._activity_window = win
    win.title(app_dialog_title("Журнал"))
    win.geometry("820x640")
    win.configure(bg=Theme.BG)

    outer = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    outer.pack(fill="both", expand=True, padx=12, pady=12)

    tk.Label(
        outer,
        text="Журнал JARVIS",
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        font=("Segoe UI Semibold", 14),
    ).pack(anchor="w", padx=16, pady=(16, 4))
    note = tk.Label(
        outer,
        text="Здесь видно, что JARVIS понял, что выполнил и можно ли это отменить. Ошибки показываются человеческим языком и теперь их можно фильтровать по типу и поиску.",
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
    actions_filters = tk.Frame(actions_card, bg=Theme.CARD_BG)
    actions_filters.pack(fill="x", padx=14, pady=(14, 0))
    action_search = tk.Entry(
        actions_filters,
        textvariable=self._activity_filter_query_var,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        insertbackground=Theme.FG,
        relief="flat",
    )
    action_search.pack(side="left", fill="x", expand=True, ipady=6)
    action_route_box = ttk.Combobox(
        actions_filters,
        textvariable=self._activity_filter_route_var,
        values=[title for title, _code in ACTION_ROUTE_FILTERS],
        state="readonly",
        style="Jarvis.TCombobox",
        width=18,
    )
    action_route_box.pack(side="left", padx=(8, 0))
    if hasattr(self, "_setup_entry_bindings"):
        try:
            self._setup_entry_bindings(action_search)
        except Exception:
            pass
    if hasattr(self, "_bind_selector_wheel_guard"):
        try:
            self._bind_selector_wheel_guard(action_route_box)
        except Exception:
            pass

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
        text="Сбросить фильтр",
        command=lambda: (self._activity_filter_query_var.set(""), self._activity_filter_route_var.set(ACTION_ROUTE_FILTERS[0][0])),
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
    ).pack(side="left")
    tk.Button(
        actions_footer,
        text="Отменить выбранное",
        command=lambda: self.undo_action_entry(_selected_action_entry_filtered(self)),
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
    logs_filters = tk.Frame(logs_card, bg=Theme.CARD_BG)
    logs_filters.pack(fill="x", padx=14, pady=(14, 0))
    log_search = tk.Entry(
        logs_filters,
        textvariable=self._log_filter_query_var,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        insertbackground=Theme.FG,
        relief="flat",
    )
    log_search.pack(side="left", fill="x", expand=True, ipady=6)
    log_level_box = ttk.Combobox(
        logs_filters,
        textvariable=self._log_filter_level_var,
        values=[title for title, _code in LOG_LEVEL_FILTERS],
        state="readonly",
        style="Jarvis.TCombobox",
        width=18,
    )
    log_level_box.pack(side="left", padx=(8, 0))
    if hasattr(self, "_setup_entry_bindings"):
        try:
            self._setup_entry_bindings(log_search)
        except Exception:
            pass
    if hasattr(self, "_bind_selector_wheel_guard"):
        try:
            self._bind_selector_wheel_guard(log_level_box)
        except Exception:
            pass

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
        text="Сбросить фильтр",
        command=lambda: (self._log_filter_query_var.set(""), self._log_filter_level_var.set(LOG_LEVEL_FILTERS[0][0])),
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
    ).pack(side="left")
    tk.Button(
        logs_footer,
        text="Очистить логи",
        command=lambda: activity_mod._clear_logs(self),
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
    _refresh_activity_widgets_with_filters(self)
    self._sync_action_detail()
    self._sync_log_detail()


def apply_activity_history_filters(app_cls):
    if getattr(app_cls, "_activity_history_filters_applied", False):
        return
    app_cls._activity_history_filters_applied = True
    app_cls._base_ensure_activity_state_with_filters = app_cls._ensure_activity_state
    app_cls._ensure_activity_state = _ensure_activity_state_with_filters
    app_cls._refresh_activity_widgets = _refresh_activity_widgets_with_filters
    app_cls._schedule_activity_filter_refresh = _schedule_activity_filter_refresh
    app_cls.show_history = _show_history_with_filters

    activity_mod._ensure_activity_state = _ensure_activity_state_with_filters
    activity_mod._refresh_activity_widgets = _refresh_activity_widgets_with_filters
    activity_mod._selected_action_entry = _selected_action_entry_filtered
    activity_mod._selected_log_entry = _selected_log_entry_filtered
    activity_mod.show_history = _show_history_with_filters


__all__ = ["apply_activity_history_filters"]

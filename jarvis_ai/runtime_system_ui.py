import tkinter as tk
from tkinter import messagebox, ttk

from .action_permissions import DEFAULT_PERMISSION_MODES, PERMISSION_CATEGORIES, category_label
from .branding import app_brand_name
from .commands import normalize_text
from .environment_doctor import doctor_summary, render_doctor_report, run_environment_doctor
from .scenario_engine import explain_scenario_conditions, upsert_scenario
from .smart_memory import remove_memory_item, upsert_memory_item
from .theme import Theme
from .ui_factory import bind_dynamic_wrap, create_action_grid, create_note_box, create_section_card


def _selected_memory_item(self):
    listbox = getattr(self, "_memory_listbox", None)
    items = getattr(self, "_memory_view_items", [])
    if listbox is None:
        return None
    try:
        selection = listbox.curselection()
    except Exception:
        selection = ()
    if not selection:
        return None
    index = int(selection[0])
    if 0 <= index < len(items):
        return items[index]
    return None


def _selected_scenario_item(self):
    listbox = getattr(self, "_scenario_listbox", None)
    items = getattr(self, "_scenario_view_items", [])
    if listbox is None:
        return None
    try:
        selection = listbox.curselection()
    except Exception:
        selection = ()
    if not selection:
        return None
    index = int(selection[0])
    if 0 <= index < len(items):
        return items[index]
    return None


def _refresh_memory_widgets(self):
    listbox = getattr(self, "_memory_listbox", None)
    summary_var = getattr(self, "_memory_summary_var", None)
    if listbox is None:
        return
    items = list(self._get_memory_items())
    self._memory_view_items = items
    try:
        listbox.delete(0, tk.END)
        for item in items:
            scope = {"personal": "личная", "temporary": "временная", "pinned": "закрепленная"}.get(item.get("scope"), item.get("scope", "личная"))
            prefix = "★ " if item.get("pinned") else ""
            created = str(item.get("created_at", "") or "").strip()[:16]
            listbox.insert(tk.END, f"{prefix}{item.get('title')}  •  {scope}  •  {created or 'без даты'}")
    except Exception:
        pass
    if summary_var is not None:
        summary_var.set("Записей: " + str(len(items)))
    if hasattr(self, "_sync_memory_detail"):
        try:
            self._sync_memory_detail()
        except Exception:
            pass


def _sync_memory_detail(self, *_args):
    var = getattr(self, "_memory_detail_var", None)
    if var is None:
        return
    item = self._selected_memory_item()
    if item is None:
        var.set("Выберите запись памяти, чтобы увидеть что JARVIS запомнил, когда и почему.")
        return
    parts = [
        str(item.get("title", "") or "").strip(),
        str(item.get("value", "") or "").strip(),
        "Когда сохранено: " + (str(item.get("created_at", "") or "").strip() or "неизвестно"),
        "Почему сохранено: " + (str(item.get("why", "") or "").strip() or "Причина не указана"),
        "Источник: " + (str(item.get("source", "") or "").strip() or "chat"),
    ]
    last_used = str(item.get("last_used_at", "") or "").strip()
    if last_used:
        parts.append("Последнее использование: " + last_used)
    var.set("\n".join(parts))


def _refresh_scenario_widgets(self):
    listbox = getattr(self, "_scenario_listbox", None)
    summary_var = getattr(self, "_scenario_summary_var", None)
    if listbox is None:
        return
    items = list(self._get_scenario_items())
    self._scenario_view_items = items
    try:
        listbox.delete(0, tk.END)
        for item in items:
            marker = "● " if item.get("enabled", True) else "○ "
            listbox.insert(tk.END, f"{marker}{item.get('name')}  •  {item.get('summary') or 'без описания'}")
    except Exception:
        pass
    if summary_var is not None:
        current = str(self._cfg().get_current_scenario() or "").strip()
        summary_var.set(f"Сценариев: {len(items)}  •  активен: {current or 'нет'}")


def _memory_editor_window(self, item=None):
    item = dict(item or {})
    win = tk.Toplevel(self.root)
    win.title("Память JARVIS AI 2.0")
    win.geometry("560x420")
    win.configure(bg=Theme.BG)
    win.transient(self.root)
    try:
        win.lift()
        win.focus_force()
    except Exception:
        pass
    card = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=12, pady=12)

    tk.Label(card, text="Память JARVIS", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=14, pady=(14, 4))
    tk.Label(card, text="Сохраните факт, личную заметку или временную подсказку для JARVIS.", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(0, 12))

    title_var = tk.StringVar(value=str(item.get("title", "") or ""))
    scope_items = [("Личная", "personal"), ("Временная", "temporary"), ("Закреплённая", "pinned")]
    current_scope = str(item.get("scope", "personal") or "personal")
    current_scope_label = next((label for label, key in scope_items if key == current_scope), scope_items[0][0])
    scope_var = tk.StringVar(value=current_scope_label)
    tags_var = tk.StringVar(value=", ".join(item.get("tags", []) or []))
    why_var = tk.StringVar(value=str(item.get("why", "") or ""))
    source_var = tk.StringVar(value=str(item.get("source", "") or "chat"))
    pinned_var = tk.BooleanVar(value=bool(item.get("pinned", False)))

    def row(label_text, widget):
        box = tk.Frame(card, bg=Theme.CARD_BG)
        box.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(box, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 4))
        widget.pack(fill="x")

    row("Заголовок", tk.Entry(card, textvariable=title_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, font=("Segoe UI", 10)))
    value_box = tk.Text(card, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, height=8, wrap="word", font=("Segoe UI", 10))
    value_box.insert("1.0", str(item.get("value", "") or ""))
    row("Содержимое", value_box)
    scope_combo = ttk.Combobox(card, textvariable=scope_var, state="readonly", values=[label for label, _ in scope_items])
    row("Тип памяти", scope_combo)
    row("Теги через запятую", tk.Entry(card, textvariable=tags_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, font=("Segoe UI", 10)))
    row("Почему это запомнить", tk.Entry(card, textvariable=why_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, font=("Segoe UI", 10)))
    row("Источник", tk.Entry(card, textvariable=source_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, font=("Segoe UI", 10)))
    pin_row = tk.Frame(card, bg=Theme.CARD_BG)
    pin_row.pack(fill="x", padx=14, pady=(0, 10))
    tk.Checkbutton(pin_row, text="Закрепить запись", variable=pinned_var, bg=Theme.CARD_BG, fg=Theme.FG, selectcolor=Theme.CARD_BG, activebackground=Theme.CARD_BG, activeforeground=Theme.FG).pack(anchor="w")

    actions = tk.Frame(card, bg=Theme.CARD_BG)
    actions.pack(fill="x", padx=14, pady=(6, 14))

    def _save():
        payload = {
            "id": item.get("id", ""),
            "title": str(title_var.get() or "").strip() or str(value_box.get("1.0", "end").strip() or "")[:80],
            "value": str(value_box.get("1.0", "end").strip() or ""),
            "scope": next((key for label, key in scope_items if label == str(scope_var.get() or "").strip()), "personal"),
            "pinned": bool(pinned_var.get()),
            "tags": [part.strip() for part in str(tags_var.get() or "").split(",") if part.strip()],
            "why": str(why_var.get() or "").strip(),
            "source": str(source_var.get() or "").strip() or "chat",
        }
        if not payload["value"]:
            messagebox.showwarning(app_brand_name(), "Заполните текст записи.", parent=win)
            return
        self._set_memory_items(upsert_memory_item(self._get_memory_items(), payload))
        self.set_status_temp("Память обновлена", "ok")
        win.destroy()

    tk.Button(actions, text="Сохранить", command=_save, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right")
    tk.Button(actions, text="Отмена", command=win.destroy, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right", padx=(0, 8))


def _scenario_editor_window(self, item=None):
    item = dict(item or {})
    win = tk.Toplevel(self.root)
    win.title("Сценарии JARVIS AI 2.0")
    win.geometry("620x520")
    win.configure(bg=Theme.BG)
    win.transient(self.root)
    try:
        win.lift()
        win.focus_force()
    except Exception:
        pass
    card = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=12, pady=12)

    tk.Label(card, text="Сценарий", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=14, pady=(14, 4))
    tk.Label(card, text="Один сценарий может включать несколько режимов сразу: плотность UI, фокус, активное прослушивание и тему.", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(0, 12))

    body = tk.Frame(card, bg=Theme.CARD_BG)
    body.pack(fill="both", expand=True, padx=14, pady=(0, 8))

    def field(label_text, variable, values=None):
        box = tk.Frame(body, bg=Theme.CARD_BG)
        box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 4))
        if values is None:
            entry = tk.Entry(box, textvariable=variable, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, font=("Segoe UI", 10))
            entry.pack(fill="x")
            return entry
        combo = ttk.Combobox(box, textvariable=variable, state="readonly", values=values)
        combo.pack(fill="x")
        return combo

    name_var = tk.StringVar(value=str(item.get("name", "") or ""))
    summary_var = tk.StringVar(value=str(item.get("summary", "") or ""))
    trigger_var = tk.StringVar(value=", ".join(item.get("trigger_phrases", []) or []))
    enabled_var = tk.BooleanVar(value=bool(item.get("enabled", True)))
    changes = dict(item.get("changes", {}) or {})
    conditions = dict(item.get("conditions", {}) or {})

    density_items = [("Без изменений", "unchanged"), ("Комфортная", "comfortable"), ("Компактная", "compact")]
    toggle_items = [("Без изменений", "unchanged"), ("Включить", "on"), ("Выключить", "off")]
    theme_items = [("Без изменений", "unchanged"), ("Тёмная", "dark"), ("Светлая", "light")]

    density_value = changes.get("ui_density", "unchanged") if changes.get("ui_density") in {"comfortable", "compact"} else "unchanged"
    focus_value = "on" if changes.get("focus_mode_enabled") is True else "off" if changes.get("focus_mode_enabled") is False else "unchanged"
    theme_value = changes.get("theme_mode", "unchanged") if changes.get("theme_mode") in {"dark", "light"} else "unchanged"
    listen_value = "on" if changes.get("active_listening_enabled") is True else "off" if changes.get("active_listening_enabled") is False else "unchanged"
    boost_value = "on" if changes.get("wake_word_boost") is True else "off" if changes.get("wake_word_boost") is False else "unchanged"

    density_var = tk.StringVar(value=next((label for label, key in density_items if key == density_value), density_items[0][0]))
    focus_var = tk.StringVar(value=next((label for label, key in toggle_items if key == focus_value), toggle_items[0][0]))
    theme_var = tk.StringVar(value=next((label for label, key in theme_items if key == theme_value), theme_items[0][0]))
    listen_var = tk.StringVar(value=next((label for label, key in toggle_items if key == listen_value), toggle_items[0][0]))
    boost_var = tk.StringVar(value=next((label for label, key in toggle_items if key == boost_value), toggle_items[0][0]))
    time_after_var = tk.StringVar(value=str(conditions.get("time_after", "") or ""))
    time_before_var = tk.StringVar(value=str(conditions.get("time_before", "") or ""))
    process_any_var = tk.StringVar(value=", ".join(conditions.get("process_any", []) or []))
    mic_contains_var = tk.StringVar(value=str(conditions.get("mic_contains", "") or ""))

    field("Название", name_var)
    field("Кратко о сценарии", summary_var)
    field("Фразы запуска через запятую", trigger_var)
    field("Плотность интерфейса", density_var, [label for label, _ in density_items])
    field("Фокус-режим", focus_var, [label for label, _ in toggle_items])
    field("Тема", theme_var, [label for label, _ in theme_items])
    field("Активное прослушивание", listen_var, [label for label, _ in toggle_items])
    field("Усиление слова активации", boost_var, [label for label, _ in toggle_items])
    field("Авто: после времени HH:MM", time_after_var)
    field("Авто: до времени HH:MM", time_before_var)
    field("Авто: процессы через запятую", process_any_var)
    field("Авто: микрофон содержит", mic_contains_var)
    tk.Checkbutton(body, text="Сценарий включён", variable=enabled_var, bg=Theme.CARD_BG, fg=Theme.FG, selectcolor=Theme.CARD_BG, activebackground=Theme.CARD_BG, activeforeground=Theme.FG).pack(anchor="w", pady=(2, 0))

    actions = tk.Frame(card, bg=Theme.CARD_BG)
    actions.pack(fill="x", padx=14, pady=(0, 14))

    def _save():
        name = str(name_var.get() or "").strip()
        if not name:
            messagebox.showwarning(app_brand_name(), "Укажите название сценария.", parent=win)
            return
        changes_out = {}
        selected_density = next((key for label, key in density_items if label == str(density_var.get() or "").strip()), "unchanged")
        selected_focus = next((key for label, key in toggle_items if label == str(focus_var.get() or "").strip()), "unchanged")
        selected_theme = next((key for label, key in theme_items if label == str(theme_var.get() or "").strip()), "unchanged")
        selected_listen = next((key for label, key in toggle_items if label == str(listen_var.get() or "").strip()), "unchanged")
        selected_boost = next((key for label, key in toggle_items if label == str(boost_var.get() or "").strip()), "unchanged")
        if selected_density != "unchanged":
            changes_out["ui_density"] = selected_density
        if selected_focus != "unchanged":
            changes_out["focus_mode_enabled"] = selected_focus == "on"
        if selected_theme != "unchanged":
            changes_out["theme_mode"] = selected_theme
        if selected_listen != "unchanged":
            changes_out["active_listening_enabled"] = selected_listen == "on"
        if selected_boost != "unchanged":
            changes_out["wake_word_boost"] = selected_boost == "on"
        conditions_out = {
            "time_after": str(time_after_var.get() or "").strip(),
            "time_before": str(time_before_var.get() or "").strip(),
            "process_any": [part.strip().lower() for part in str(process_any_var.get() or "").split(",") if part.strip()],
            "mic_contains": str(mic_contains_var.get() or "").strip(),
        }
        payload = {
            "id": item.get("id", ""),
            "name": name,
            "summary": str(summary_var.get() or "").strip(),
            "trigger_phrases": [part.strip() for part in str(trigger_var.get() or "").split(",") if part.strip()],
            "enabled": bool(enabled_var.get()),
            "changes": changes_out,
            "conditions": conditions_out,
        }
        self._set_scenario_items(upsert_scenario(self._get_scenario_items(), payload))
        self.set_status_temp("Сценарий сохранен", "ok")
        win.destroy()

    tk.Button(actions, text="Сохранить", command=_save, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right")
    tk.Button(actions, text="Отмена", command=win.destroy, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right", padx=(0, 8))


def _patched_create_settings_tab5(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    _, interface_body = create_section_card(
        body,
        "Режим интерфейса",
        "Обычный режим оставляет только полезный live-контекст, диагностика показывает больше служебных деталей, а фокус убирает всё лишнее ради чата.",
    )
    interface_mode_items = [
        ("Обычный", "normal"),
        ("Диагностика", "diagnostic"),
        ("Фокус", "focus"),
    ]
    current_interface_mode = str(self._cfg().get_workspace_view_mode() or "normal").strip().lower()
    current_interface_label = next((label for label, key in interface_mode_items if key == current_interface_mode), interface_mode_items[0][0])
    interface_mode_var = tk.StringVar(value=current_interface_label)
    interface_mode_box = ttk.Combobox(interface_body, textvariable=interface_mode_var, values=[label for label, _ in interface_mode_items], state="readonly", style="Jarvis.TCombobox")
    interface_mode_box.pack(fill="x", pady=(0, 8))
    self._bind_selector_wheel_guard(interface_mode_box)

    def _save_interface_mode():
        selected = next((key for label, key in interface_mode_items if label == str(interface_mode_var.get() or "").strip()), "normal")
        if callable(getattr(self, "_apply_workspace_view_mode", None)):
            self._apply_workspace_view_mode(selected, persist=True)
        else:
            self._cfg().set_workspace_view_mode(selected)
            self._cfg().set_focus_mode_enabled(selected == "focus")
        self.set_status_temp("Режим интерфейса сохранён", "ok")

    tk.Button(interface_body, text="Сохранить режим интерфейса", command=_save_interface_mode, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(anchor="w", pady=(0, 6))

    _, memory_body = create_section_card(
        body,
        "Память JARVIS",
        "Здесь хранится то, что JARVIS запомнил о вас и о работе. Можно проверить записи и выбрать, как новая память сохраняется по умолчанию.",
    )
    self._memory_summary_var = tk.StringVar(value="Записей: 0")
    tk.Label(memory_body, textvariable=self._memory_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

    memory_mode_items = [
        ("Постоянная", "always"),
        ("Спрашивать перед сохранением", "ask"),
        ("Сначала временная", "temporary_first"),
    ]
    current_memory_mode = str(self._cfg().get_memory_write_mode() or "always").strip().lower()
    current_memory_label = next((label for label, key in memory_mode_items if key == current_memory_mode), memory_mode_items[0][0])
    memory_mode_row = tk.Frame(memory_body, bg=Theme.CARD_BG)
    memory_mode_row.pack(fill="x", pady=(0, 10))
    tk.Label(memory_mode_row, text="Режим сохранения памяти", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w")
    memory_mode_var = tk.StringVar(value=current_memory_label)
    memory_mode_box = ttk.Combobox(
        memory_mode_row,
        textvariable=memory_mode_var,
        values=[label for label, _ in memory_mode_items],
        state="readonly",
        style="Jarvis.TCombobox",
    )
    memory_mode_box.pack(fill="x", pady=(4, 0))
    self._bind_selector_wheel_guard(memory_mode_box)

    def _save_memory_mode():
        selected = next((key for label, key in memory_mode_items if label == str(memory_mode_var.get() or "").strip()), "always")
        self._cfg().set_memory_write_mode(selected)
        self.set_status_temp("Режим памяти сохранён", "ok")

    tk.Button(memory_mode_row, text="Сохранить режим памяти", command=_save_memory_mode, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(anchor="w", pady=(8, 0))

    self._memory_listbox = tk.Listbox(memory_body, bg=Theme.INPUT_BG, fg=Theme.FG, selectbackground=Theme.ACCENT, selectforeground=Theme.FG, relief="flat", bd=0, highlightthickness=0, activestyle="none", font=("Segoe UI", 10), height=6)
    self._memory_listbox.pack(fill="x", pady=(0, 10))
    self._memory_detail_var = tk.StringVar(value="Выберите запись памяти, чтобы увидеть что JARVIS запомнил, когда и почему.")
    memory_detail = tk.Label(memory_body, textvariable=self._memory_detail_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 10))
    memory_detail.pack(fill="x", pady=(0, 10))
    bind_dynamic_wrap(memory_detail, memory_body, padding=20, minimum=220)
    self._memory_listbox.bind("<<ListboxSelect>>", self._sync_memory_detail, add="+")

    def _edit_memory():
        item = self._selected_memory_item()
        if item is None:
            messagebox.showinfo(app_brand_name(), "Сначала выберите запись памяти.", parent=self.root)
            return
        self._memory_editor_window(item)

    def _delete_memory():
        item = self._selected_memory_item()
        if item is None:
            return
        self._set_memory_items(remove_memory_item(self._get_memory_items(), item.get("id")))
        self.set_status_temp("Запись памяти удалена", "ok")

    def _clear_memory():
        if not messagebox.askyesno(app_brand_name(), "Очистить всю память JARVIS?", parent=self.root):
            return
        self._set_memory_items([])
        self.set_status_temp("Память очищена", "ok")

    def _avoid_memory():
        item = self._selected_memory_item()
        if item is None:
            messagebox.showinfo(app_brand_name(), "Сначала выберите запись памяти.", parent=self.root)
            return
        patterns = list(self._cfg().get_memory_avoid_patterns() or [])
        for raw in (item.get("title", ""), item.get("value", "")):
            normalized = normalize_text(str(raw or ""))
            if normalized and normalized not in patterns:
                patterns.append(normalized)
        self._cfg().set_memory_avoid_patterns(patterns)
        self._set_memory_items(remove_memory_item(self._get_memory_items(), item.get("id")))
        self.set_status_temp("Добавил в список «не запоминать такое»", "ok")

    create_action_grid(
        memory_body,
        [
            {"text": "Добавить", "command": self._memory_editor_window, "bg": Theme.ACCENT},
            {"text": "Изменить", "command": _edit_memory},
            {"text": "Удалить", "command": _delete_memory},
            {"text": "Закрепить", "command": lambda: self._memory_editor_window(dict(self._selected_memory_item() or {}, pinned=True, scope="pinned")) if self._selected_memory_item() else messagebox.showinfo(app_brand_name(), "Сначала выберите запись памяти.", parent=self.root)},
            {"text": "Не запоминать такое", "command": _avoid_memory},
            {"text": "Очистить всё", "command": _clear_memory},
        ],
        columns=3,
    )

    _, scenario_body = create_section_card(
        body,
        "Сценарии",
        "Сценарии помогают быстро переключать режимы работы JARVIS: интерфейс, фокус, голос и чувствительность.",
    )
    self._scenario_summary_var = tk.StringVar(value="Сценариев: 0")
    tk.Label(scenario_body, textvariable=self._scenario_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
    self._scenario_listbox = tk.Listbox(scenario_body, bg=Theme.INPUT_BG, fg=Theme.FG, selectbackground=Theme.ACCENT, selectforeground=Theme.FG, relief="flat", bd=0, highlightthickness=0, activestyle="none", font=("Segoe UI", 10), height=6)
    self._scenario_listbox.pack(fill="x", pady=(0, 10))

    def _add_template(name, summary, changes, conditions=None):
        payload = {
            "name": name,
            "summary": summary,
            "enabled": True,
            "changes": dict(changes),
            "conditions": dict(conditions or {}),
            "trigger_phrases": [],
        }
        self._set_scenario_items(upsert_scenario(self._get_scenario_items(), payload))
        self.set_status_temp(f"Шаблон «{name}» добавлен", "ok")

    create_action_grid(
        scenario_body,
        [
            {"text": "Работа", "command": lambda: _add_template("Рабочий режим", "Спокойный интерфейс и активное прослушивание.", {"ui_density": "comfortable", "focus_mode_enabled": False, "active_listening_enabled": True})},
            {"text": "Игра", "command": lambda: _add_template("Игровой режим", "Компактный интерфейс, меньше отвлекающих деталей и выше чувствительность.", {"ui_density": "compact", "focus_mode_enabled": True, "wake_word_boost": True}, {"process_any": ["steam.exe", "robloxplayerbeta.exe"]})},
            {"text": "Ночь", "command": lambda: _add_template("Ночной режим", "Тише, спокойнее и без лишнего фонового шума.", {"ui_density": "comfortable", "focus_mode_enabled": False, "active_listening_enabled": False}, {"time_after": "23:00"})},
            {"text": "Гарнитура", "command": lambda: _add_template("Профиль гарнитуры", "Когда найдена гарнитура, JARVIS делает голосовой профиль чуть увереннее.", {"active_listening_enabled": True, "wake_word_boost": True}, {"mic_contains": "headset"})},
        ],
        columns=2,
    )

    def _edit_scenario():
        item = self._selected_scenario_item()
        if item is None:
            messagebox.showinfo(app_brand_name(), "Сначала выберите сценарий.", parent=self.root)
            return
        self._scenario_editor_window(item)

    def _apply_scenario():
        item = self._selected_scenario_item()
        if item is None:
            return
        message = self._handle_scenario_route({"scenario": item})
        self.add_msg(message, "bot")
        self.set_status_temp("Сценарий применён", "ok")

    def _explain_scenario():
        item = self._selected_scenario_item()
        if item is None:
            messagebox.showinfo(app_brand_name(), "Сначала выберите сценарий.", parent=self.root)
            return
        report = explain_scenario_conditions(self, item)
        if hasattr(self, "_show_text_report_window"):
            self._show_text_report_window("Разбор сценария", report, geometry="760x520")
        else:
            messagebox.showinfo(app_brand_name(), report, parent=self.root)

    def _delete_scenario():
        item = self._selected_scenario_item()
        if item is None:
            return
        remaining = [entry for entry in self._get_scenario_items() if entry.get("id") != item.get("id")]
        self._set_scenario_items(remaining)
        self.set_status_temp("Сценарий удалён", "ok")

    create_action_grid(
        scenario_body,
        [
            {"text": "Добавить", "command": self._scenario_editor_window, "bg": Theme.ACCENT},
            {"text": "Изменить", "command": _edit_scenario},
            {"text": "Применить", "command": _apply_scenario},
            {"text": "Почему не сработал?", "command": _explain_scenario},
            {"text": "Удалить", "command": _delete_scenario},
        ],
        columns=3,
    )

    _, permissions_body = create_section_card(
        body,
        "Опасные действия",
        "Здесь задаётся, когда JARVIS должен спрашивать подтверждение перед выключением ПК, запуском ссылок, скриптов и системных действий. По умолчанию рискованные действия требуют подтверждения прямо в чате.",
    )
    permission_mode_items = [
        ("Всегда спрашивать", "always"),
        ("Разрешать один раз", "ask_once"),
        ("Всегда выполнять", "trust"),
    ]
    permission_modes = dict(DEFAULT_PERMISSION_MODES)
    permission_modes.update(self._cfg().get_dangerous_action_modes() or {})
    permission_vars = {}
    for category in PERMISSION_CATEGORIES:
        row = tk.Frame(permissions_body, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text=category_label(category), bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 4))
        current_label = next((label for label, key in permission_mode_items if key == str(permission_modes.get(category, DEFAULT_PERMISSION_MODES[category]) or "").strip().lower()), permission_mode_items[0][0])
        permission_vars[category] = tk.StringVar(value=current_label)
        combo = ttk.Combobox(row, textvariable=permission_vars[category], values=[label for label, _ in permission_mode_items], state="readonly", style="Jarvis.TCombobox")
        combo.pack(fill="x")
        self._bind_selector_wheel_guard(combo)

    def _save_permissions():
        payload = {}
        for category in PERMISSION_CATEGORIES:
            payload[category] = next((key for label, key in permission_mode_items if label == str(permission_vars[category].get() or "").strip()), DEFAULT_PERMISSION_MODES[category])
        self._cfg().set_dangerous_action_modes(payload)
        self.set_status_temp("Разрешения сохранены", "ok")

    preset_row = tk.Frame(permissions_body, bg=Theme.CARD_BG)
    preset_row.pack(fill="x", pady=(2, 8))

    def _apply_permission_preset(target_mode: str):
        for category in PERMISSION_CATEGORIES:
            label = next((label for label, key in permission_mode_items if key == target_mode), permission_mode_items[0][0])
            permission_vars[category].set(label)

    tk.Button(preset_row, text="Безопасно", command=lambda: _apply_permission_preset("always"), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left")
    tk.Button(preset_row, text="Всегда выполнять", command=lambda: _apply_permission_preset("trust"), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))
    tk.Button(permissions_body, text="Сохранить разрешения", command=_save_permissions, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(anchor="w", pady=(4, 0))

    _, journal_body = create_section_card(
        body,
        "Журнал и отмена",
        "Показывает, что JARVIS понял и сделал, и даёт быстрый доступ к истории и отмене последнего действия.",
    )
    self._human_log_summary_var = getattr(self, "_human_log_summary_var", tk.StringVar(value="Пока без ошибок и предупреждений."))
    tk.Label(journal_body, textvariable=self._human_log_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
    tk.Label(journal_body, textvariable=getattr(self, "_last_action_card_var", tk.StringVar(value="Последнее действие появится здесь.")), bg=Theme.CARD_BG, fg=Theme.FG, justify="left", font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(0, 10))
    create_action_grid(
        journal_body,
        [
            {"text": "Открыть журнал", "command": self.show_history, "bg": Theme.ACCENT},
            {"text": "Отменить последнее", "command": self.undo_last_action},
            {"text": "Центр ошибок", "command": self.show_error_center},
        ],
        columns=3,
    )

    _, doctor_body = create_section_card(
        body,
        "Мастер проверки среды",
        "Проверяет Groq API ключ, Telegram, микрофон, TTS, ffmpeg, сеть, proxy/VPN и пользовательские действия.",
    )
    doctor_summary_var = tk.StringVar(value="Проверка ещё не запускалась.")
    tk.Label(doctor_body, textvariable=doctor_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

    def _run_doctor():
        items = run_environment_doctor(self)
        summary = doctor_summary(items)
        doctor_summary_var.set(summary)
        tone = "ok"
        if any(item.get("status") == "error" for item in items):
            tone = "error"
        elif any(item.get("status") == "warn" for item in items):
            tone = "warn"
        self.set_status_temp(summary, tone, duration_ms=3200)
        self._show_text_report_window("Мастер проверки среды", render_doctor_report(items), geometry="820x680")

    create_action_grid(
        doctor_body,
        [
            {"text": "Запустить проверку", "command": _run_doctor, "bg": Theme.ACCENT},
            {"text": "Проверка готовности", "command": self.run_readiness_master},
            {"text": "Проверка релиза", "command": self.run_release_lock_check},
            {"text": "Обновления", "command": self.check_for_updates_now},
        ],
        columns=2,
    )

    _, system_body = create_section_card(
        body,
        "Системные инструменты",
        "Резервные копии, импорт/экспорт наборов, ZIP с диагностикой и восстановление живут здесь, а не на главном экране.",
    )
    system_actions = [
        {"text": "Резервная копия", "command": self.create_profile_backup_action, "bg": Theme.ACCENT},
        {"text": "Восстановить", "command": self.restore_profile_backup_action},
        {"text": "Пакет поддержки", "command": self.export_diagnostics_bundle_action},
        {"text": "Экспорт набора", "command": self.export_plugin_pack_action},
        {"text": "Импорт набора", "command": self.import_plugin_pack_action},
    ]
    rollback_action = getattr(self, "rollback_last_update_action", None)
    if callable(rollback_action):
        system_actions.append({"text": "Откатить обновление", "command": rollback_action})
    create_action_grid(system_body, system_actions, columns=2)

    _, note_label = create_note_box(
        body,
        "Главный экран должен оставаться разговорным. Память, проверки, разрешения и системные операции собраны здесь, чтобы не перегружать чат.",
        tone="soft",
    )
    bind_dynamic_wrap(note_label, note_label.master, padding=28, minimum=220)

    self._refresh_memory_widgets()
    self._refresh_scenario_widgets()


def _patched_build_embedded_settings_page(self):
    page = type(self)._base_build_embedded_settings_page_v2(self)
    tabs = getattr(self, "embedded_settings_tabs", {})
    if isinstance(tabs, dict):
        if "technical" in tabs and "system" not in tabs:
            tabs["system"] = tabs["technical"]
        if "audio" in tabs and "voice" not in tabs:
            tabs["voice"] = tabs["audio"]
    return page


def register_system_ui(app_cls, settings_mixin_cls=None):
    app_cls._selected_memory_item = _selected_memory_item
    app_cls._selected_scenario_item = _selected_scenario_item
    app_cls._refresh_memory_widgets = _refresh_memory_widgets
    app_cls._refresh_scenario_widgets = _refresh_scenario_widgets
    app_cls._sync_memory_detail = _sync_memory_detail
    app_cls._memory_editor_window = _memory_editor_window
    app_cls._scenario_editor_window = _scenario_editor_window


__all__ = ["register_system_ui"]

import tkinter as tk
from tkinter import messagebox, ttk

from .branding import app_brand_name
from .scenario_engine import upsert_scenario
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
            listbox.insert(tk.END, f"{prefix}{item.get('title')}  •  {scope}")
    except Exception:
        pass
    if summary_var is not None:
        summary_var.set("Записей: " + str(len(items)))


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
    card = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=12, pady=12)

    tk.Label(card, text="Память JARVIS", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=14, pady=(14, 4))
    tk.Label(card, text="Сохраните факт, личную заметку или временную подсказку для JARVIS.", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(0, 12))

    title_var = tk.StringVar(value=str(item.get("title", "") or ""))
    scope_var = tk.StringVar(value=str(item.get("scope", "personal") or "personal"))
    tags_var = tk.StringVar(value=", ".join(item.get("tags", []) or []))
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
    scope_combo = ttk.Combobox(card, textvariable=scope_var, state="readonly", values=["personal", "temporary", "pinned"])
    row("Тип памяти", scope_combo)
    row("Теги через запятую", tk.Entry(card, textvariable=tags_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", bd=0, font=("Segoe UI", 10)))
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
            "scope": str(scope_var.get() or "personal").strip(),
            "pinned": bool(pinned_var.get()),
            "tags": [part.strip() for part in str(tags_var.get() or "").split(",") if part.strip()],
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

    density_var = tk.StringVar(value=changes.get("ui_density", "unchanged") if changes.get("ui_density") in {"comfortable", "compact"} else "unchanged")
    focus_var = tk.StringVar(value="on" if changes.get("focus_mode_enabled") is True else "off" if changes.get("focus_mode_enabled") is False else "unchanged")
    theme_var = tk.StringVar(value=changes.get("theme_mode", "unchanged") if changes.get("theme_mode") in {"dark", "light"} else "unchanged")
    listen_var = tk.StringVar(value="on" if changes.get("active_listening_enabled") is True else "off" if changes.get("active_listening_enabled") is False else "unchanged")
    boost_var = tk.StringVar(value="on" if changes.get("wake_word_boost") is True else "off" if changes.get("wake_word_boost") is False else "unchanged")

    field("Название", name_var)
    field("Кратко о сценарии", summary_var)
    field("Фразы запуска через запятую", trigger_var)
    field("Плотность интерфейса", density_var, ["unchanged", "comfortable", "compact"])
    field("Фокус-режим", focus_var, ["unchanged", "on", "off"])
    field("Тема", theme_var, ["unchanged", "dark", "light"])
    field("Активное прослушивание", listen_var, ["unchanged", "on", "off"])
    field("Wake-word boost", boost_var, ["unchanged", "on", "off"])
    tk.Checkbutton(body, text="Сценарий включен", variable=enabled_var, bg=Theme.CARD_BG, fg=Theme.FG, selectcolor=Theme.CARD_BG, activebackground=Theme.CARD_BG, activeforeground=Theme.FG).pack(anchor="w", pady=(2, 0))

    actions = tk.Frame(card, bg=Theme.CARD_BG)
    actions.pack(fill="x", padx=14, pady=(0, 14))

    def _save():
        name = str(name_var.get() or "").strip()
        if not name:
            messagebox.showwarning(app_brand_name(), "Укажите название сценария.", parent=win)
            return
        changes_out = {}
        if density_var.get() != "unchanged":
            changes_out["ui_density"] = density_var.get()
        if focus_var.get() != "unchanged":
            changes_out["focus_mode_enabled"] = focus_var.get() == "on"
        if theme_var.get() != "unchanged":
            changes_out["theme_mode"] = theme_var.get()
        if listen_var.get() != "unchanged":
            changes_out["active_listening_enabled"] = listen_var.get() == "on"
        if boost_var.get() != "unchanged":
            changes_out["wake_word_boost"] = boost_var.get() == "on"
        payload = {
            "id": item.get("id", ""),
            "name": name,
            "summary": str(summary_var.get() or "").strip(),
            "trigger_phrases": [part.strip() for part in str(trigger_var.get() or "").split(",") if part.strip()],
            "enabled": bool(enabled_var.get()),
            "changes": changes_out,
        }
        self._set_scenario_items(upsert_scenario(self._get_scenario_items(), payload))
        self.set_status_temp("Сценарий сохранен", "ok")
        win.destroy()

    tk.Button(actions, text="Сохранить", command=_save, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right")
    tk.Button(actions, text="Отмена", command=win.destroy, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right", padx=(0, 8))


def _patched_create_settings_tab5(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    _, memory_body = create_section_card(
        body,
        "Память JARVIS",
        "Личная, временная и закрепленная память разделены. Здесь можно быстро менять, удалять и закреплять записи без копания в конфиге.",
    )
    self._memory_summary_var = tk.StringVar(value="Записей: 0")
    tk.Label(memory_body, textvariable=self._memory_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
    self._memory_listbox = tk.Listbox(memory_body, bg=Theme.INPUT_BG, fg=Theme.FG, selectbackground=Theme.ACCENT, selectforeground=Theme.FG, relief="flat", bd=0, highlightthickness=0, activestyle="none", font=("Segoe UI", 10), height=6)
    self._memory_listbox.pack(fill="x", pady=(0, 10))

    def _edit_memory():
        item = self._selected_memory_item()
        if item is None:
            messagebox.showinfo(app_brand_name(), "Сначала выберите запись в памяти.", parent=self.root)
            return
        self._memory_editor_window(item)

    def _delete_memory():
        item = self._selected_memory_item()
        if item is None:
            return
        self._set_memory_items(remove_memory_item(self._get_memory_items(), item.get("id")))
        self.set_status_temp("Запись удалена", "ok")

    def _clear_memory():
        if not messagebox.askyesno(app_brand_name(), "Очистить всю память JARVIS?", parent=self.root):
            return
        self._set_memory_items([])
        self.set_status_temp("Память очищена", "ok")

    create_action_grid(
        memory_body,
        [
            {"text": "Добавить", "command": self._memory_editor_window, "bg": Theme.ACCENT},
            {"text": "Изменить", "command": _edit_memory},
            {"text": "Удалить", "command": _delete_memory},
            {"text": "Закрепить", "command": lambda: self._memory_editor_window(dict(self._selected_memory_item() or {}, pinned=True, scope="pinned")) if self._selected_memory_item() else messagebox.showinfo(app_brand_name(), "Сначала выберите запись.", parent=self.root)},
            {"text": "Очистить все", "command": _clear_memory},
        ],
        columns=2,
    )

    _, scenario_body = create_section_card(
        body,
        "Сценарии",
        "Готовые режимы помогают одним кликом включать рабочий, игровой, ночной или стрим-профиль. Можно редактировать их под себя.",
    )
    self._scenario_summary_var = tk.StringVar(value="Сценариев: 0")
    tk.Label(scenario_body, textvariable=self._scenario_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
    self._scenario_listbox = tk.Listbox(scenario_body, bg=Theme.INPUT_BG, fg=Theme.FG, selectbackground=Theme.ACCENT, selectforeground=Theme.FG, relief="flat", bd=0, highlightthickness=0, activestyle="none", font=("Segoe UI", 10), height=6)
    self._scenario_listbox.pack(fill="x", pady=(0, 10))

    def _add_template(name, summary, changes):
        payload = {
            "name": name,
            "summary": summary,
            "enabled": True,
            "changes": dict(changes),
            "trigger_phrases": [],
        }
        self._set_scenario_items(upsert_scenario(self._get_scenario_items(), payload))
        self.set_status_temp(f"Шаблон «{name}» добавлен", "ok")

    create_action_grid(
        scenario_body,
        [
            {"text": "Рабочий", "command": lambda: _add_template("Рабочий режим", "Спокойный интерфейс и активное прослушивание.", {"ui_density": "comfortable", "focus_mode_enabled": False, "active_listening_enabled": True})},
            {"text": "Игровой", "command": lambda: _add_template("Игровой режим", "Компактнее, меньше отвлечений, выше чувствительность.", {"ui_density": "compact", "focus_mode_enabled": True, "wake_word_boost": True})},
            {"text": "Ночной", "command": lambda: _add_template("Ночной режим", "Тише и спокойнее для поздней работы.", {"ui_density": "comfortable", "focus_mode_enabled": False, "active_listening_enabled": False})},
            {"text": "Стрим", "command": lambda: _add_template("Стрим режим", "Минимум лишнего, быстрая реакция и голос под гарнитуру.", {"ui_density": "compact", "focus_mode_enabled": True, "active_listening_enabled": True, "wake_word_boost": True})},
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
        self.set_status_temp("Сценарий применен", "ok")

    def _delete_scenario():
        item = self._selected_scenario_item()
        if item is None:
            return
        remaining = [entry for entry in self._get_scenario_items() if entry.get("id") != item.get("id")]
        self._set_scenario_items(remaining)
        self.set_status_temp("Сценарий удален", "ok")

    create_action_grid(
        scenario_body,
        [
            {"text": "Добавить", "command": self._scenario_editor_window, "bg": Theme.ACCENT},
            {"text": "Изменить", "command": _edit_scenario},
            {"text": "Применить", "command": _apply_scenario},
            {"text": "Удалить", "command": _delete_scenario},
        ],
        columns=2,
    )

    _, journal_body = create_section_card(
        body,
        "Журнал и отмена",
        "Показывает последние действия JARVIS, что он понял, что выполнил и можно ли это откатить. Ошибки здесь уже переведены на человеческий язык.",
    )
    self._human_log_summary_var = getattr(self, "_human_log_summary_var", tk.StringVar(value="Сбоев не зафиксировано."))
    tk.Label(journal_body, textvariable=self._human_log_summary_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
    tk.Label(
        journal_body,
        textvariable=getattr(self, "_last_action_card_var", tk.StringVar(value="Последнее действие появится здесь.")),
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        justify="left",
        font=("Segoe UI", 10, "bold"),
    ).pack(fill="x", pady=(0, 10))
    create_action_grid(
        journal_body,
        [
            {"text": "Открыть журнал", "command": self.show_history, "bg": Theme.ACCENT},
            {"text": "Отменить последнее", "command": self.undo_last_action},
        ],
        columns=2,
    )

    _, system_body = create_section_card(
        body,
        "Системные инструменты",
        "Здесь живут проверка готовности, проверка релиза, резервные копии, откат после обновления, экспорт диагностики и перенос пользовательских наборов. Домашний экран за счет этого остается спокойнее.",
    )
    create_action_grid(
        system_body,
        [
            {"text": "Проверка готовности", "command": self.run_readiness_master, "bg": Theme.ACCENT},
            {"text": "Проверка релиза", "command": self.run_release_lock_check},
            {"text": "Резервная копия", "command": self.create_profile_backup_action},
            {"text": "Восстановить", "command": self.restore_profile_backup_action},
            {"text": "Откат обновления", "command": self.rollback_last_update_action},
            {"text": "Диагностика ZIP", "command": self.export_diagnostics_bundle_action},
            {"text": "Экспорт набора", "command": self.export_plugin_pack_action},
            {"text": "Импорт набора", "command": self.import_plugin_pack_action},
            {"text": "Обновления", "command": self.check_for_updates_now},
        ],
        columns=2,
    )
    _, note_label = create_note_box(
        body,
        "Если интерфейс начинает перегружаться, оставляйте на домашнем экране только чат и голос, а все глубокие инструменты открывайте отсюда.",
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


def register_system_ui(app_cls, settings_mixin_cls):
    app_cls._selected_memory_item = _selected_memory_item
    app_cls._selected_scenario_item = _selected_scenario_item
    app_cls._refresh_memory_widgets = _refresh_memory_widgets
    app_cls._refresh_scenario_widgets = _refresh_scenario_widgets
    app_cls._memory_editor_window = _memory_editor_window
    app_cls._scenario_editor_window = _scenario_editor_window
    if not hasattr(settings_mixin_cls, "_base_build_embedded_settings_page_v2"):
        settings_mixin_cls._base_build_embedded_settings_page_v2 = settings_mixin_cls._build_embedded_settings_page
    settings_mixin_cls._build_embedded_settings_page = _patched_build_embedded_settings_page
    settings_mixin_cls._create_settings_tab5 = _patched_create_settings_tab5


__all__ = ["register_system_ui"]

import tkinter as tk
from tkinter import messagebox

from ...action_permissions import DEFAULT_PERMISSION_MODES, PERMISSION_CATEGORIES, category_label
from ...branding import app_brand_name
from ...commands import normalize_text
from ...environment_doctor import doctor_summary, render_doctor_report, run_environment_doctor
from ...scenario_engine import explain_scenario_conditions, upsert_scenario
from ...smart_memory import remove_memory_item
from ...theme import Theme
from ...ui_factory import bind_dynamic_wrap, create_action_grid, create_note_box, create_section_card


def build_system_settings_section(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    def selector_row(container, label_text, items, current_key, *, help_text=""):
        labels = [label for label, _key in items]
        current_label = next((label for label, key in items if key == current_key), labels[0])
        row = tk.Frame(container, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=(0, 10))
        self._create_settings_field_header(row, label_text, help_text, font=("Segoe UI Semibold", 10))
        var = tk.StringVar(value=current_label)
        shell, button = self._create_settings_choice_control(row, var, labels, font=("Segoe UI", 10))
        shell.pack(fill="x")

        def selected_key():
            raw = str(var.get() or "").strip()
            return next((key for label, key in items if label == raw), current_key)

        return var, button, selected_key

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
    interface_mode_var, interface_mode_button, interface_mode_selected = selector_row(
        interface_body,
        "Режим интерфейса",
        interface_mode_items,
        current_interface_mode,
    )
    self._settings_system_interface_var = interface_mode_var
    self._settings_system_interface_selector = interface_mode_button

    def _save_interface_mode():
        selected = interface_mode_selected()
        if callable(getattr(self, "_apply_workspace_view_mode", None)):
            self._apply_workspace_view_mode(selected, persist=True)
        else:
            self._cfg().set_workspace_view_mode(selected)
            self._cfg().set_focus_mode_enabled(selected == "focus")
        self._settings_toast("Режим интерфейса сохранён", "ok")

    self._settings_system_save_interface_btn = tk.Button(
        interface_body,
        text="Сохранить режим интерфейса",
        command=_save_interface_mode,
        bg=Theme.ACCENT,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
        cursor="hand2",
    )
    self._settings_system_save_interface_btn.pack(anchor="w", pady=(0, 6))

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
    memory_mode_var, memory_mode_button, memory_mode_selected = selector_row(
        memory_body,
        "Режим сохранения памяти",
        memory_mode_items,
        current_memory_mode,
    )
    self._settings_system_memory_mode_var = memory_mode_var
    self._settings_system_memory_mode_selector = memory_mode_button

    def _save_memory_mode():
        self._cfg().set_memory_write_mode(memory_mode_selected())
        self._settings_toast("Режим памяти сохранён", "ok")

    self._settings_system_save_memory_btn = tk.Button(
        memory_body,
        text="Сохранить режим памяти",
        command=_save_memory_mode,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=12,
        pady=8,
        cursor="hand2",
    )
    self._settings_system_save_memory_btn.pack(anchor="w", pady=(0, 10))

    self._memory_listbox = tk.Listbox(
        memory_body,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        selectbackground=Theme.ACCENT,
        selectforeground=Theme.FG,
        relief="flat",
        bd=0,
        highlightthickness=0,
        activestyle="none",
        font=("Segoe UI", 10),
        height=6,
    )
    self._memory_listbox.pack(fill="x", pady=(0, 10))
    self._memory_detail_var = tk.StringVar(value="Выберите запись памяти, чтобы увидеть что JARVIS запомнил, когда и почему.")
    memory_detail = tk.Label(memory_body, textvariable=self._memory_detail_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 10))
    memory_detail.pack(fill="x", pady=(0, 10))
    bind_dynamic_wrap(memory_detail, memory_body, padding=20, minimum=220)
    self._memory_listbox.bind("<<ListboxSelect>>", self._sync_memory_detail, add="+")

    def _edit_memory():
        item = self._selected_memory_item()
        if item is None:
            self._settings_toast("Сначала выберите запись памяти", "warn")
            return
        self._memory_editor_window(item)

    def _delete_memory():
        item = self._selected_memory_item()
        if item is None:
            self._settings_toast("Сначала выберите запись памяти", "warn")
            return
        self._set_memory_items(remove_memory_item(self._get_memory_items(), item.get("id")))
        self._settings_toast("Запись памяти удалена", "ok")

    def _clear_memory():
        if not messagebox.askyesno(app_brand_name(), "Очистить всю память JARVIS?", parent=self.root):
            return
        self._set_memory_items([])
        self._settings_toast("Память очищена", "ok")

    def _avoid_memory():
        item = self._selected_memory_item()
        if item is None:
            self._settings_toast("Сначала выберите запись памяти", "warn")
            return
        patterns = list(self._cfg().get_memory_avoid_patterns() or [])
        for raw in (item.get("title", ""), item.get("value", "")):
            normalized = normalize_text(str(raw or ""))
            if normalized and normalized not in patterns:
                patterns.append(normalized)
        self._cfg().set_memory_avoid_patterns(patterns)
        self._set_memory_items(remove_memory_item(self._get_memory_items(), item.get("id")))
        self._settings_toast("Добавлено в список «не запоминать такое»", "ok")

    create_action_grid(
        memory_body,
        [
            {"text": "Добавить", "command": self._memory_editor_window, "bg": Theme.ACCENT},
            {"text": "Изменить", "command": _edit_memory},
            {"text": "Удалить", "command": _delete_memory},
            {
                "text": "Закрепить",
                "command": lambda: self._memory_editor_window(dict(self._selected_memory_item() or {}, pinned=True, scope="pinned"))
                if self._selected_memory_item()
                else self._settings_toast("Сначала выберите запись памяти", "warn"),
            },
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
    self._scenario_listbox = tk.Listbox(
        scenario_body,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        selectbackground=Theme.ACCENT,
        selectforeground=Theme.FG,
        relief="flat",
        bd=0,
        highlightthickness=0,
        activestyle="none",
        font=("Segoe UI", 10),
        height=6,
    )
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
        self._settings_toast(f"Шаблон «{name}» добавлен", "ok")

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
            self._settings_toast("Сначала выберите сценарий", "warn")
            return
        self._scenario_editor_window(item)

    def _apply_scenario():
        item = self._selected_scenario_item()
        if item is None:
            self._settings_toast("Сначала выберите сценарий", "warn")
            return
        message = self._handle_scenario_route({"scenario": item})
        self.add_msg(message, "bot")
        self._settings_toast("Сценарий применён", "ok")

    def _explain_scenario():
        item = self._selected_scenario_item()
        if item is None:
            self._settings_toast("Сначала выберите сценарий", "warn")
            return
        report = explain_scenario_conditions(self, item)
        if hasattr(self, "_show_text_report_window"):
            self._show_text_report_window("Разбор сценария", report, geometry="760x520")
        else:
            self._settings_toast("Разбор сценария подготовлен", "ok")

    def _delete_scenario():
        item = self._selected_scenario_item()
        if item is None:
            self._settings_toast("Сначала выберите сценарий", "warn")
            return
        remaining = [entry for entry in self._get_scenario_items() if entry.get("id") != item.get("id")]
        self._set_scenario_items(remaining)
        self._settings_toast("Сценарий удалён", "ok")

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
    permission_selectors = {}
    for category in PERMISSION_CATEGORIES:
        current_mode = str(permission_modes.get(category, DEFAULT_PERMISSION_MODES[category]) or "").strip().lower()
        var, button, selected = selector_row(
            permissions_body,
            category_label(category),
            permission_mode_items,
            current_mode,
        )
        permission_vars[category] = (var, selected)
        permission_selectors[category] = button
    self._settings_system_permission_selectors = permission_selectors

    preset_row = tk.Frame(permissions_body, bg=Theme.CARD_BG)
    preset_row.pack(fill="x", pady=(2, 8))

    def _apply_permission_preset(target_mode: str):
        for category in PERMISSION_CATEGORIES:
            var, _selected = permission_vars[category]
            label = next((label for label, key in permission_mode_items if key == target_mode), permission_mode_items[0][0])
            var.set(label)

    tk.Button(preset_row, text="Безопасно", command=lambda: _apply_permission_preset("always"), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8, cursor="hand2").pack(side="left")
    tk.Button(preset_row, text="Всегда выполнять", command=lambda: _apply_permission_preset("trust"), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8, cursor="hand2").pack(side="left", padx=(8, 0))

    def _save_permissions():
        payload = {}
        for category in PERMISSION_CATEGORIES:
            _var, selected = permission_vars[category]
            payload[category] = selected()
        self._cfg().set_dangerous_action_modes(payload)
        self._settings_toast("Разрешения сохранены", "ok")

    self._settings_system_save_permissions_btn = tk.Button(
        permissions_body,
        text="Сохранить разрешения",
        command=_save_permissions,
        bg=Theme.ACCENT,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
        cursor="hand2",
    )
    self._settings_system_save_permissions_btn.pack(anchor="w", pady=(4, 0))

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

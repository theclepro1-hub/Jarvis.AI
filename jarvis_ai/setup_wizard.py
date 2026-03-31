import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .action_permissions import DEFAULT_PERMISSION_MODES
from .branding import app_brand_name, app_title
from .commands import make_dynamic_key, normalize_text
from .state import CONFIG_MGR
from .theme import Theme
from .ui_factory import bind_dynamic_wrap

class SetupWizard:
    STEP_TITLES = (
        "1/5 — Ключ и профиль",
        "2/5 — Микрофон и голос",
        "3/5 — Интерфейс",
        "4/5 — Приложения и игры",
        "5/5 — Проверка и запуск",
    )

    def __init__(self, parent_app, activation_only: bool = False):
        self.parent = parent_app
        self.activation_only = bool(activation_only)
        self.window = tk.Toplevel(parent_app.root)
        try:
            self.window.withdraw()
        except Exception:
            pass
        self.window.title(
            app_title("Регистрация и активация" if self.activation_only else "Первая настройка", with_version=True)
        )
        self.window.configure(bg=Theme.BG_LIGHT)
        self.window.geometry("980x720" if self.activation_only else "1120x860")
        self.window.minsize(940 if self.activation_only else 1040, 700 if self.activation_only else 820)
        self.window.resizable(True, True)
        self.window.transient(parent_app.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._wizard_clipboard_bound = False
        self._bind_wizard_clipboard_shortcuts()
        try:
            self.window.attributes("-topmost", True)
            self.window.after(200, lambda: self.window.attributes("-topmost", False))
        except Exception:
            pass
        self.step_index = 0
        self.custom_apps_state = list(CONFIG_MGR.get_custom_apps() or [])
        self._initial_active_listening = bool(CONFIG_MGR.get("active_listening_enabled", True))
        self.theme_items = [("Тёмная", "dark"), ("Светлая", "light")]
        self.density_items = [("Комфортный", "comfortable"), ("Компактный", "compact")]
        self.listening_items = [
            ("1 - Базовый", "normal"),
            ("2 - Усиленный", "boost"),
            ("3 - Максимальный", "aggressive"),
        ]
        self.dangerous_mode_items = [
            ("Всегда спрашивать", "ask"),
            ("Разрешать один раз", "ask_once"),
            ("Всегда выполнять", "trust"),
        ]

        self.groq_var = tk.StringVar(value=CONFIG_MGR.get_api_key())
        self.tg_token_var = tk.StringVar(value=CONFIG_MGR.get_telegram_token())
        self.tg_id_var = tk.StringVar(value=str(CONFIG_MGR.get_telegram_user_id() or ""))
        self.user_name_var = tk.StringVar(value=CONFIG_MGR.get_user_name())
        self.user_login_var = tk.StringVar(value=CONFIG_MGR.get_user_login())

        self.music_var = tk.StringVar(value=CONFIG_MGR.get("yandex_music_path", ""))
        self.steam_var = tk.StringVar(value=CONFIG_MGR.get("steam_path", ""))
        self.epic_var = tk.StringVar(value=CONFIG_MGR.get("epic_launcher_path", ""))
        self.discord_var = tk.StringVar(value=CONFIG_MGR.get("discord_candidates", [""])[0] if CONFIG_MGR.get("discord_candidates") else "")
        self.tg_desktop_var = tk.StringVar(value=CONFIG_MGR.get("telegram_desktop_path", ""))
        self.sync_games_var = tk.BooleanVar(value=True)

        current_theme = str(CONFIG_MGR.get_theme_mode() or "dark").strip().lower()
        if current_theme not in {"dark", "light"}:
            current_theme = "dark"
        current_density = str(CONFIG_MGR.get_ui_density() or "comfortable").strip().lower()
        if current_density not in {"comfortable", "compact"}:
            current_density = "comfortable"
        current_theme_label = next((lbl for lbl, key in self.theme_items if key == current_theme), self.theme_items[0][0])
        current_density_label = next((lbl for lbl, key in self.density_items if key == current_density), self.density_items[0][0])
        current_listening = CONFIG_MGR.get_listening_profile()
        current_listening_label = next((lbl for lbl, key in self.listening_items if key == current_listening), self.listening_items[0][0])
        self.mic_names = list(self.parent._get_microphone_devices() or [])
        selected_mic = str(CONFIG_MGR.get_mic_device_name() or self.parent.get_selected_microphone_name() or "").strip()
        if selected_mic and selected_mic not in self.mic_names:
            self.mic_names.insert(0, selected_mic)
        if not self.mic_names:
            self.mic_names = ["Авто"]
        self.mic_var = tk.StringVar(value=selected_mic or self.mic_names[0])
        self.theme_var = tk.StringVar(value=current_theme_label)
        self.density_var = tk.StringVar(value=current_density_label)
        self.listening_var = tk.StringVar(value=current_listening_label)
        self.voice_rate_var = tk.IntVar(value=int(CONFIG_MGR.get_voice_rate()))
        self.voice_volume_var = tk.DoubleVar(value=float(CONFIG_MGR.get_voice_volume()))
        self.active_listening_var = tk.BooleanVar(value=bool(CONFIG_MGR.get("active_listening_enabled", True)))
        self.free_chat_var = tk.BooleanVar(value=bool(CONFIG_MGR.get("free_chat_mode", False)))
        self.test_command_var = tk.StringVar(value="привет")
        current_dangerous_modes = dict(CONFIG_MGR.get("dangerous_action_modes", {}) or {})
        dangerous_values = [
            str(current_dangerous_modes.get(category, DEFAULT_PERMISSION_MODES[category]) or "").strip().lower()
            for category in DEFAULT_PERMISSION_MODES
        ]
        dangerous_mode_key = "ask"
        if dangerous_values and all(value == "trust" for value in dangerous_values):
            dangerous_mode_key = "trust"
        elif dangerous_values and all(value == "ask_once" for value in dangerous_values):
            dangerous_mode_key = "ask_once"
        self.dangerous_mode_var = tk.StringVar(
            value=next((label for label, key in self.dangerous_mode_items if key == dangerous_mode_key), self.dangerous_mode_items[0][0])
        )

        self._create_widgets()
        self._render_step()
        self._sync_to_parent_geometry()
        self._show_ready()

    def _on_close_request(self):
        if self.parent._startup_gate_setup and not str(self.groq_var.get() or "").strip():
            messagebox.showwarning(app_brand_name(), "Сначала введите Groq API ключ на шаге 1.")
            return
        try:
            self.window.destroy()
        finally:
            self.parent.on_setup_wizard_closed()

    def _setup_entry_bindings(self, entry):
        try:
            self.parent._setup_entry_bindings(entry)
        except Exception:
            pass

    def _paste_to_focused(self, _event=None):
        target = None
        try:
            target = self.window.focus_get() or self.parent.root.focus_get()
        except Exception:
            target = None
        if target is not None:
            try:
                if self.parent._insert_clipboard_into_widget(target):
                    return "break"
            except Exception:
                pass
        return None

    def _layout_aware_paste_to_focused(self, event=None):
        try:
            if self.parent._matches_ctrl_shortcut(event, "v"):
                return self._paste_to_focused(event)
        except Exception:
            pass
        return None

    def _bind_wizard_clipboard_shortcuts(self):
        if self._wizard_clipboard_bound:
            return
        try:
            for seq in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
                self.window.bind(seq, self._paste_to_focused, add="+")
            self.window.bind("<Control-KeyPress>", self._layout_aware_paste_to_focused, add="+")
            self._wizard_clipboard_bound = True
        except Exception:
            self._wizard_clipboard_bound = False

    def _sync_to_parent_geometry(self):
        try:
            self.parent.root.update_idletasks()
        except Exception:
            pass
        try:
            parent_state = str(self.parent.root.state() or "").lower()
        except Exception:
            parent_state = "normal"
        if parent_state == "zoomed":
            try:
                self.window.state("zoomed")
                return
            except Exception:
                pass
        try:
            geometry = str(self.parent.root.winfo_geometry() or "").strip()
        except Exception:
            geometry = ""
        if geometry and "x" in geometry and "+" in geometry:
            try:
                self.window.geometry(geometry)
            except Exception:
                pass

    def _show_ready(self):
        try:
            self.window.update_idletasks()
        except Exception:
            pass
        try:
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
        except Exception:
            pass

    def _create_widgets(self):
        root = tk.Frame(self.window, bg=Theme.BG_LIGHT)
        root.pack(fill="both", expand=True, padx=18, pady=18)

        head = tk.Frame(root, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        head.pack(fill="x")
        title_text = "Регистрация и активация" if self.activation_only else "Мастер первого запуска"
        subtitle_text = (
            "Введите ключ и базовые данные, затем приложение откроется без промежуточных экранов."
            if self.activation_only
            else "Пройдем 3 шага и сразу можно работать."
        )
        tk.Label(head, text=title_text, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(head, text=subtitle_text, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(0, 10))

        self.step_label = tk.Label(head, text="", bg=Theme.CARD_BG, fg=Theme.ACCENT, font=("Segoe UI", 10, "bold"))
        self.step_label.pack(anchor="w", padx=14, pady=(0, 12))

        self.body = tk.Frame(root, bg=Theme.BG_LIGHT, highlightbackground=Theme.BORDER, highlightthickness=1)
        self.body.pack(fill="both", expand=True, pady=(12, 0))
        self.body_canvas = tk.Canvas(self.body, bg=Theme.BG_LIGHT, highlightthickness=0, bd=0)
        self.body_scroll = ttk.Scrollbar(self.body, orient="vertical", command=self.body_canvas.yview, style="Jarvis.Vertical.TScrollbar")
        self.body_scroll.pack(side="right", fill="y")
        self.body_canvas.pack(side="left", fill="both", expand=True)
        self.body_inner = tk.Frame(self.body_canvas, bg=Theme.BG_LIGHT)
        self.body_window_id = self.body_canvas.create_window((0, 0), window=self.body_inner, anchor="nw")
        self.body_canvas.configure(yscrollcommand=self.body_scroll.set)

        def _sync_wizard_body(_event=None):
            try:
                self.body_canvas.configure(scrollregion=self.body_canvas.bbox("all"))
                self.body_canvas.itemconfigure(self.body_window_id, width=self.body_canvas.winfo_width())
            except Exception:
                pass

        self.body_inner.bind("<Configure>", _sync_wizard_body, add="+")
        self.body_canvas.bind("<Configure>", lambda e: self.body_canvas.itemconfigure(self.body_window_id, width=e.width), add="+")
        self.parent._register_scroll_target(self.body_canvas)

        footer = tk.Frame(root, bg=Theme.BG_LIGHT)
        footer.pack(fill="x", pady=(12, 0))
        self.prev_btn = tk.Button(footer, text="Назад", command=self.prev_step, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8)
        self.prev_btn.pack(side="left")
        self.skip_btn = tk.Button(
            footer,
            text="Пропустить этап",
            command=self.skip_step,
            bg="#2dd4bf",
            fg="#072a22",
            relief="flat",
            padx=14,
            pady=8,
        )
        self.skip_btn.pack(side="left", padx=(8, 0))
        self.next_btn = tk.Button(footer, text="Далее", command=self.next_step, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=16, pady=8)
        self.next_btn.pack(side="right")

        if self.activation_only:
            self.prev_btn.configure(state="disabled")
            self.skip_btn.pack_forget()
            self.next_btn.configure(text="Активировать и открыть чат")

    def browse_file(self, var):
        filename = filedialog.askopenfilename(title="Выберите исполняемый файл", filetypes=[("Executable", "*.exe")])
        if filename:
            var.set(filename)

    def _clear_body(self):
        for child in self.body_inner.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    def _paste_var_from_clipboard(self, var: tk.StringVar):
        try:
            value = str(self.window.clipboard_get() or "")
            if value:
                var.set(value)
        except Exception:
            pass

    def _row_entry(self, parent, label: str, var: tk.StringVar, show: str = "", paste_button: bool = False):
        row = tk.Frame(parent, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
        entry = tk.Entry(row, textvariable=var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat", show=show)
        entry.pack(side="left", fill="x", expand=True, ipady=7)
        self._setup_entry_bindings(entry)
        if paste_button:
            tk.Button(
                row,
                text="Вставить",
                command=lambda v=var: self._paste_var_from_clipboard(v),
                bg=Theme.BUTTON_BG,
                fg=Theme.FG,
                relief="flat",
                padx=8,
            ).pack(side="right", padx=(8, 0))
        return entry

    def _row_path(self, parent, label: str, var: tk.StringVar):
        row = tk.Frame(parent, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
        entry = tk.Entry(row, textvariable=var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat")
        entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        self._setup_entry_bindings(entry)
        tk.Button(row, text="Обзор", command=lambda: self.browse_file(var), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10).pack(side="right")
        return entry

    def _row_combo(self, parent, label: str, var: tk.StringVar, values):
        row = tk.Frame(parent, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
        box = ttk.Combobox(row, textvariable=var, values=list(values), state="readonly", style="Jarvis.TCombobox")
        box.pack(side="left", fill="x", expand=True)
        self.parent._bind_selector_wheel_guard(box)
        return box

    def _render_step(self):
        self._clear_body()
        if self.activation_only:
            self.step_label.configure(text="Регистрация")
            self.prev_btn.configure(state="disabled")
            self.next_btn.configure(text="Активировать и открыть чат")
            if self.skip_btn.winfo_manager():
                self.skip_btn.configure(state="disabled")
        else:
            self.step_label.configure(text=self.STEP_TITLES[self.step_index])
            self.prev_btn.configure(state="normal" if self.step_index > 0 else "disabled")
            self.skip_btn.configure(state="normal" if self.step_index in (1, 2) else "disabled")
            self.next_btn.configure(text="Завершить" if self.step_index == 4 else "Далее")

        card = tk.Frame(self.body_inner, bg=Theme.CARD_BG)
        card.pack(fill="x", padx=14, pady=14)

        if self.activation_only:
            tk.Label(card, text="Активация доступа", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 8), padx=10)
            body = tk.Frame(card, bg=Theme.CARD_BG)
            body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self._row_entry(body, "Groq API ключ", self.groq_var, show="•", paste_button=True)
            self._row_entry(body, "Telegram Bot Token", self.tg_token_var, show="•", paste_button=True)
            self._row_entry(body, "ID пользователя Telegram", self.tg_id_var, paste_button=True)
            self._row_entry(body, "Имя пользователя", self.user_name_var)
            self._row_entry(body, "Логин пользователя", self.user_login_var)
            self._row_combo(body, "Опасные действия", self.dangerous_mode_var, [item[0] for item in self.dangerous_mode_items])
            tk.Label(
                body,
                text="Вставка работает через Ctrl+V, Shift+Insert и правую кнопку мыши.\nБез API-ключа чат не откроется. Здесь же можно сразу выбрать, как JARVIS должен вести себя с опасными командами.",
                bg=Theme.CARD_BG,
                fg=Theme.FG_SECONDARY,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))
            return

        if self.step_index == 0:
            tk.Label(card, text="Ключи и доступ", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 8), padx=10)
            body = tk.Frame(card, bg=Theme.CARD_BG)
            body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self._row_entry(body, "Groq API ключ", self.groq_var, show="•")
            self._row_entry(body, "Telegram Bot Token", self.tg_token_var, show="•")
            self._row_entry(body, "ID пользователя Telegram", self.tg_id_var)
            self._row_entry(body, "Имя пользователя", self.user_name_var)
            self._row_entry(body, "Логин пользователя", self.user_login_var)
            self._row_combo(body, "Опасные действия", self.dangerous_mode_var, [item[0] for item in self.dangerous_mode_items])
            tk.Label(
                body,
                text="Telegram можно заполнить позже. Для голоса и чата достаточно API ключа. Режим опасных действий можно оставить безопасным и поменять позже в настройках.",
                bg=Theme.CARD_BG,
                fg=Theme.FG_SECONDARY,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))
            return

        if self.step_index == 1:
            tk.Label(card, text="Микрофон и голос", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 8), padx=10)
            body = tk.Frame(card, bg=Theme.CARD_BG)
            body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            mic_row = tk.Frame(body, bg=Theme.CARD_BG)
            mic_row.pack(fill="x", pady=4)
            tk.Label(mic_row, text="Микрофон", bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
            mic_box = ttk.Combobox(mic_row, textvariable=self.mic_var, values=self.mic_names, state="readonly", style="Jarvis.TCombobox")
            mic_box.pack(side="left", fill="x", expand=True)
            self.parent._bind_selector_wheel_guard(mic_box)

            listen_row = tk.Frame(body, bg=Theme.CARD_BG)
            listen_row.pack(fill="x", pady=4)
            tk.Label(listen_row, text="Слышимость голоса", bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
            listening_box = ttk.Combobox(listen_row, textvariable=self.listening_var, values=[x[0] for x in self.listening_items], state="readonly", style="Jarvis.TCombobox")
            listening_box.pack(side="left", fill="x", expand=True)
            self.parent._bind_selector_wheel_guard(listening_box)
            tk.Label(body, text="⚠ Усиленные режимы могут улавливать шумы и посторонние голоса.", bg=Theme.CARD_BG, fg=Theme.STATUS_WARN).pack(anchor="w", pady=(2, 8))

            tk.Label(body, text="Скорость голоса", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w")
            rate_value_var = tk.StringVar(value=f"{self.voice_rate_var.get()} символов/мин")
            rate_scale = tk.Scale(
                body,
                from_=150,
                to=350,
                orient="horizontal",
                variable=self.voice_rate_var,
                showvalue=False,
                bg=Theme.CARD_BG,
                fg=Theme.FG,
                troughcolor=Theme.BUTTON_BG,
                highlightthickness=0,
                relief="flat",
                command=lambda _v: rate_value_var.set(f"{int(self.voice_rate_var.get())} символов/мин"),
            )
            rate_scale.pack(fill="x")
            self.parent._bind_selector_wheel_guard(rate_scale)
            tk.Label(body, textvariable=rate_value_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY).pack(anchor="e")

            tk.Label(body, text="Громкость", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(6, 0))
            volume_value_var = tk.StringVar(value=f"{self.voice_volume_var.get():.2f}")
            volume_scale = tk.Scale(
                body,
                from_=0.2,
                to=1.0,
                resolution=0.01,
                orient="horizontal",
                variable=self.voice_volume_var,
                showvalue=False,
                bg=Theme.CARD_BG,
                fg=Theme.FG,
                troughcolor=Theme.BUTTON_BG,
                highlightthickness=0,
                relief="flat",
                command=lambda _v: volume_value_var.set(f"{self.voice_volume_var.get():.2f}"),
            )
            volume_scale.pack(fill="x")
            self.parent._bind_selector_wheel_guard(volume_scale)
            tk.Label(body, textvariable=volume_value_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY).pack(anchor="e")

            tk.Checkbutton(
                body,
                text="Активное прослушивание (реакция на слово «Джарвис»)",
                variable=self.active_listening_var,
                bg=Theme.CARD_BG,
                fg=Theme.FG,
                selectcolor=Theme.INPUT_BG,
                activebackground=Theme.CARD_BG,
                activeforeground=Theme.FG,
            ).pack(anchor="w", pady=(8, 2))

            voice_actions = tk.Frame(body, bg=Theme.CARD_BG)
            voice_actions.pack(fill="x", pady=(10, 0))
            tk.Button(voice_actions, text="Обучить голос", command=self.parent.run_voice_training_wizard, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=10, pady=8).pack(side="left")
            tk.Button(voice_actions, text="Проверка готовности", command=self.parent.run_readiness_master, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10, pady=8).pack(side="left", padx=(8, 0))

            note = tk.Label(
                body,
                text="Сначала выберите микрофон и прогоните обучение слышимости. Так JARVIS будет заметно лучше реагировать на голос и слово активации.",
                bg=Theme.CARD_BG,
                fg=Theme.FG_SECONDARY,
                justify="left",
                wraplength=720,
            )
            note.pack(anchor="w", pady=(12, 0))
            bind_dynamic_wrap(note, body, padding=28, minimum=220)
            return

        if self.step_index == 2:
            tk.Label(card, text="Интерфейс", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 8), padx=10)
            body = tk.Frame(card, bg=Theme.CARD_BG)
            body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            theme_row = tk.Frame(body, bg=Theme.CARD_BG)
            theme_row.pack(fill="x", pady=4)
            tk.Label(theme_row, text="Тема", bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
            theme_box = ttk.Combobox(theme_row, textvariable=self.theme_var, values=[x[0] for x in self.theme_items], state="readonly", style="Jarvis.TCombobox")
            theme_box.pack(side="left", fill="x", expand=True)
            self.parent._bind_selector_wheel_guard(theme_box)

            density_row = tk.Frame(body, bg=Theme.CARD_BG)
            density_row.pack(fill="x", pady=4)
            tk.Label(density_row, text="Плотность интерфейса", bg=Theme.CARD_BG, fg=Theme.FG, width=24, anchor="w").pack(side="left")
            density_box = ttk.Combobox(density_row, textvariable=self.density_var, values=[x[0] for x in self.density_items], state="readonly", style="Jarvis.TCombobox")
            density_box.pack(side="left", fill="x", expand=True)
            self.parent._bind_selector_wheel_guard(density_box)

            tk.Checkbutton(
                body,
                text="Свободный режим общения (более живые и длинные ответы)",
                variable=self.free_chat_var,
                bg=Theme.CARD_BG,
                fg=Theme.FG,
                selectcolor=Theme.INPUT_BG,
                activebackground=Theme.CARD_BG,
                activeforeground=Theme.FG,
            ).pack(anchor="w", pady=(8, 2))

            note = tk.Label(
                body,
                text="Для обычного использования лучше держать комфортный режим. Компактный подойдет, если экран небольшой или хочется видеть больше элементов сразу.",
                bg=Theme.CARD_BG,
                fg=Theme.FG_SECONDARY,
                justify="left",
                wraplength=720,
            )
            note.pack(anchor="w", pady=(10, 0))
            bind_dynamic_wrap(note, body, padding=28, minimum=220)
            return

        if self.step_index == 3:
            tk.Label(card, text="Приложения и игры", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 8), padx=10)
            body = tk.Frame(card, bg=Theme.CARD_BG)
            body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            self._row_path(body, "Яндекс.Музыка", self.music_var)
            self._row_path(body, "Steam", self.steam_var)
            self._row_path(body, "Epic Launcher", self.epic_var)
            self._row_path(body, "Discord", self.discord_var)
            self._row_path(body, "Telegram Desktop", self.tg_desktop_var)

            tk.Checkbutton(
                body,
                text="Автоматически подтянуть игры из лаунчеров",
                variable=self.sync_games_var,
                bg=Theme.CARD_BG,
                fg=Theme.FG,
                selectcolor=Theme.INPUT_BG,
                activebackground=Theme.CARD_BG,
                activeforeground=Theme.FG,
            ).pack(anchor="w", pady=(8, 6))

            tk.Label(body, text="Свои приложения", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 4))
            list_wrap = tk.Frame(body, bg=Theme.CARD_BG)
            list_wrap.pack(fill="x")
            self.custom_listbox = tk.Listbox(list_wrap, bg=Theme.INPUT_BG, fg=Theme.FG, relief="flat", selectbackground=Theme.ACCENT, height=9, bd=0, highlightthickness=0)
            self.custom_listbox.pack(side="left", fill="both", expand=True)
            sc = ttk.Scrollbar(list_wrap, command=self.custom_listbox.yview, style="Jarvis.Vertical.TScrollbar")
            sc.pack(side="right", fill="y")
            self.custom_listbox.configure(yscrollcommand=sc.set)
            self._refresh_custom_apps_list()
            btns = tk.Frame(body, bg=Theme.CARD_BG)
            btns.pack(fill="x", pady=(6, 0))
            tk.Button(btns, text="+ Добавить приложение", command=self._add_custom_app_from_wizard, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10).pack(side="left")
            tk.Button(btns, text="Удалить выбранное", command=self._remove_custom_app_from_wizard, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10).pack(side="left", padx=(8, 0))
            return

        tk.Label(card, text="Проверка и запуск", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 8), padx=10)
        body = tk.Frame(card, bg=Theme.CARD_BG)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        summary = tk.Label(
            body,
            text=(
                f"Микрофон: {self.mic_var.get() or 'авто'}\n"
                f"Плотность интерфейса: {self.density_var.get()}\n"
                f"Тема: {self.theme_var.get()}\n"
                f"Слышимость: {self.listening_var.get()}"
            ),
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 10),
        )
        summary.pack(anchor="w", pady=(0, 12))

        self._row_entry(body, "Тестовая команда", self.test_command_var)
        tk.Label(
            body,
            text="После завершения мастер сразу откроет чат и отправит эту пробную команду, чтобы можно было быстро проверить, как всё работает.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=720,
        ).pack(anchor="w", pady=(8, 12))

        actions = tk.Frame(body, bg=Theme.CARD_BG)
        actions.pack(fill="x")
        tk.Button(actions, text="Проверка готовности", command=self.parent.run_readiness_master, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left")
        tk.Button(actions, text="Центр голоса", command=lambda: self.parent.open_full_settings_view("voice"), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))

    def _refresh_custom_apps_list(self):
        if not hasattr(self, "custom_listbox"):
            return
        self.custom_listbox.delete(0, tk.END)
        for item in self.custom_apps_state:
            self.custom_listbox.insert(tk.END, item.get("name", "Без имени"))
        if not self.custom_apps_state:
            self.custom_listbox.insert(tk.END, "Пока пусто")

    def _add_custom_app_from_wizard(self):
        path_value = filedialog.askopenfilename(
            title="Выберите приложение",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            parent=self.window,
        )
        if not path_value:
            return
        default_name = os.path.splitext(os.path.basename(path_value))[0]
        name = simpledialog.askstring("Название", "Как назвать приложение в командах?", initialvalue=default_name, parent=self.window)
        if not name:
            return
        key = make_dynamic_key(name, "custom")
        exists = {str(a.get("key", "")).strip().lower() for a in self.custom_apps_state}
        if key in exists:
            key = f"{key}_{len(self.custom_apps_state) + 1}"
        exe_name = os.path.basename(path_value)
        self.custom_apps_state.append(
            {
                "key": key,
                "name": name.strip(),
                "launch": path_value,
                "aliases": [normalize_text(name)],
                "close_exes": [exe_name] if exe_name else [],
                "source": "custom",
            }
        )
        self._refresh_custom_apps_list()

    def _remove_custom_app_from_wizard(self):
        if not hasattr(self, "custom_listbox"):
            return
        sel = self.custom_listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.custom_apps_state):
            self.custom_apps_state.pop(idx)
        self._refresh_custom_apps_list()

    def prev_step(self):
        self.step_index = max(0, self.step_index - 1)
        self._render_step()

    def next_step(self):
        if self.activation_only:
            if not str(self.groq_var.get() or "").strip():
                messagebox.showwarning(app_brand_name(), "Введите Groq API ключ, чтобы продолжить.")
                return
            self.save_and_close()
            return
        if self.step_index == 0 and not str(self.groq_var.get() or "").strip():
            messagebox.showwarning(app_brand_name(), "Введите Groq API ключ, чтобы продолжить.")
            return
        if self.step_index < 4:
            self.step_index += 1
            self._render_step()
            return
        self.save_and_close()

    def skip_step(self):
        if self.step_index in (1, 2, 3, 4):
            self.next_step()

    def save_and_close(self):
        if not str(self.groq_var.get() or "").strip():
            messagebox.showwarning(app_brand_name(), "Введите Groq API ключ, чтобы открыть чат.")
            self.step_index = 0
            self._render_step()
            return
        try:
            tg_id = int(self.tg_id_var.get().strip()) if self.tg_id_var.get().strip() else 0
        except Exception:
            tg_id = 0

        theme_key = next((key for lbl, key in self.theme_items if lbl == self.theme_var.get().strip()), CONFIG_MGR.get_theme_mode())
        density_key = next((key for lbl, key in self.density_items if lbl == self.density_var.get().strip()), CONFIG_MGR.get_ui_density())
        listening_key = next((key for lbl, key in self.listening_items if lbl == self.listening_var.get().strip()), CONFIG_MGR.get_listening_profile())
        selected_mic = str(self.mic_var.get() or "").strip()
        mic_index = None
        actual_mics = list(self.parent._get_microphone_devices() or [])
        if selected_mic and selected_mic in actual_mics:
            try:
                candidate_index = actual_mics.index(selected_mic)
                if 0 <= candidate_index < len(actual_mics):
                    mic_index = candidate_index
            except Exception:
                mic_index = None

        updates = {
            "api_key": self.groq_var.get().strip(),
            "telegram_token": self.tg_token_var.get().strip(),
            "telegram_user_id": tg_id,
            "allowed_user_ids": [tg_id] if tg_id else [],
            "user_name": self.user_name_var.get().strip(),
            "user_login": self.user_login_var.get().strip(),
            "yandex_music_path": self.music_var.get().strip(),
            "steam_path": self.steam_var.get().strip(),
            "epic_launcher_path": self.epic_var.get().strip(),
            "discord_candidates": [self.discord_var.get().strip()] if self.discord_var.get().strip() else [],
            "telegram_desktop_path": self.tg_desktop_var.get().strip(),
            "custom_apps": self.custom_apps_state,
            "mic_device_index": mic_index,
            "mic_device_name": selected_mic,
            "theme_mode": theme_key,
            "ui_density": density_key,
            "voice_rate": int(self.voice_rate_var.get()),
            "voice_volume": float(self.voice_volume_var.get()),
            "listening_profile": listening_key,
            "active_listening_enabled": bool(self.active_listening_var.get()),
            "free_chat_mode": bool(self.free_chat_var.get()),
        }
        dangerous_mode_key = next((key for label, key in self.dangerous_mode_items if label == self.dangerous_mode_var.get().strip()), "ask")
        updates["dangerous_action_modes"] = {category: dangerous_mode_key for category in DEFAULT_PERMISSION_MODES}
        CONFIG_MGR.set_many(updates)
        if self.sync_games_var.get():
            try:
                self.parent.sync_launcher_games(show_message=False)
            except Exception:
                pass
        CONFIG_MGR.set_first_run_done()
        self.parent.reload_services()
        self.parent.set_density_mode(density_key)
        self.parent.apply_theme_runtime()
        try:
            self.parent.apply_listening_profile(listening_key)
        except Exception:
            pass
        self.parent.refresh_mic_status_label()
        self.parent.refresh_output_status_label()
        self.parent.refresh_tts_status_label()
        if self._initial_active_listening and not bool(self.active_listening_var.get()):
            messagebox.showinfo(
                app_brand_name(),
                "Активное прослушивание отключено.\nТеперь на слово «Джарвис» помощник не отзывается.",
                parent=self.window,
            )
        messagebox.showinfo(
            app_brand_name(),
            "Вы успешно всё настроили.\nЗа программу спасибо скажите Арсланке, он старался 🙂",
            parent=self.window,
        )
        try:
            self.window.destroy()
        finally:
            self.parent.on_setup_wizard_closed()
        test_command = str(self.test_command_var.get() or "").strip()
        if test_command:
            try:
                self.parent.root.after(450, lambda cmd=test_command: self.parent.executor.submit(self.parent.process_query, cmd))
            except Exception:
                pass

    def skip(self):
        CONFIG_MGR.set_first_run_done()
        try:
            self.window.destroy()
        finally:
            self.parent.on_setup_wizard_closed()

__all__ = ["SetupWizard"]

import tkinter as tk

from ...theme import Theme
from ...ui_factory import bind_dynamic_wrap, create_action_grid


def build_voice_settings_section(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    card = tk.Frame(body, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    card.pack(fill="x", padx=18, pady=(0, 14))
    head = tk.Frame(card, bg=Theme.CARD_BG)
    head.pack(fill="x", padx=16, pady=(16, 8))
    tk.Label(head, text="Центр голоса", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 14)).pack(side="left")
    tk.Button(
        head,
        text="Обучить голос",
        command=self.run_voice_training_wizard,
        bg=Theme.ACCENT,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
        cursor="hand2",
    ).pack(side="right")

    desc = tk.Label(
        card,
        text="Один экран для проверки микрофона: живой уровень, отладка слова активации, тестовая запись, прослушивание и автоподбор профиля.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=("Segoe UI", 10),
    )
    desc.pack(fill="x", padx=16, pady=(0, 12))
    bind_dynamic_wrap(desc, card, padding=34, minimum=280)

    self.voice_meter_var = getattr(self, "voice_meter_var", tk.StringVar(value="Уровень микрофона: жду сигнал..."))
    self.wake_debug_var = getattr(self, "wake_debug_var", tk.StringVar(value="Слово активации: жду «джарвис»."))
    self.voice_last_heard_var = getattr(self, "voice_last_heard_var", tk.StringVar(value="Пока нет распознанных фраз."))

    meter_label = tk.Label(card, textvariable=self.voice_meter_var, bg=Theme.CARD_BG, fg=Theme.FG, justify="left", font=("Segoe UI", 10, "bold"))
    meter_label.pack(fill="x", padx=16)
    bind_dynamic_wrap(meter_label, card, padding=34, minimum=280)

    secondary_canvas = getattr(self, "voice_meter_canvas_secondary", None)
    secondary_exists = False
    if secondary_canvas is not None:
        try:
            secondary_exists = bool(secondary_canvas.winfo_exists())
        except Exception:
            secondary_exists = False
    if not secondary_exists:
        self.voice_meter_canvas_secondary = tk.Canvas(card, height=14, bg=Theme.CARD_BG, highlightthickness=0)
    else:
        self.voice_meter_canvas_secondary.configure(bg=Theme.CARD_BG, highlightthickness=0, height=14)
    self.voice_meter_canvas_secondary.pack(fill="x", padx=16, pady=(8, 8))

    wake_label = tk.Label(card, textvariable=self.wake_debug_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 10))
    wake_label.pack(fill="x", padx=16)
    bind_dynamic_wrap(wake_label, card, padding=34, minimum=280)

    heard_wrap = tk.Frame(card, bg=Theme.BUTTON_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    heard_wrap.pack(fill="x", padx=16, pady=(10, 12))
    tk.Label(heard_wrap, text="Что услышал JARVIS", bg=Theme.BUTTON_BG, fg=Theme.FG, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
    heard_label = tk.Label(heard_wrap, textvariable=self.voice_last_heard_var, bg=Theme.BUTTON_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 10))
    heard_label.pack(fill="x", padx=12, pady=(0, 10))
    bind_dynamic_wrap(heard_label, heard_wrap, padding=28, minimum=260)

    _, buttons = create_action_grid(
        card,
        [
            {"text": "Тестовая запись", "command": self.run_voice_recording_test, "bg": Theme.ACCENT},
            {"text": "Что услышал JARVIS", "command": self.show_last_voice_capture_summary},
            {"text": "Прослушать запись", "command": self.play_last_voice_capture},
            {"text": "Автоподбор профиля", "command": self.run_voice_profile_autotune},
            {"text": "Проверка готовности", "command": self.run_readiness_master},
            {"text": "Открыть диагностику", "command": lambda: self._show_control_center_section("diagnostics")},
        ],
        columns=2,
        bg=Theme.CARD_BG,
    )
    for btn in buttons:
        btn.configure(highlightbackground=Theme.BORDER, highlightthickness=1, font=("Segoe UI", 10))

    profile_card = tk.Frame(body, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    profile_card.pack(fill="x", padx=18, pady=(0, 14))
    tk.Label(profile_card, text="Профили устройств", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=16, pady=(16, 6))
    tk.Label(
        profile_card,
        text="Отдельные профили для гарнитуры, USB-микрофона, встроенного микрофона и веб-камеры. В режиме «авто» JARVIS сам подхватит нужный профиль.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=("Segoe UI", 10),
    ).pack(fill="x", padx=16, pady=(0, 12))

    overrides = dict(self._cfg().get_device_profile_overrides() or {})
    self._voice_profile_override_vars = {
        "headset": tk.StringVar(value=str(overrides.get("headset", "boost") or "boost")),
        "usb_mic": tk.StringVar(value=str(overrides.get("usb_mic", "boost") or "boost")),
        "built_in": tk.StringVar(value=str(overrides.get("built_in", "normal") or "normal")),
        "webcam": tk.StringVar(value=str(overrides.get("webcam", "normal") or "normal")),
        "default": tk.StringVar(value=str(overrides.get("default", "normal") or "normal")),
    }

    for key, label_text in (
        ("headset", "Гарнитура"),
        ("usb_mic", "USB-микрофон"),
        ("built_in", "Встроенный микрофон"),
        ("webcam", "Веб-камера"),
        ("default", "Fallback-профиль"),
    ):
        row = tk.Frame(profile_card, bg=Theme.CARD_BG)
        row.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(row, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 4))
        shell, button = self._create_settings_choice_control(
            row,
            self._voice_profile_override_vars[key],
            ["normal", "boost", "aggressive"],
            font=("Segoe UI", 10),
        )
        shell.pack(fill="x")
        try:
            setattr(self, f"_voice_profile_selector_{key}", button)
        except Exception:
            pass

    def _save_profiles():
        payload = {key: var.get() for key, var in self._voice_profile_override_vars.items()}
        self._cfg().set_device_profile_overrides(payload)
        self._maybe_auto_switch_device_profile(self.get_selected_microphone_name())
        self.set_status_temp("Профили устройств сохранены", "ok")

    footer = tk.Frame(profile_card, bg=Theme.CARD_BG)
    footer.pack(fill="x", padx=16, pady=(6, 16))
    tk.Button(footer, text="Сохранить профили", command=_save_profiles, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8, cursor="hand2").pack(side="right")

    self._apply_voice_insight_widgets()

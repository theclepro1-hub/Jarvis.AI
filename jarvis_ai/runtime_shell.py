import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from .branding import app_version_badge
from .guide_noobs import GuideNoobPanel
from .runtime import parse_geometry
from .theme import Theme
from .ui_factory import bind_dynamic_wrap, create_action_grid


def _advance_guide_hint(self):
    panel = getattr(self, "guide_panel", None)
    if panel is None:
        return

    hints = [
        (
            "Нубик JARVIS",
            "Привет, я рядом",
            "Главный экран теперь держится на одном принципе: в центре только разговор, а не админ-панель.",
            "→ Напишите команду внизу или нажмите на микрофон справа.",
        ),
        (
            "Нубик JARVIS",
            "Подсказка по голосу",
            "Если реакция на голос кажется слабой, сначала смотрите на живой индикатор в углу. Он сразу показывает уровень и текущий порог.",
            "→ Потом уже открывайте «Центр голоса» для глубокой проверки.",
        ),
        (
            "Нубик JARVIS",
            "Факт дня",
            "Ложные срабатывания wake-word чаще всего приходят не от модели, а от слишком агрессивного порога и фонового шума в комнате.",
            "→ Для тихой комнаты лучше держать базовый или усиленный режим, а не максимальный.",
        ),
        (
            "Нубик JARVIS",
            "Про настройки",
            "Настройки оставлены вкладками, чтобы все глубокие вещи открывались по клику и не ломали главный экран.",
            "→ Если наведете на важные кнопки, я подскажу, что они делают.",
        ),
        (
            "Нубик JARVIS",
            "Про систему",
            "Релизные проверки, память, сценарии и журнал не должны жить рядом с чат-композером. Иначе внимание распадается.",
            "→ Для редких действий открывайте «Система», а тут держите спокойный центр.",
        ),
        (
            "Нубик JARVIS",
            "Еще факт",
            "На Windows слишком мелкий текст ломается раньше, чем кажется: Microsoft рекомендует не опускаться ниже 12 px regular и 14 px semibold.",
            "→ Поэтому я стараюсь держать иерархию спокойной и читаемой.",
        ),
    ]

    self._guide_hint_index = (int(getattr(self, "_guide_hint_index", -1)) + 1) % len(hints)
    title, status, text, pointer = hints[self._guide_hint_index]
    panel.set_message(title=title, status=status, text=text, pointer=pointer)


def _ensure_tray_icon_available(self):
    if getattr(self, "tray_icon", None) is not None:
        return
    icon_path = str(getattr(self, "_tray_icon_path", "") or "").strip()
    if icon_path:
        try:
            self.create_tray_icon(icon_path)
        except Exception:
            pass


def _hide_to_tray_force(self):
    try:
        geom = self._normal_geometry if self.is_full else self.root.geometry()
        if geom and parse_geometry(geom):
            self._cfg().set_window_geometry(geom)
    except Exception:
        pass
    _ensure_tray_icon_available(self)
    try:
        self.root.withdraw()
    except Exception:
        pass


def _patched_hide_to_tray(self):
    behavior = str(self._cfg().get_close_behavior() or "exit").strip().lower()
    if behavior == "tray":
        return _hide_to_tray_force(self)
    self.quit_app()


def _patched_toggle_window(self):
    try:
        state = str(self.root.state() or "")
    except Exception:
        state = ""
    if state in {"withdrawn", "iconic"}:
        self.show_window()
    else:
        _hide_to_tray_force(self)


def _patched_quit_app_main(self):
    if getattr(self, "_is_quitting", False):
        return
    self._is_quitting = True
    try:
        self.shutdown()
    except Exception:
        pass
    try:
        self.root.quit()
    except Exception:
        pass
    try:
        self.root.destroy()
    except Exception:
        pass


def _clear_background_layers(self):
    for attr_name in ("_bg_anim_after_id", "_bg_rebuild_after_id"):
        after_id = getattr(self, attr_name, None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            setattr(self, attr_name, None)
    for logo in list(getattr(self, "dvd_logos", [])):
        try:
            logo.destroy()
        except Exception:
            pass
    self.dvd_logos = []
    self._bg_anim_started = False


def _patched_shutdown(self):
    if getattr(self, "_shutdown_complete_v2", False):
        return
    self._shutdown_complete_v2 = True
    self._voice_meter_stop = True

    delayed_start = getattr(self, "_voice_meter_boot_after", None)
    if delayed_start:
        try:
            self.root.after_cancel(delayed_start)
        except Exception:
            pass
        self._voice_meter_boot_after = None

    try:
        if getattr(self, "guide_panel", None):
            self.guide_panel.stop()
    except Exception:
        pass
    try:
        corner_guide = getattr(self, "workspace_guide_panel", None)
        if corner_guide:
            corner_guide.stop()
    except Exception:
        pass
    try:
        self._close_command_palette()
    except Exception:
        pass

    _clear_background_layers(self)
    self._tray_icon_started = False
    return type(self)._base_shutdown_v2(self)


def _patched_start_bg_anim(self, append: bool = False):
    _clear_background_layers(self)


def _patched_restart_bg_anim(self, animated: bool = True, retire_mode: str = "edge"):
    _clear_background_layers(self)


def _schedule_voice_meter_boot(self, delay_ms: int = 700):
    pending = getattr(self, "_voice_meter_boot_after", None)
    if pending:
        try:
            self.root.after_cancel(pending)
        except Exception:
            pass
    self._voice_meter_boot_after = self.root.after(delay_ms, self._run_delayed_voice_meter_boot)


def _run_delayed_voice_meter_boot(self):
    self._voice_meter_boot_after = None
    if self.safe_mode or not getattr(self, "running", False):
        return
    try:
        self._start_audio_meter_monitor()
    except Exception:
        pass


def _patched_start_runtime_services(self):
    result = type(self)._base_start_runtime_services_v2(self)
    self._ensure_voice_debug_state()
    if not self.safe_mode:
        self._schedule_voice_meter_boot(950)
    return result


def _patched_reload_services(self):
    result = type(self)._base_reload_services_v2(self)
    self._ensure_voice_debug_state()
    self._maybe_auto_switch_device_profile(self.get_selected_microphone_name())
    if not self.safe_mode:
        self._schedule_voice_meter_boot(350)
    self._apply_voice_insight_widgets()
    return result


def _nav_button(parent, text, command, accent: bool = False):
    return tk.Button(
        parent,
        text=text,
        command=command,
        anchor="w",
        bg=Theme.ACCENT if accent else Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=16,
        pady=11,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        cursor="hand2",
        font=("Segoe UI Semibold", 10),
    )


def _toolbar_button(parent, text, command, accent: bool = False):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=Theme.ACCENT if accent else Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=12,
        pady=8,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        cursor="hand2",
        font=("Segoe UI Semibold", 9),
    )


def _status_chip(parent, title, *, text="", textvariable=None, fg=None, min_width: int = 150):
    card = tk.Frame(
        parent,
        bg=Theme.BUTTON_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        padx=12,
        pady=10,
    )
    card.pack(side="left", fill="both", expand=True, padx=(0, 8))
    card.pack_propagate(False)
    card.configure(width=min_width)
    tk.Label(
        card,
        text=title,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG_SECONDARY,
        font=("Segoe UI", 8, "bold"),
        justify="left",
    ).pack(anchor="w")
    value = tk.Label(
        card,
        text=text,
        textvariable=textvariable,
        bg=Theme.BUTTON_BG,
        fg=fg or Theme.FG,
        font=("Segoe UI", 10),
        justify="left",
    )
    value.pack(anchor="w", fill="x", pady=(6, 0))
    bind_dynamic_wrap(value, card, padding=26, minimum=120)
    return card, value


def _build_corner_meter(self, parent=None):
    host = parent or getattr(self, "chat_shell", None)
    if host is None:
        return
    card = tk.Frame(
        host,
        bg=Theme.CARD_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    if parent is None:
        card.place(relx=1.0, x=-18, y=18, anchor="ne")
    else:
        card.pack(fill="x")
    self.corner_voice_card = card
    self.voice_insight_card = card
    tk.Label(card, text="Слышимость", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 10)).pack(
        anchor="w", padx=12, pady=(10, 2)
    )
    self.corner_voice_meter_var = tk.StringVar(value="Микрофон 0%")
    tk.Label(
        card,
        textvariable=self.corner_voice_meter_var,
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        font=("Segoe UI", 9),
    ).pack(anchor="w", padx=12)
    self.corner_voice_meter_canvas = tk.Canvas(card, height=12, bg=Theme.CARD_BG, highlightthickness=0)
    self.corner_voice_meter_canvas.pack(fill="x", padx=12, pady=(8, 6))
    self.corner_voice_stats_var = tk.StringVar(value="RMS 0  •  порог 80")
    tk.Label(
        card,
        textvariable=self.corner_voice_stats_var,
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        font=("Segoe UI", 8),
    ).pack(anchor="w", padx=12, pady=(0, 10))


def _set_workspace_section(self, section: str = "chat"):
    normalized = str(section or "chat").strip().lower()
    self._workspace_section = normalized
    mapping = {
        "chat": ("Диалог", "Главный рабочий режим: слева навигация, в центре разговор, справа живые подсказки и голос."),
        "main": ("Настройки", "Крупные настройки теперь живут внутри приложения как вкладки, без конфликтующего отдельного окна."),
        "voice": ("Центр голоса", "Здесь настраиваются микрофон, слышимость, wake-word и связанные голосовые сценарии."),
        "audio": ("Центр голоса", "Здесь настраиваются микрофон, слышимость, wake-word и связанные голосовые сценарии."),
        "apps": ("Приложения и сценарии", "Быстрые действия, подключаемые инструменты и пользовательские маршруты собраны в одном месте."),
        "diagnostics": ("Диагностика", "Предрелизные проверки, внутренняя диагностика и живые отчеты без лишнего шума на главном экране."),
        "updates": ("Релиз и обновления", "Здесь лежат каналы обновлений, публикация и релизные инструменты."),
        "release": ("Релиз и обновления", "Здесь лежат каналы обновлений, публикация и релизные инструменты."),
        "system": ("Система", "Редкие системные операции, бэкапы и обслуживание вынесены подальше от повседневного диалога."),
    }
    title, desc = mapping.get(normalized, mapping["chat"])
    try:
        self.quick_title_label.configure(text=title)
    except Exception:
        pass
    try:
        self.quick_desc_label.configure(text=desc)
    except Exception:
        pass
    buttons = getattr(self, "sidebar_section_buttons", {})
    for key, btn in buttons.items():
        try:
            active = key == normalized or (normalized in {"audio", "voice"} and key == "voice")
            btn.configure(bg=Theme.ACCENT if active else Theme.BUTTON_BG)
        except Exception:
            pass


def _patched_build_workspace_sidebar(self, metrics):
    for child in list(self.sidebar.winfo_children()):
        try:
            child.destroy()
        except Exception:
            pass

    self.sidebar_action_buttons = []
    self.sidebar_section_buttons = {}

    top = tk.Frame(self.sidebar, bg=Theme.CARD_BG)
    top.pack(fill="x", padx=18, pady=(18, 14))
    tk.Label(
        top,
        text="JARVIS AI 2.0",
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        font=("Bahnschrift SemiBold", 21),
    ).pack(anchor="w")
    tk.Label(
        top,
        text=f"{app_version_badge()}  •  workspace 16.1.1",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        font=metrics["small_font"],
    ).pack(anchor="w", pady=(6, 0))

    nav = tk.Frame(
        self.sidebar,
        bg=Theme.CARD_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    nav.pack(fill="x", padx=12, pady=(0, 10))
    tk.Label(nav, text="Вкладки", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 11)).pack(
        anchor="w", padx=14, pady=(14, 8)
    )

    items = [
        ("Чат", "chat", lambda: (self.close_full_settings_view(), self.clear_chat()), False),
        ("Центр голоса", "voice", lambda: self.open_full_settings_view("voice"), False),
        ("Настройки", "main", lambda: self.open_full_settings_view("main"), False),
        ("Приложения и игры", "apps", lambda: self.open_full_settings_view("apps"), False),
        ("Диагностика", "diagnostics", lambda: self.open_full_settings_view("diagnostics"), False),
        ("Релиз", "updates", lambda: self.open_full_settings_view("updates"), False),
        ("Система", "system", lambda: self.open_full_settings_view("system"), False),
    ]
    for text, section, command, accent in items:
        btn = _nav_button(nav, text, lambda s=section, c=command: (self._update_guide_context(s), c()), accent=accent)
        btn.pack(fill="x", padx=14, pady=(0, 8))
        self._bind_hover_bg(btn, role="button")
        self.sidebar_action_buttons.append(btn)
        self.sidebar_section_buttons[section] = btn

    note = tk.Label(
        self.sidebar,
        text="Одна вкладка = один режим. Без всплывающих панелей поверх чата и без конкурирующих окон.",
        bg=Theme.BUTTON_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=metrics["small_font"],
        padx=12,
        pady=10,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    note.pack(fill="x", padx=12, pady=(0, 10))
    bind_dynamic_wrap(note, self.sidebar, padding=36, minimum=160)

    guide_host = tk.Frame(self.sidebar, bg=Theme.CARD_BG)
    guide_host.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    noob_asset = self.assets.get("noob")
    noob_image = noob_asset if isinstance(noob_asset, ImageTk.PhotoImage) else None
    self.guide_panel = GuideNoobPanel(
        guide_host,
        image=noob_image,
        title="Нубик JARVIS",
        on_click=self._advance_guide_hint,
        variant="default",
    )
    self._update_guide_context("chat")
    self._set_workspace_section("chat")


def _patched_build_workspace_overview(self, metrics):
    self._ensure_voice_debug_state()
    for container in (getattr(self, "top_bar", None), getattr(self, "quick_head", None), getattr(self, "quick_bar", None)):
        if container is None:
            continue
        for child in list(container.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

    header = tk.Frame(self.top_bar, bg=Theme.CARD_BG)
    header.pack(fill="x")

    left = tk.Frame(header, bg=Theme.CARD_BG)
    left.pack(side="left", fill="x", expand=True)
    tk.Label(
        left,
        text="JARVIS AI 2.0",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        font=("Segoe UI", 9, "bold"),
    ).pack(anchor="w")
    self.quick_title_label = tk.Label(
        left,
        text="Диалог",
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        font=("Bahnschrift SemiBold", 25),
        justify="left",
    )
    self.quick_title_label.pack(anchor="w", pady=(8, 0))
    self.quick_desc_label = tk.Label(
        left,
        text="Главный рабочий режим: слева навигация, в центре разговор, справа живые подсказки и голос.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        font=metrics["body_font"],
    )
    self.quick_desc_label.pack(anchor="w", pady=(8, 0))
    bind_dynamic_wrap(self.quick_desc_label, left, padding=26, minimum=260)
    self.status_label = tk.Label(
        left,
        textvariable=self.status_var,
        bg=Theme.CARD_BG,
        fg=Theme.STATUS_OK,
        font=("Segoe UI", 9, "bold"),
    )
    self.status_label.pack(anchor="w", pady=(10, 0))

    right = tk.Frame(header, bg=Theme.CARD_BG)
    right.pack(side="right", padx=(18, 0))
    self.header_action_buttons = []
    for text, command, accent in (
        ("Новый чат", lambda: (self.close_full_settings_view(), self.clear_chat()), False),
        ("Журнал", self.show_history, False),
        ("Ctrl+K", self.open_command_palette, False),
        ("Настройки", lambda: self.open_full_settings_view("main"), True),
    ):
        btn = _toolbar_button(right, text, command, accent=accent)
        btn.pack(side="right", padx=(0, 8))
        self._bind_hover_bg(btn, role="button")
        self.header_action_buttons.append(btn)

    summary = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)
    summary.pack(fill="x")
    row = tk.Frame(summary, bg=Theme.CARD_BG)
    row.pack(fill="x")

    self.net_chip, self.net_label = _status_chip(row, "Сеть", text="Онлайн", fg=Theme.ONLINE, min_width=132)
    self.mic_status_var = tk.StringVar(value="Микрофон: не выбран")
    self.mic_chip, self.mic_status_label = _status_chip(row, "Микрофон", textvariable=self.mic_status_var, min_width=184)
    self.output_status_var = tk.StringVar(value="Вывод: не выбран")
    self.output_chip, self.output_status_label = _status_chip(row, "Вывод", textvariable=self.output_status_var, min_width=184)
    self.tts_status_var = tk.StringVar(value="Голос: pyttsx3")
    self.tts_chip, self.tts_status_label = _status_chip(row, "Озвучка", textvariable=self.tts_status_var, min_width=172)
    try:
        self.tts_chip.pack_configure(padx=(0, 0))
    except Exception:
        pass

    self.workspace_mode_badge = None
    self.top_divider = tk.Frame(self.workspace, bg=Theme.BORDER, height=1)
    self.top_divider.pack(fill="x", pady=(0, 8))


def _patched_build_workspace_chat(self, metrics):
    if hasattr(self, "_ensure_activity_state"):
        self._ensure_activity_state()

    stage = tk.Frame(self.content_stage, bg=Theme.BG_LIGHT)
    stage.pack(fill="both", expand=True)
    stage.grid_columnconfigure(0, weight=1)
    stage.grid_rowconfigure(0, weight=1)
    stage.grid_rowconfigure(1, weight=0)
    self.chat_stage = stage

    self.chat_shell = tk.Frame(
        stage,
        bg=Theme.CARD_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    self.chat_shell.grid(row=0, column=0, sticky="nsew")

    self.chat_header = tk.Frame(self.chat_shell, bg=Theme.CARD_BG)
    self.chat_header.pack(fill="x", padx=20, pady=(18, 0))
    left = tk.Frame(self.chat_header, bg=Theme.CARD_BG)
    left.pack(side="left", fill="x", expand=True)
    tk.Label(left, text="Новая беседа", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 16)).pack(anchor="w")
    self.chat_hint_label = tk.Label(
        left,
        text="Пишите как человеку: вопрос, просьбу, команду или свободную мысль. Главный экран должен помогать разговору, а не кричать поверх него.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        font=metrics["body_font"],
        justify="left",
    )
    self.chat_hint_label.pack(anchor="w", pady=(4, 0))
    bind_dynamic_wrap(self.chat_hint_label, left, padding=24, minimum=260)
    self.action_explainer_var = tk.StringVar(value="JARVIS коротко покажет, что понял, перед сложным действием.")
    self.action_explainer_label = tk.Label(
        left,
        textvariable=self.action_explainer_var,
        bg=Theme.CARD_BG,
        fg=Theme.ACCENT,
        font=("Segoe UI", 9, "bold"),
        justify="left",
    )
    self.action_explainer_label.pack(anchor="w", pady=(8, 0))
    bind_dynamic_wrap(self.action_explainer_label, left, padding=24, minimum=260)

    self.chat_canvas = tk.Canvas(self.chat_shell, bg=Theme.BG_LIGHT, highlightthickness=0)
    self.chat_scroll = ttk.Scrollbar(
        self.chat_shell,
        orient="vertical",
        command=self.chat_canvas.yview,
        style="Jarvis.Vertical.TScrollbar",
    )
    self.chat_scroll.pack(side="right", fill="y", padx=(0, 6), pady=8)
    self.chat_canvas.configure(yscrollcommand=self.chat_scroll.set)
    self.chat_canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
    self.chat_frame = tk.Frame(self.chat_canvas, bg=Theme.BG_LIGHT)
    self.chat_window_id = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw", width=920)
    self.chat_frame.bind("<Configure>", lambda _e: self._sync_chat_scroll_region())
    self.chat_canvas.bind("<Configure>", lambda e: self._sync_chat_canvas_width(e.width))
    self._register_scroll_target(self.chat_canvas)

    self.chat_side = tk.Frame(stage, bg=Theme.BG_LIGHT, width=318)
    self.chat_side.grid(row=0, column=1, sticky="ns", padx=(14, 0))
    self.chat_side.grid_propagate(False)

    voice_host = tk.Frame(self.chat_side, bg=Theme.BG_LIGHT)
    voice_host.pack(fill="x")
    _build_corner_meter(self, parent=voice_host)

    noob_host = tk.Frame(self.chat_side, bg=Theme.BG_LIGHT)
    noob_host.pack(fill="both", expand=True, pady=(12, 0))
    noob_asset = self.assets.get("noob")
    noob_image = noob_asset if isinstance(noob_asset, ImageTk.PhotoImage) else None
    self.chat_noob_panel = GuideNoobPanel(
        noob_host,
        image=noob_image,
        title="Нубик JARVIS",
        on_click=self._advance_guide_hint,
        variant="default",
    )
    self.utility_shell = self.chat_side


def _patched_build_workspace_controls(self, metrics):
    self.controls_bar = tk.Frame(self.workspace, bg=Theme.BG_LIGHT, height=max(metrics["entry_height"], 88))
    self.controls_bar.pack(side="bottom", fill="x", pady=(12, 0))
    self.controls_bar.pack_propagate(False)

    left_tools = tk.Frame(self.controls_bar, bg=Theme.BG_LIGHT)
    left_tools.pack(side="left", padx=(0, 8))
    palette_btn = _toolbar_button(left_tools, "Ctrl+K", self.open_command_palette)
    palette_btn.pack(side="left")
    self._bind_hover_bg(palette_btn, role="button")

    self.entry_wrap = tk.Frame(
        self.controls_bar,
        bg=Theme.CARD_BG,
        padx=12,
        pady=8,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    self.entry_wrap.pack(side="left", fill="both", expand=True)
    self.entry = tk.Entry(
        self.entry_wrap,
        bg=Theme.INPUT_BG,
        fg=Theme.FG,
        font=("Segoe UI", 13),
        bd=0,
        insertbackground=Theme.FG,
        exportselection=0,
        relief="flat",
    )
    self.entry.pack(side="left", fill="both", expand=True, ipady=8)
    self._setup_entry_bindings(self.entry)
    self.entry.bind("<Return>", lambda e: self.send_text())

    self.paste_btn = tk.Label(self.entry_wrap, text="📎", bg=Theme.BUTTON_BG, fg=Theme.FG, font=("Segoe UI", 10), cursor="hand2", padx=9, pady=6)
    self.paste_btn.pack(side="right", padx=(6, 0))
    self.paste_btn.bind("<Button-1>", lambda e: self.paste_text())
    self._bind_hover_bg(self.paste_btn, role="input_icon")

    self.copy_btn = tk.Label(self.entry_wrap, text="📋", bg=Theme.BUTTON_BG, fg=Theme.FG, font=("Segoe UI", 10), cursor="hand2", padx=9, pady=6)
    self.copy_btn.pack(side="right", padx=(6, 0))
    self.copy_btn.bind("<Button-1>", lambda e: self.copy_chat())
    self._bind_hover_bg(self.copy_btn, role="input_icon")

    self.send_btn = tk.Label(self.entry_wrap, bg=Theme.BUTTON_BG, cursor="hand2", padx=10, pady=6)
    self.send_btn.pack(side="right", padx=(6, 0))
    if "send" in self.assets:
        if isinstance(self.assets["send"], ImageTk.PhotoImage):
            self.send_btn.config(image=self.assets["send"])
        else:
            self.send_btn.config(text=self.assets["send"], fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
    else:
        self.send_btn.config(text="➤", fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
    self.send_btn.bind("<Button-1>", lambda e: self.send_text())
    self._bind_hover_bg(self.send_btn, role="input_icon")

    self.mic_btn = tk.Label(
        self.controls_bar,
        bg=Theme.ACCENT,
        fg=Theme.FG,
        cursor="hand2",
        padx=15,
        pady=11,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    self.mic_btn.pack(side="right", padx=(8, 0))
    if "mic" in self.assets:
        if isinstance(self.assets["mic"], ImageTk.PhotoImage):
            self.mic_btn.config(image=self.assets["mic"])
        else:
            self.mic_btn.config(text=self.assets["mic"], fg=Theme.FG, font=("Segoe UI", 16))
    else:
        self.mic_btn.config(text="🎤", fg=Theme.FG, font=("Segoe UI", 16))
    self.mic_btn.bind("<Button-1>", self.mic_click)
    self._bind_hover_bg(self.mic_btn, role="button")


def _patched_refresh_chat_empty_state(self):
    if not getattr(self, "chat_frame", None):
        return
    has_history = bool(getattr(self, "chat_history", []))
    placeholder = getattr(self, "_chat_empty_state", None)
    if has_history:
        if placeholder and placeholder.winfo_exists():
            placeholder.destroy()
        self._chat_empty_state = None
        return
    if placeholder and placeholder.winfo_exists():
        return

    empty = tk.Frame(self.chat_frame, bg=Theme.BG_LIGHT)
    empty.pack(fill="both", expand=True, padx=24, pady=(54, 24))
    self._chat_empty_state = empty

    card = tk.Frame(empty, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    card.pack(fill="x")
    tk.Label(
        card,
        text="Начнем спокойно",
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        font=("Bahnschrift SemiBold", 24),
    ).pack(anchor="center", padx=20, pady=(26, 8))
    hint = tk.Label(
        card,
        text="Задайте вопрос, попросите открыть программу, продиктуйте команду голосом или быстро прыгните в нужный раздел. Главный экран теперь не должен отвлекать вас служебщиной.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        justify="center",
        font=("Segoe UI", 11),
    )
    hint.pack(fill="x", padx=28, pady=(0, 16))
    bind_dynamic_wrap(hint, card, padding=56, minimum=260)
    _, buttons = create_action_grid(
        card,
        [
            {"text": "Центр голоса", "command": lambda: self.open_full_settings_view("voice"), "bg": Theme.ACCENT},
            {"text": "Настройки", "command": lambda: self.open_full_settings_view("main")},
            {"text": "Приложения и игры", "command": lambda: self.open_full_settings_view("apps")},
            {"text": "Система", "command": lambda: self.open_full_settings_view("system")},
        ],
        columns=2,
        bg=Theme.CARD_BG,
    )
    for btn in buttons:
        btn.configure(highlightbackground=Theme.BORDER, highlightthickness=1, font=("Segoe UI Semibold", 10), padx=12, pady=10)
        self._bind_hover_bg(btn, role="button")


def _patched_build_workspace_rail(self, _metrics):
    self.rail_action_buttons = []
    self.side_status_labels = []
    self.side_tip_label = None
    try:
        self.side_panel.grid_remove()
    except Exception:
        pass


def _patched_refresh_workspace_layout_mode(self, *_args):
    if not hasattr(self, "shell"):
        return
    try:
        width = int(self.main_container.winfo_width() or self.root.winfo_width() or 0)
    except Exception:
        width = 0
    focus = bool(self._cfg().get_focus_mode_enabled())
    sidebar_visible = (not focus) and width >= 1060
    self._set_focus_layout_visible(sidebar_visible, False)

    utility_shell = getattr(self, "utility_shell", None)
    if utility_shell is not None and utility_shell is not getattr(self, "chat_side", None):
        try:
            utility_shell.grid_remove()
        except Exception:
            pass

    chat_stage = getattr(self, "chat_stage", None)
    chat_side = getattr(self, "chat_side", None)
    settings_open = False
    if hasattr(self, "_is_full_settings_open"):
        try:
            settings_open = bool(self._is_full_settings_open())
        except Exception:
            settings_open = False
    if chat_stage is not None and chat_side is not None and not settings_open:
        try:
            if focus:
                chat_side.grid_remove()
            elif width >= 1380:
                chat_side.grid()
                chat_side.grid(row=0, column=1, sticky="ns", padx=(14, 0), pady=0)
                chat_side.grid_propagate(False)
                chat_side.configure(width=318)
            elif width >= 1120:
                chat_side.grid()
                chat_side.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(12, 0))
                chat_side.grid_propagate(True)
                chat_side.configure(width=1)
            else:
                chat_side.grid_remove()
        except Exception:
            pass

    current_section = getattr(self, "_workspace_section", "chat")
    self._set_workspace_section("chat" if focus and current_section == "chat" else current_section)
    self._update_guide_context("focus" if focus else "chat")


def register_shell_runtime(app_cls):
    if not hasattr(app_cls, "_base_shutdown_v2"):
        app_cls._base_shutdown_v2 = app_cls.shutdown
    if not hasattr(app_cls, "_base_start_runtime_services_v2"):
        app_cls._base_start_runtime_services_v2 = app_cls._start_runtime_services
    if not hasattr(app_cls, "_base_reload_services_v2"):
        app_cls._base_reload_services_v2 = app_cls.reload_services

    app_cls._advance_guide_hint = _advance_guide_hint
    app_cls._hide_to_tray_force = _hide_to_tray_force
    app_cls.hide_to_tray = _patched_hide_to_tray
    app_cls.toggle_window = _patched_toggle_window
    app_cls._quit_app_main = _patched_quit_app_main
    app_cls.shutdown = _patched_shutdown
    app_cls.start_bg_anim = _patched_start_bg_anim
    app_cls.restart_bg_anim = _patched_restart_bg_anim
    app_cls._schedule_voice_meter_boot = _schedule_voice_meter_boot
    app_cls._run_delayed_voice_meter_boot = _run_delayed_voice_meter_boot
    app_cls._start_runtime_services = _patched_start_runtime_services
    app_cls.reload_services = _patched_reload_services
    app_cls._set_workspace_section = _set_workspace_section
    app_cls._build_workspace_sidebar = _patched_build_workspace_sidebar
    app_cls._build_workspace_overview = _patched_build_workspace_overview
    app_cls._build_workspace_chat = _patched_build_workspace_chat
    app_cls._build_workspace_controls = _patched_build_workspace_controls
    app_cls._refresh_chat_empty_state = _patched_refresh_chat_empty_state
    app_cls._build_workspace_rail = _patched_build_workspace_rail
    app_cls.refresh_workspace_layout_mode = _patched_refresh_workspace_layout_mode


__all__ = ["register_shell_runtime"]

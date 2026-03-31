import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from .branding import app_version_badge
from .guide_noobs import GuideNoobPanel
from .runtime import parse_geometry
from .theme import Theme
from .ui_actions import build_workspace_menu_actions, build_workspace_section_actions
from .ui_factory import bind_dynamic_wrap, create_action_grid


def _advance_guide_hint(self):
    panel = getattr(self, "guide_panel", None)
    if panel is None:
        return

    hints = [
        (
            "Нубик JARVIS",
            "Привет, я рядом",
            "Главный экран держится на одном правиле: в центре только разговор.",
            "→ Напишите команду снизу или нажмите микрофон справа.",
        ),
        (
            "Нубик JARVIS",
            "Подсказка по голосу",
            "Если голос срабатывает слабо, сначала смотрите на живой индикатор в углу.",
            "→ Потом уже открывайте «Центр голоса».",
        ),
        (
            "Нубик JARVIS",
            "Факт дня",
            "Ложные срабатывания чаще приходят от шума и слишком агрессивного порога.",
            "→ Для тихой комнаты обычно хватает усиленного режима.",
        ),
        (
            "Нубик JARVIS",
            "Про настройки",
            "Настройки открываются отдельным центром, чтобы не ломать чат.",
            "→ Наведите на важные кнопки, и я подскажу их смысл.",
        ),
        (
            "Нубик JARVIS",
            "Про систему",
            "Редкие системные действия лучше держать вне чата, чтобы не терять фокус.",
            "→ Для них открывайте раздел «Система».",
        ),
        (
            "Нубик JARVIS",
            "Еще факт",
            "На Windows слишком мелкий текст ломается быстрее, чем кажется.",
            "→ Поэтому интерфейс лучше держать спокойным и читаемым.",
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


def _nav_button(parent, text, command, accent: bool = False, *, font=None, padx: int = 16, pady: int = 11):
    return tk.Button(
        parent,
        text=text,
        command=command,
        anchor="w",
        bg=Theme.ACCENT if accent else Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=padx,
        pady=pady,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        cursor="hand2",
        font=font or ("Segoe UI Semibold", 10),
    )


def _toolbar_button(parent, text, command, accent: bool = False, *, font=None, padx: int = 12, pady: int = 8):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=Theme.ACCENT if accent else Theme.BUTTON_BG,
        fg=Theme.FG,
        relief="flat",
        padx=padx,
        pady=pady,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        cursor="hand2",
        font=font or ("Segoe UI Semibold", 9),
    )


def _open_workspace_menu(self):
    menu = tk.Menu(
        self.root,
        tearoff=0,
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        activebackground=Theme.ACCENT,
        activeforeground=Theme.FG,
        bd=0,
        relief="flat",
    )
    items = build_workspace_menu_actions(self)
    for item in items:
        if item is None:
            menu.add_separator()
            continue
        text, command = item
        menu.add_command(label=text, command=command)
    try:
        if getattr(self, "menu_btn", None) is not None and self.menu_btn.winfo_exists():
            x = self.menu_btn.winfo_rootx()
            y = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height() + 4
        else:
            x = self.root.winfo_rootx() + 24
            y = self.root.winfo_rooty() + 64
        menu.tk_popup(x, y)
    finally:
        try:
            menu.grab_release()
        except Exception:
            pass


def _status_chip(
    parent,
    title,
    *,
    text="",
    textvariable=None,
    fg=None,
    min_width: int = 150,
    title_font=None,
    value_font=None,
    padx: int = 12,
    pady: int = 10,
):
    card = tk.Frame(
        parent,
        bg=Theme.BUTTON_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        padx=padx,
        pady=pady,
    )
    card.pack(side="left", fill="both", expand=True, padx=(0, 8))
    card.pack_propagate(False)
    card.configure(width=min_width)
    tk.Label(
        card,
        text=title,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG_SECONDARY,
        font=title_font or ("Segoe UI", 8, "bold"),
        justify="left",
    ).pack(anchor="w")
    value = tk.Label(
        card,
        text=text,
        textvariable=textvariable,
        bg=Theme.BUTTON_BG,
        fg=fg or Theme.FG,
        font=value_font or ("Segoe UI", 10),
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
        "chat": ("Диалог", "Главный рабочий режим: слева разделы, в центре разговор и снизу быстрый ввод без лишней служебной панели."),
        "main": ("Настройки", "Все глубокие настройки открываются отдельно от чата и не ломают главный экран."),
        "voice": ("Центр голоса", "Здесь настраиваются микрофон, слышимость, слово активации и связанные голосовые сценарии."),
        "audio": ("Центр голоса", "Здесь настраиваются микрофон, слышимость, слово активации и связанные голосовые сценарии."),
        "diagnostics": ("Диагностика", "Предрелизные проверки, внутренняя диагностика и живые отчеты без лишнего шума на главном экране."),
        "system": ("Система", "Редкие системные операции, память, сценарии, приложения и релизные инструменты собраны отдельно от разговора."),
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
    compact_buttons = getattr(self, "compact_section_buttons", {})
    for key, btn in compact_buttons.items():
        try:
            active = key == normalized or (normalized in {"audio", "voice"} and key == "voice")
            btn.configure(bg=Theme.ACCENT if active else Theme.BUTTON_BG)
        except Exception:
            pass


def _patched_build_workspace_shell_v2(self, metrics=None):
    metrics = metrics or self._workspace_metrics()

    self.shell = tk.Frame(self.main_container, bg=Theme.BG_LIGHT)
    self.shell.pack(fill="both", expand=True, padx=metrics["shell_pad"], pady=metrics["shell_pad"])
    self.shell.grid_columnconfigure(0, weight=0)
    self.shell.grid_columnconfigure(1, weight=1)
    self.shell.grid_rowconfigure(0, weight=1)

    self.sidebar = tk.Frame(
        self.shell,
        bg=Theme.CARD_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        width=metrics["sidebar_width"],
    )
    self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    self.sidebar.grid_propagate(False)

    self.workspace = tk.Frame(self.shell, bg=Theme.BG_LIGHT)
    self.workspace.grid(row=0, column=1, sticky="nsew")

    self.side_panel = tk.Frame(self.shell, bg=Theme.BG_LIGHT, width=1)
    self.side_panel.grid(row=0, column=2, sticky="nsew")
    self.side_panel.grid_propagate(False)
    self.side_panel.grid_remove()

    self.top_bar = tk.Frame(
        self.workspace,
        bg=Theme.CARD_BG,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        padx=metrics["card_pad"],
        pady=metrics["card_pad"],
    )
    self.top_bar.pack(side="top", fill="x")

    self.quick_bar = tk.Frame(self.workspace, bg=Theme.CARD_BG)
    self.quick_head = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)

    self.content_stage = tk.Frame(self.workspace, bg=Theme.BG_LIGHT)
    self.content_stage.pack(side="top", fill="both", expand=True, pady=(10, 0))

    self._build_workspace_sidebar(metrics)
    self._build_workspace_overview(metrics)
    self._build_workspace_chat(metrics)
    self._build_workspace_controls(metrics)
    self._build_workspace_rail(metrics)
    self._refresh_chat_empty_state()
    try:
        self.refresh_workspace_layout_mode()
    except Exception:
        pass


def _patched_rebuild_workspace_shell_v2(self):
    if not hasattr(self, "main_container"):
        return

    metrics = self._workspace_metrics()
    previous_entry = ""
    try:
        if getattr(self, "entry", None) is not None and self.entry.winfo_exists():
            previous_entry = str(self.entry.get() or "")
    except Exception:
        previous_entry = ""
    current_section = str(getattr(self, "_workspace_section", "chat") or "chat")

    old_shell = getattr(self, "shell", None)
    if old_shell is not None:
        try:
            old_shell.destroy()
        except Exception:
            pass

    self._workspace_layout_signature = None
    self._workspace_shell_layout_mode = None
    self._scroll_targets = []
    self._active_scroll_target = None
    self._wheel_delta_accum = {}

    self._build_workspace_shell_v2(metrics)
    try:
        self._set_workspace_section(current_section)
    except Exception:
        pass
    try:
        self._refresh_chat_theme()
    except Exception:
        pass
    try:
        if previous_entry:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, previous_entry)
            self.entry.configure(fg=Theme.FG)
        else:
            self._show_entry_placeholder()
    except Exception:
        pass
    try:
        self.refresh_workspace_layout_mode()
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
        text=f"{app_version_badge()}  •  рабочее пространство",
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
    tk.Label(nav, text="Разделы", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 11)).pack(
        anchor="w", padx=14, pady=(14, 8)
    )

    for item in build_workspace_section_actions(self):
        section = str(item["key"])
        command = item["command"]
        btn = _nav_button(
            nav,
            str(item["label"]),
            lambda s=section, c=command: (self._update_guide_context(s), c()),
            accent=False,
        )
        btn.pack(fill="x", padx=14, pady=(0, 8))
        self._bind_hover_bg(btn, role="button")
        self.sidebar_action_buttons.append(btn)
        self.sidebar_section_buttons[section] = btn

    note = tk.Label(
        self.sidebar,
        text="Главный экран держится вокруг разговора. Когда окно становится узким, боковая колонка исчезает и остается только чат.",
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
    guide_host.pack(fill="x", expand=False, padx=12, pady=(0, 12))
    noob_asset = self.assets.get("noob_sidebar") or self.assets.get("noob")
    noob_image = noob_asset if isinstance(noob_asset, ImageTk.PhotoImage) else None
    self.guide_panel = GuideNoobPanel(
        guide_host,
        image=noob_image,
        title="Нубик JARVIS",
        on_click=self._advance_guide_hint,
        variant="sidebar",
    )
    self._update_guide_context("chat")
    self._set_workspace_section("chat")


def _patched_build_workspace_overview(self, metrics):
    self._ensure_voice_debug_state()
    for container in (getattr(self, "top_bar", None),):
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
        text="Главный экран показывает только разговор: короткий статус сверху, широкий чат в центре и крупный ввод снизу.",
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

    self.compact_controls_row = tk.Frame(left, bg=Theme.CARD_BG)
    self.compact_controls_row.pack(anchor="w", pady=(10, 0))
    self.compact_nav_bar = tk.Frame(self.compact_controls_row, bg=Theme.CARD_BG)
    self.compact_nav_bar.pack(side="left")
    self.compact_section_buttons = {}
    for item in build_workspace_section_actions(self):
        key = str(item["key"])
        btn = _toolbar_button(
            self.compact_nav_bar,
            str(item["compact"]),
            item["command"],
            accent=False,
        )
        btn.pack(side="left", padx=(0, 6))
        self._bind_hover_bg(btn, role="button")
        self.compact_section_buttons[key] = btn

    self.menu_btn = _toolbar_button(self.compact_controls_row, "Меню", self._open_workspace_menu, accent=False)
    self.menu_btn.pack(side="left")
    self._bind_hover_bg(self.menu_btn, role="button")
    self.compact_controls_row.pack_forget()

    right = tk.Frame(header, bg=Theme.CARD_BG)
    right.pack(side="right", padx=(18, 0))
    self.header_action_buttons = []
    self.header_meter_host = tk.Frame(right, bg=Theme.CARD_BG)
    self.header_meter_host.pack(side="right")
    _build_corner_meter(self, parent=self.header_meter_host)

    for child in list(self.quick_bar.winfo_children()):
        try:
            child.destroy()
        except Exception:
            pass
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
    self._preferred_scroll_target = self.chat_canvas
    self.chat_side = None
    self.chat_noob_panel = None
    self.utility_shell = None


def _patched_build_workspace_controls(self, metrics):
    self.controls_bar = tk.Frame(self.workspace, bg=Theme.BG_LIGHT, height=max(metrics["entry_height"], 88))
    self.controls_bar.pack(side="bottom", fill="x", pady=(12, 0))
    self.controls_bar.pack_propagate(False)

    self.entry_wrap = tk.Frame(
        self.controls_bar,
        bg=Theme.CARD_BG,
        padx=12,
        pady=8,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
    )
    self.entry_wrap.pack(side="left", fill="both", expand=True, padx=(0, 8))
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
    self.entry.bind("<FocusIn>", lambda _e: self._clear_entry_placeholder(), add="+")
    self.entry.bind(
        "<FocusOut>",
        lambda _e: self._show_entry_placeholder() if not str(self.entry.get() or "").strip() else None,
        add="+",
    )

    def _entry_keypress(event):
        if bool(getattr(self, "_entry_placeholder_active", False)):
            ignored = {
                "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                "Caps_Lock", "Tab", "Escape", "Left", "Right", "Up", "Down",
                "Home", "End", "Prior", "Next",
            }
            if str(getattr(event, "keysym", "") or "") not in ignored:
                self._clear_entry_placeholder()
        return None

    self.entry.bind("<KeyPress>", _entry_keypress, add="+")
    self.entry.bind("<Button-1>", lambda _e: self._clear_entry_placeholder(), add="+")

    self.paste_btn = tk.Button(
        self.entry_wrap,
        text="📎",
        command=self.paste_text,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=9,
        pady=6,
        relief="flat",
        bd=0,
        highlightthickness=0,
        takefocus=False,
    )
    self.paste_btn.pack(side="right", padx=(6, 0))
    self._bind_hover_bg(self.paste_btn, role="input_icon")

    self.copy_btn = tk.Button(
        self.entry_wrap,
        text="📋",
        command=self.copy_chat,
        bg=Theme.BUTTON_BG,
        fg=Theme.FG,
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=9,
        pady=6,
        relief="flat",
        bd=0,
        highlightthickness=0,
        takefocus=False,
    )
    self.copy_btn.pack(side="right", padx=(6, 0))
    self._bind_hover_bg(self.copy_btn, role="input_icon")

    self.send_btn = tk.Button(
        self.entry_wrap,
        bg=Theme.BUTTON_BG,
        cursor="hand2",
        padx=10,
        pady=6,
        command=self.send_text,
        relief="flat",
        bd=0,
        highlightthickness=0,
        takefocus=False,
    )
    self.send_btn.pack(side="right", padx=(6, 0))
    if "send" in self.assets:
        if isinstance(self.assets["send"], ImageTk.PhotoImage):
            self.send_btn.config(image=self.assets["send"])
        else:
            self.send_btn.config(text=self.assets["send"], fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
    else:
        self.send_btn.config(text="➤", fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
    self._bind_hover_bg(self.send_btn, role="input_icon")

    self.mic_btn = tk.Button(
        self.controls_bar,
        bg=Theme.ACCENT,
        fg=Theme.FG,
        cursor="hand2",
        padx=15,
        pady=11,
        highlightbackground=Theme.BORDER,
        highlightthickness=1,
        command=self.mic_click,
        relief="flat",
        bd=0,
        takefocus=False,
    )
    self.mic_btn.pack(side="right", padx=(8, 0))
    if "mic" in self.assets:
        if isinstance(self.assets["mic"], ImageTk.PhotoImage):
            self.mic_btn.config(image=self.assets["mic"])
        else:
            self.mic_btn.config(text=self.assets["mic"], fg=Theme.FG, font=("Segoe UI", 16))
    else:
        self.mic_btn.config(text="🎤", fg=Theme.FG, font=("Segoe UI", 16))
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
        if hasattr(self, "_apply_main_container_bounds"):
            self._apply_main_container_bounds()
    except Exception:
        pass
    try:
        width = int(self.root.winfo_width() or self.main_container.winfo_width() or 0)
    except Exception:
        width = 0
    focus = bool(self._cfg().get_focus_mode_enabled())
    previous_mode = str(getattr(self, "_workspace_shell_layout_mode", "") or "")
    if focus:
        layout_mode = "focus"
    elif previous_mode == "wide":
        layout_mode = "wide" if width >= 1360 else "compact"
    elif previous_mode == "compact":
        layout_mode = "wide" if width >= 1440 else "compact"
    else:
        layout_mode = "wide" if width >= 1400 else "compact"

    sidebar_visible = (not focus) and layout_mode == "wide"
    compact_nav_visible = (not focus) and layout_mode == "compact"
    layout_signature = (layout_mode, sidebar_visible, compact_nav_visible)
    if layout_signature == getattr(self, "_workspace_layout_signature", None):
        return
    self._workspace_layout_signature = layout_signature
    self._workspace_shell_layout_mode = layout_mode
    self._set_focus_layout_visible(sidebar_visible, False)

    utility_shell = getattr(self, "utility_shell", None)
    if utility_shell is not None and utility_shell is not getattr(self, "chat_side", None):
        try:
            utility_shell.grid_remove()
        except Exception:
            pass

    chat_stage = getattr(self, "chat_stage", None)
    chat_side = getattr(self, "chat_side", None)
    if chat_stage is not None and chat_side is not None:
        try:
            chat_side.grid_remove()
        except Exception:
            pass

    compact_controls_row = getattr(self, "compact_controls_row", None)
    if compact_controls_row is not None:
        try:
            mapped = bool(str(compact_controls_row.winfo_manager() or "").strip())
        except Exception:
            mapped = False
        if compact_nav_visible and not mapped:
            compact_controls_row.pack(anchor="w", pady=(10, 0))
        elif not compact_nav_visible and mapped:
            compact_controls_row.pack_forget()

    quick_bar = getattr(self, "quick_bar", None)
    if quick_bar is not None:
        try:
            quick_bar.pack_forget()
        except Exception:
            pass

    current_section = getattr(self, "_workspace_section", "chat")
    if current_section:
        self._set_workspace_section(current_section)
    self._update_guide_context("focus" if focus else current_section)


def register_shell_runtime(app_cls):
    if not hasattr(app_cls, "_base_shutdown_v2"):
        app_cls._base_shutdown_v2 = app_cls.shutdown
    if not hasattr(app_cls, "_base_start_runtime_services_v2"):
        app_cls._base_start_runtime_services_v2 = app_cls._start_runtime_services
    if not hasattr(app_cls, "_base_reload_services_v2"):
        app_cls._base_reload_services_v2 = app_cls.reload_services

    def _assign(name, value):
        if name in app_cls.__dict__:
            return
        setattr(app_cls, name, value)

    _assign("_advance_guide_hint", _advance_guide_hint)
    _assign("_hide_to_tray_force", _hide_to_tray_force)
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
    _assign("_set_workspace_section", _set_workspace_section)
    _assign("_build_workspace_shell_v2", _patched_build_workspace_shell_v2)
    _assign("_rebuild_workspace_shell_v2", _patched_rebuild_workspace_shell_v2)
    _assign("_build_workspace_sidebar", _patched_build_workspace_sidebar)
    _assign("_build_workspace_overview", _patched_build_workspace_overview)
    _assign("_build_workspace_chat", _patched_build_workspace_chat)
    _assign("_build_workspace_controls", _patched_build_workspace_controls)
    _assign("_refresh_chat_empty_state", _patched_refresh_chat_empty_state)
    _assign("_build_workspace_rail", _patched_build_workspace_rail)
    _assign("refresh_workspace_layout_mode", _patched_refresh_workspace_layout_mode)
    _assign("_open_workspace_menu", _open_workspace_menu)


__all__ = ["register_shell_runtime"]

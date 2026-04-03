import logging
import glob
import json
import os
import re
import shutil
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import ImageTk

from ..audio_devices import expand_audio_device_name as _expand_audio_device_name, get_audio_device_entry as _get_audio_device_entry
from ..branding import APP_LOGGER_NAME, app_brand_name, app_version_badge
from ..commands import make_dynamic_key
from ..custom_actions import custom_actions_example
from ..guide_noobs import GuideNoobPanel
from ..release_meta import DEFAULT_GITHUB_REPO, DEFAULT_RELEASE_API_URL, DEFAULT_RELEASES_URL
from ..runtime import runtime_root_path
from ..state import CONFIG_MGR, DEFAULT_CHAT_MODEL, db, get_config_path
from ..storage import app_log_dir, custom_actions_path
from ..theme import Theme
from ..ui_factory import bind_dynamic_wrap, create_action_button, create_action_grid, create_note_box, create_section_card

LOG_FILE = os.path.join(app_log_dir(), "jarvis.log")
logger = logging.getLogger(APP_LOGGER_NAME)


class SettingsUiMixin:
    def _settings_toast(self, message: str, tone: str = "ok"):
        text = str(message or "").strip()
        if not text:
            return
        if callable(getattr(self, "set_status_temp", None)):
            self.set_status_temp(text, tone)
            return
        if callable(getattr(self, "set_status", None)):
            self.set_status(text, tone)

    def _hide_workspace_surface_for_settings(self):
        bg_canvas = getattr(self, "bg_canvas", None)
        if bg_canvas is None:
            return
        try:
            if bg_canvas.winfo_manager():
                bg_canvas.pack_forget()
        except tk.TclError:
            return

    def _restore_workspace_surface_after_settings(self):
        bg_canvas = getattr(self, "bg_canvas", None)
        if bg_canvas is None:
            return
        try:
            if not bg_canvas.winfo_manager():
                bg_canvas.pack(fill="both", expand=True)
        except tk.TclError:
            return

    def _suspend_activation_gate_for_settings(self):
        gate = getattr(self, "activation_gate", None)
        suspended = False
        if gate is not None:
            try:
                suspended = bool(gate.winfo_ismapped())
            except tk.TclError:
                suspended = False
        self._settings_activation_gate_suspended = suspended
        if not suspended:
            return
        hide_gate = getattr(self, "_hide_embedded_activation_gate", None)
        if callable(hide_gate):
            try:
                hide_gate()
            except tk.TclError:
                pass

    def _resume_activation_gate_after_settings(self):
        if not bool(getattr(self, "_settings_activation_gate_suspended", False)):
            return
        self._settings_activation_gate_suspended = False
        if not bool(getattr(self, "_startup_gate_setup", False)):
            return
        show_gate = getattr(self, "_show_embedded_activation_gate", None)
        if callable(show_gate):
            try:
                show_gate()
            except tk.TclError:
                pass

    def _hide_legacy_settings_surfaces(self):
        panel = getattr(self, "quick_settings_panel", None)
        if panel is not None:
            try:
                if panel.winfo_exists():
                    panel.place_forget()
            except Exception:
                pass
        page = getattr(self, "embedded_settings_page", None)
        if page is not None:
            try:
                if page.winfo_exists():
                    page.pack_forget()
                    page.grid_forget()
                    page.place_forget()
            except Exception:
                pass

    def _save_settings_tab1_from_footer(self):
        cb = getattr(self, "_settings_tab1_save_callback", None)
        if callable(cb):
            cb()
            return
        messagebox.showinfo(app_brand_name(), "Откройте вкладку «Основные», затем попробуйте сохранить ещё раз.")

    def _destroy_control_center_window(self, resume_bg: bool = True):
        win = getattr(self, "settings_window", None)
        canvas = getattr(self, "_control_center_content_canvas", None)

        def _cancel_after(widget, attr_name: str):
            after_id = getattr(self, attr_name, None)
            setattr(self, attr_name, None)
            if widget is None or after_id is None:
                return
            try:
                widget.after_cancel(after_id)
            except Exception:
                pass

        _cancel_after(win, "_control_center_layout_after_id")
        _cancel_after(win, "_control_center_prewarm_after_id")
        _cancel_after(canvas, "_control_center_scroll_after_id")
        self._settings_tab1_save_callback = None
        self.settings_window = None
        self._control_center_outer = None
        self._control_center_header_body = None
        self._control_center_header_left = None
        self._control_center_header_right = None
        self._control_center_body = None
        self._control_center_side = None
        self._control_center_nav = None
        self._control_center_nav_buttons = {}
        self.settings_nav_buttons = {}
        self._control_center_nav_note = None
        self._control_center_guide_host = None
        self._control_center_guide = None
        self._control_center_content = None
        self._control_center_content_canvas = None
        self._control_center_content_scroll = None
        self._control_center_content_inner = None
        self._control_center_content_inner_id = None
        self._control_center_pages = {}
        self._control_center_page_builders = {}
        self._control_center_built_pages = set()
        self._control_center_layout_signature = None
        self._control_center_prewarm_queue = []
        self._control_center_prewarm_running = False
        self._control_center_prewarm_done = False
        self._control_center_scroll_signature = None
        self._control_center_scroll_top_pending = False
        if getattr(self, "_preferred_scroll_target", None) == canvas:
            self._preferred_scroll_target = None
        if getattr(self, "_active_scroll_target", None) == canvas:
            self._active_scroll_target = None
        try:
            if win is not None and win.winfo_exists():
                win.destroy()
        except Exception:
            pass
        try:
            self._cleanup_scroll_targets()
        except Exception:
            pass
        if resume_bg:
            self._set_bg_animation_paused(False, reason="settings_window")

    def _schedule_control_center_reopen(self, tab_key: Optional[str] = None):
        target = self._control_center_tab_alias(tab_key or getattr(self, "current_settings_subsection", "main"))
        if bool(getattr(self, "_control_center_rebuild_pending", False)):
            self._control_center_rebuild_target = target
            return
        self._control_center_rebuild_pending = True
        self._control_center_rebuild_target = target

        def _reopen():
            target_key = self._control_center_tab_alias(getattr(self, "_control_center_rebuild_target", target))
            self._control_center_rebuild_pending = False
            self._control_center_rebuild_target = None
            self.open_full_settings_view(target_key)

        try:
            self.root.after_idle(_reopen)
        except Exception:
            _reopen()

    def _is_full_settings_open(self) -> bool:
        win = getattr(self, "settings_window", None)
        if win is None:
            return False
        try:
            return bool(win.winfo_exists() and win.winfo_ismapped())
        except Exception:
            return False

    def _control_center_geometry_preset(self):
        try:
            sw = max(int(self.root.winfo_screenwidth() or 0), 720)
            sh = max(int(self.root.winfo_screenheight() or 0), 540)
        except Exception:
            sw, sh = 1366, 768
        usable_w = max(560, sw - 36)
        usable_h = max(460, sh - 72)
        min_w = min(1040, usable_w)
        min_h = min(700, usable_h)
        pref_w = min(1440, usable_w)
        pref_h = min(920, usable_h)
        pref_w = max(min_w, pref_w)
        pref_h = max(min_h, pref_h)
        x = max((sw - pref_w) // 2, 0)
        y = max((sh - pref_h) // 2, 0)
        return min_w, min_h, f"{pref_w}x{pref_h}+{x}+{y}"

    def _sync_control_center_window_to_root(self, win=None):
        window = win or getattr(self, "settings_window", None)
        if window is None:
            return
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return
        if not isinstance(window, tk.Toplevel):
            return
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            root_state = str(self.root.state() or "").lower()
        except Exception:
            root_state = "normal"
        try:
            if root_state == "zoomed":
                window.state("zoomed")
                return
        except Exception:
            pass
        try:
            window.state("normal")
        except Exception:
            pass
        try:
            min_w, min_h, _ = self._control_center_geometry_preset()
            root_w = int(self.root.winfo_width() or 0)
            root_h = int(self.root.winfo_height() or 0)
            root_x = int(self.root.winfo_rootx() or 0)
            root_y = int(self.root.winfo_rooty() or 0)
            screen_w = max(int(self.root.winfo_screenwidth() or 0), root_w, min_w)
            screen_h = max(int(self.root.winfo_screenheight() or 0), root_h, min_h)
        except Exception:
            return
        if root_w <= 0 or root_h <= 0:
            return
        target_w = min(max(root_w, min_w), max(screen_w - 24, min_w))
        target_h = min(max(root_h, min_h), max(screen_h - 48, min_h))
        target_x = min(max(root_x, 0), max(screen_w - target_w, 0))
        target_y = min(max(root_y, 0), max(screen_h - target_h, 0))
        try:
            window.geometry(f"{target_w}x{target_h}+{target_x}+{target_y}")
        except Exception:
            pass

    def _schedule_control_center_layout_refresh(self):
        win = getattr(self, "settings_window", None)
        if win is None:
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        after_id = getattr(self, "_control_center_layout_after_id", None)
        if after_id is not None:
            try:
                win.after_cancel(after_id)
            except Exception:
                pass

        def _refresh():
            self._control_center_layout_after_id = None
            self._refresh_control_center_layout()

        self._control_center_layout_after_id = win.after(32, _refresh)

    def _refresh_control_center_layout(self):
        win = getattr(self, "settings_window", None)
        body = getattr(self, "_control_center_body", None)
        side = getattr(self, "_control_center_side", None)
        content = getattr(self, "_control_center_content", None)
        header_body = getattr(self, "_control_center_header_body", None)
        header_left = getattr(self, "_control_center_header_left", None)
        header_right = getattr(self, "_control_center_header_right", None)
        guide_host = getattr(self, "_control_center_guide_host", None)
        guide_note = getattr(self, "_control_center_nav_note", None)
        nav = getattr(self, "_control_center_nav", None)
        if not all(widget is not None for widget in (win, body, side, content, header_body, header_left, header_right)):
            return
        try:
            width = max(int(win.winfo_width() or 0), 1)
        except Exception:
            return

        header_stacked = width < 980
        show_guide = width >= 1100
        side_width = 256
        layout_signature = (header_stacked, side_width, show_guide)
        if layout_signature == getattr(self, "_control_center_layout_signature", None):
            return
        self._control_center_layout_signature = layout_signature

        try:
            header_left.pack_forget()
            header_right.pack_forget()
        except Exception:
            pass
        if header_stacked:
            header_left.pack(fill="x", expand=True)
            header_right.pack(fill="x", pady=(12, 0))
        else:
            header_left.pack(side="left", fill="x", expand=True)
            header_right.pack(side="right", padx=(16, 0))

        try:
            body.grid_columnconfigure(0, weight=0)
            body.grid_columnconfigure(1, weight=1)
            body.grid_rowconfigure(0, weight=1)
            body.grid_rowconfigure(1, weight=0)
            side.grid(row=0, column=0, columnspan=1, sticky="nsw", padx=(0, 12), pady=0)
            content.grid(row=0, column=1, columnspan=1, sticky="nsew")
            side.grid_propagate(False)
            side.configure(width=side_width)
        except Exception:
            pass

        if guide_host is not None:
            try:
                guide_host.configure(width=max(side_width - 24, 208))
            except Exception:
                pass
            try:
                mapped = bool(str(guide_host.winfo_manager() or "").strip())
            except Exception:
                mapped = False
            if show_guide and not mapped:
                try:
                    if guide_note is not None and guide_note.winfo_exists():
                        guide_host.pack(fill="x", padx=12, pady=(0, 12), before=guide_note)
                    else:
                        guide_host.pack(fill="x", padx=12, pady=(0, 12))
                except Exception:
                    pass
            elif not show_guide and mapped:
                try:
                    guide_host.pack_forget()
                except Exception:
                    pass

        if nav is not None:
            try:
                nav.configure(padx=10 if width < 1120 else 14)
            except Exception:
                pass

    def _settings_dialog_parent(self):
        for attr in ("embedded_settings_page", "quick_settings_panel", "settings_window"):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                if widget.winfo_exists():
                    if isinstance(widget, tk.Toplevel):
                        return widget
            except Exception:
                continue
        return self.root

    def _save_quick_settings_panel(self):
        provider_items = getattr(self, "_quick_tts_provider_items", [])
        if not provider_items:
            return
        try:
            tg_id_raw = str(self._quick_tg_id_var.get() if hasattr(self, "_quick_tg_id_var") else "").strip()
            tg_id = int(tg_id_raw) if tg_id_raw else 0
        except Exception:
            tg_id = 0
        provider_label = str(self._quick_tts_provider_var.get() if hasattr(self, "_quick_tts_provider_var") else "").strip()
        selected_provider = next((key for label, key in provider_items if label == provider_label), "pyttsx3")
        eleven_key = str(self._quick_eleven_key_var.get() if hasattr(self, "_quick_eleven_key_var") else "").strip()
        eleven_voice = str(self._quick_eleven_voice_var.get() if hasattr(self, "_quick_eleven_voice_var") else "").strip()
        if selected_provider == "elevenlabs" and (not eleven_key or not eleven_voice):
            messagebox.showwarning(
                app_brand_name(),
                "Для ElevenLabs в быстрых настройках нужны и API-ключ, и ID голоса.\nПока сохраню безопасный оффлайн-режим pyttsx3.",
                parent=self._settings_dialog_parent(),
            )
            selected_provider = "pyttsx3"
        CONFIG_MGR.set_many({
            "api_key": str(self._quick_groq_var.get() if hasattr(self, "_quick_groq_var") else "").strip(),
            "telegram_token": str(self._quick_tg_token_var.get() if hasattr(self, "_quick_tg_token_var") else "").strip(),
            "telegram_user_id": tg_id,
            "allowed_user_ids": [tg_id] if tg_id else [],
            "tts_provider": selected_provider,
            "edge_tts_voice": str(self._quick_edge_voice_var.get() if hasattr(self, "_quick_edge_voice_var") else "").strip(),
            "elevenlabs_api_key": eleven_key,
            "elevenlabs_voice_id": eleven_voice,
        })
        self.reload_services()
        self.refresh_mic_status_label()
        self.refresh_output_status_label()
        self.refresh_tts_status_label()
        self._build_quick_settings_panel()
        self.set_status("Быстрые настройки сохранены", "ok")
        self.root.after(1800, lambda: self.set_status("Готов", "ok"))

    def _build_quick_settings_panel(self):
        panel = getattr(self, "quick_settings_panel", None)
        if panel is None or not panel.winfo_exists():
            panel = tk.Frame(
                self.main_container,
                bg=Theme.CARD_BG,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
            )
            self.quick_settings_panel = panel
        for child in list(panel.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        try:
            panel.pack_propagate(False)
        except Exception:
            pass

        def entry_row(parent, label: str, value: str = "", show: str = "", help_text: str = ""):
            row = tk.Frame(parent, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 8))
            self._create_settings_field_header(row, label, help_text, font=("Segoe UI Semibold", 10))
            var = tk.StringVar(value=value or "")
            entry = tk.Entry(
                row,
                textvariable=var,
                bg=Theme.INPUT_BG,
                fg=Theme.FG,
                insertbackground=Theme.FG,
                relief="flat",
                show=show,
            )
            entry.pack(fill="x", ipady=6, pady=(3, 0))
            self._setup_entry_bindings(entry)
            return var, entry

        def dropdown_row(parent, label: str, values: List[str], value: str, help_text: str = ""):
            row = tk.Frame(parent, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 8))
            self._create_settings_field_header(row, label, help_text, font=("Segoe UI Semibold", 10))
            var = tk.StringVar(value=value or (values[0] if values else ""))
            shell, button = self._create_settings_choice_control(row, var, values, font=("Segoe UI", 10))
            shell.pack(fill="x", pady=(3, 0))
            return var, button

        head = tk.Frame(panel, bg=Theme.CARD_BG)
        head.pack(fill="x", padx=14, pady=(14, 8))
        tk.Label(head, text="Быстрые настройки", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(
            head,
            text=app_version_badge(),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            head,
            text="✕",
            command=lambda: self.toggle_quick_settings_panel(False),
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            relief="flat",
            width=3,
        ).pack(side="right")

        tk.Label(
            panel,
            text="Только важное: ключи, Telegram и голос. Все тяжелые настройки остаются в полном центре управления ниже.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=332,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=14, pady=(0, 10))

        footer = tk.Frame(panel, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        footer.pack(side="bottom", fill="x", padx=14, pady=(8, 14))
        tk.Button(
            footer,
            text="Подробнее",
            command=lambda: (self.toggle_quick_settings_panel(False), self.open_full_settings_view()),
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            relief="flat",
            padx=12,
            pady=9,
        ).pack(side="left", padx=10, pady=10)
        tk.Button(
            footer,
            text="Сохранить",
            command=self._save_quick_settings_panel,
            bg=Theme.ACCENT,
            fg=Theme.FG,
            relief="flat",
            padx=14,
            pady=9,
        ).pack(side="right", padx=10, pady=10)

        content_wrap = tk.Frame(panel, bg=Theme.CARD_BG)
        content_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 0))
        content_canvas = tk.Canvas(content_wrap, bg=Theme.CARD_BG, highlightthickness=0, bd=0)
        content_scroll = ttk.Scrollbar(
            content_wrap,
            orient="vertical",
            command=content_canvas.yview,
            style="Jarvis.Vertical.TScrollbar",
        )
        content_scroll.pack(side="right", fill="y")
        content_canvas.configure(yscrollcommand=content_scroll.set)
        content_canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(content_canvas, bg=Theme.CARD_BG)
        body_id = content_canvas.create_window((0, 0), window=body, anchor="nw")

        def _sync_quick_settings_body(_event=None):
            try:
                content_canvas.configure(scrollregion=content_canvas.bbox("all"))
            except Exception:
                pass

        body.bind("<Configure>", _sync_quick_settings_body)
        content_canvas.bind(
            "<Configure>",
            lambda e: content_canvas.itemconfigure(body_id, width=max(1, int(getattr(e, "width", 0) or content_canvas.winfo_width()))),
        )
        self._register_scroll_target(content_canvas)

        self._quick_groq_var, _ = entry_row(body, "Groq API-ключ", CONFIG_MGR.get_api_key(), show="•", help_text="Секретный ключ для доступа к мозгу JARVIS через Groq. Без него чат и команды ИИ работать не будут.")
        self._quick_tg_token_var, _ = entry_row(body, "Токен Telegram-бота", CONFIG_MGR.get_telegram_token(), show="•", help_text="Нужен только если хотите управлять JARVIS из Telegram.")
        self._quick_tg_id_var, _ = entry_row(body, "ID пользователя Telegram", str(CONFIG_MGR.get_telegram_user_id() or ""), help_text="Личный ID того пользователя, которому разрешено писать вашему боту.")

        self._quick_tts_provider_items = [
            ("pyttsx3 — оффлайн / стабильно", "pyttsx3"),
            ("Edge-TTS — онлайн / быстро", "edge-tts"),
            ("ElevenLabs — онлайн / вау", "elevenlabs"),
        ]
        current_provider = CONFIG_MGR.get_tts_provider()
        current_provider_label = next((label for label, key in self._quick_tts_provider_items if key == current_provider), self._quick_tts_provider_items[0][0])
        self._quick_tts_provider_var, _ = dropdown_row(
            body,
            "Источник TTS",
            [label for label, _key in self._quick_tts_provider_items],
            current_provider_label,
            help_text="Выбор движка озвучки: оффлайн-режим без сети, быстрый онлайн-голос или максимальное качество через ElevenLabs.",
        )
        self._quick_edge_voice_var, _ = entry_row(body, "Голос Edge-TTS", CONFIG_MGR.get_edge_tts_voice(), help_text="Точное имя голоса Edge-TTS. Нужен только если выбран Edge-TTS.")
        self._quick_eleven_key_var, _ = entry_row(body, "API-ключ ElevenLabs", CONFIG_MGR.get_elevenlabs_api_key(), show="•", help_text="Секретный ключ ElevenLabs для онлайн-озвучки.")
        self._quick_eleven_voice_var, _ = entry_row(body, "ID голоса ElevenLabs", CONFIG_MGR.get_elevenlabs_voice_id(), help_text="Идентификатор голоса внутри ElevenLabs. Без него сервис не сможет озвучивать текст.")

        status_card = tk.Frame(body, bg=Theme.BUTTON_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        status_card.pack(fill="x", pady=(6, 8))
        tk.Label(status_card, text="Сейчас активно", bg=Theme.BUTTON_BG, fg=Theme.FG, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        tk.Label(
            status_card,
            text=f"Микрофон: {self._shorten_device_name(self.get_selected_microphone_name(), 54)}",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=280,
        ).pack(anchor="w", padx=10)
        tk.Label(
            status_card,
            text=f"Вывод: {self._shorten_device_name(self.get_selected_output_name(), 54)}",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=280,
        ).pack(anchor="w", padx=10, pady=(2, 0))
        tk.Label(
            status_card,
            text="Подсказка: для минимальной задержки используйте Edge-TTS. Для максимального качества — ElevenLabs.",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=280,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=10, pady=(6, 8))

        self._restyle_settings_window()
        return panel

    def toggle_quick_settings_panel(self, force: Optional[bool] = None):
        if force is False:
            self._hide_legacy_settings_surfaces()
            self._set_bg_animation_paused(False, reason="quick_settings")
            return
        self._hide_legacy_settings_surfaces()
        self.open_full_settings_view("main")

    def _build_embedded_settings_page(self):
        page = getattr(self, "embedded_settings_page", None)
        if page is None or not page.winfo_exists():
            page = tk.Frame(self.content_stage, bg=Theme.BG_LIGHT)
            self.embedded_settings_page = page
        for child in list(page.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._settings_tab1_save_callback = None
        self._configure_ttk_styles()

        shell = tk.Frame(page, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=8, pady=8)
        body = tk.Frame(shell, bg=Theme.CARD_BG)
        body.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(
            body,
            text="Настройки теперь открываются отдельно",
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=("Segoe UI Semibold", 18),
            justify="left",
        ).pack(anchor="w")
        desc = tk.Label(
            body,
            text="Главный экран больше не разворачивает длинные вкладки внутри чата. Для голоса, памяти, сценариев, релиза и профиля открывается отдельный центр управления.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 11),
            justify="left",
            wraplength=760,
        )
        desc.pack(fill="x", pady=(10, 16))
        tk.Button(
            body,
            text="Открыть центр управления",
            command=lambda: self.open_full_settings_view("main"),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            relief="flat",
            padx=18,
            pady=10,
        ).pack(anchor="w")
        note = tk.Label(
            body,
            text="Если увидели этот экран, значит сработал старый маршрут интерфейса. Основной сценарий теперь только один: чат на главном экране и отдельный центр управления по кнопке.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 10),
            wraplength=760,
        )
        note.pack(fill="x", pady=(16, 0))
        bind_dynamic_wrap(desc, body, padding=24, minimum=320)
        bind_dynamic_wrap(note, body, padding=24, minimum=320)
        return page

    def _select_embedded_settings_tab(self, tab_key: Optional[str] = None):
        notebook = getattr(self, "embedded_settings_notebook", None)
        tabs = getattr(self, "embedded_settings_tabs", {})
        if notebook is None or not tabs:
            return
        normalized = str(tab_key or "main").strip().lower()
        aliases = {
            "system": "system",
            "technical": "system",
            "main": "main",
            "profile": "main",
            "ai": "main",
            "apps": "apps",
            "voice": "audio",
            "audio": "audio",
            "diagnostics": "diagnostics",
            "readiness": "diagnostics",
            "updates": "updates",
            "release": "updates",
        }
        target = tabs.get(aliases.get(normalized, "main"))
        if target is None:
            return
        try:
            notebook.select(target)
        except Exception:
            pass

    def _sync_embedded_settings_workspace_section(self):
        notebook = getattr(self, "embedded_settings_notebook", None)
        tabs = getattr(self, "embedded_settings_tabs", {})
        if notebook is None or not tabs:
            return
        try:
            current = str(notebook.select() or "")
        except Exception:
            return
        reverse = {str(widget): key for key, widget in tabs.items()}
        current_key = reverse.get(current, "main")
        section = {
            "audio": "voice",
            "main": "main",
            "apps": "apps",
            "diagnostics": "diagnostics",
            "updates": "updates",
            "technical": "system",
            "system": "system",
        }.get(current_key, "main")
        if hasattr(self, "_set_workspace_section"):
            try:
                self._set_workspace_section(section)
            except Exception:
                pass

    def _control_center_tab_alias(self, tab_key: Optional[str] = None) -> str:
        normalized = str(tab_key or self._cfg().get_last_control_center_section() or "main").strip().lower()
        aliases = {
            "main": "main",
            "profile": "main",
            "ai": "main",
            "voice": "voice",
            "audio": "voice",
            "diagnostics": "diagnostics",
            "readiness": "diagnostics",
            "apps": "apps",
            "updates": "updates",
            "release": "updates",
            "system": "system",
            "technical": "system",
        }
        return aliases.get(normalized, "main")

    def _control_center_noob_message(self, section: str):
        mapping = {
            "main": (
                "Нубик JARVIS",
                "Основное",
                "Здесь активация, ключ Groq, профиль пользователя и базовые настройки JARVIS.",
                "→ Если ключа нет или ИИ не отвечает, начните отсюда.",
            ),
            "voice": (
                "Нубик JARVIS",
                "Центр голоса",
                "Здесь проверяются микрофон, тестовая запись, прослушивание и профиль устройства.",
                "→ Сначала тестовая запись, потом глубокая диагностика.",
            ),
            "apps": (
                "Нубик JARVIS",
                "Приложения и игры",
                "Здесь добавляются ваши приложения, ярлыки и команды запуска.",
                "→ Если программа не открывается по имени, проверьте этот раздел.",
            ),
            "diagnostics": (
                "Нубик JARVIS",
                "Диагностика",
                "Здесь readiness-check, crash test и внутренняя проверка кода.",
                "→ Это техзона. Для обычного пользования она нужна редко.",
            ),
            "updates": (
                "Нубик JARVIS",
                "Релиз",
                "Здесь обновления, release lock, backup и контроль артефактов перед GitHub release.",
                "→ Перед публикацией прогоните release lock и readiness.",
            ),
            "system": (
                "Нубик JARVIS",
                "Система",
                "Здесь память, сценарии, журнал, бэкапы и сервисные инструменты.",
                "→ Всё тяжёлое убрано сюда, чтобы не перегружать чат.",
            ),
        }
        return mapping.get(section, mapping["main"])

    def _set_control_center_guide_hint(self, title: str = "", status: str = "", text: str = "", pointer: str = ""):
        guide = getattr(self, "_control_center_guide", None)
        if guide is None:
            return
        guide.set_message(
            title=title or "Нубик JARVIS",
            status=status or "Подсказка",
            text=text or "Наведитесь на кнопку или переключитесь на нужный раздел, и я коротко объясню, что здесь происходит.",
            pointer=pointer or "→ Клик по Нубику вернет общую подсказку по разделу.",
        )

    def _bind_control_center_guide_hint(self, widget, title: str, status: str, text: str, pointer: str = ""):
        if widget is None:
            return

        def _apply_hint(_event=None):
            self._set_control_center_guide_hint(title=title, status=status, text=text, pointer=pointer)

        try:
            widget.bind("<Enter>", _apply_hint, add="+")
            widget.bind("<FocusIn>", _apply_hint, add="+")
        except Exception:
            pass

    def _make_settings_help_badge(self, parent, text: str = ""):
        badge = tk.Button(
            parent,
            text="?",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            width=2,
            padx=0,
            pady=0,
            cursor="question_arrow",
            font=("Segoe UI Semibold", 10),
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            relief="flat",
            bd=0,
            takefocus=False,
        )
        tip = str(text or "").strip()
        if tip:
            self._bind_control_center_guide_hint(
                badge,
                "Нубик JARVIS",
                "Что это значит?",
                tip,
                "→ Это короткое объяснение именно этой настройки, без лишней технички.",
            )
            try:
                badge.configure(
                    command=lambda t=tip: messagebox.showinfo(
                        "Что это значит?",
                        t,
                        parent=self._settings_dialog_parent(),
                    )
                )
            except Exception:
                pass
        return badge

    def _create_settings_field_header(self, parent, label: str, help_text: str = "", *, font=None):
        head = tk.Frame(parent, bg=parent.cget("bg"))
        head.pack(fill="x")
        tk.Label(
            head,
            text=label,
            bg=parent.cget("bg"),
            fg=Theme.FG,
            font=font or ("Segoe UI Semibold", 11),
        ).pack(side="left", anchor="w")
        if str(help_text or "").strip():
            badge = self._make_settings_help_badge(head, help_text)
            badge.pack(side="right")
        return head

    def _create_settings_choice_control(self, parent, variable, values, *, font=None):
        options = [str(item) for item in list(values or []) if str(item or "").strip()]
        if not options:
            options = ["(нет вариантов)"]

        try:
            current = str(variable.get() if isinstance(variable, tk.StringVar) else "").strip()
        except Exception:
            current = ""
        if not current:
            try:
                variable.set(options[0])
            except Exception:
                pass

        shell = tk.Frame(
            parent,
            bg=Theme.INPUT_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            bd=0,
        )
        display_var = tk.StringVar(value="")
        menu = tk.Menu(
            shell,
            tearoff=0,
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            activebackground=Theme.ACCENT,
            activeforeground=Theme.FG,
            bd=0,
            relief="flat",
            font=font or ("Segoe UI", 11),
        )

        def _sync_label(*_args):
            try:
                selected = str(variable.get() if isinstance(variable, tk.StringVar) else "").strip()
            except Exception:
                selected = ""
            if not selected:
                selected = options[0]
            display_var.set(f"{selected}   ▾")

        def _select(choice: str):
            try:
                variable.set(str(choice))
            except Exception:
                pass
            _sync_label()
            try:
                button.event_generate("<<JarvisSelectorChanged>>")
            except Exception:
                pass

        for item in options:
            menu.add_command(label=item, command=lambda value=item: _select(value))

        def _open_menu(event=None):
            del event
            try:
                x = button.winfo_rootx()
                y = button.winfo_rooty() + button.winfo_height() + 2
                menu.tk_popup(x, y)
            finally:
                try:
                    menu.grab_release()
                except Exception:
                    pass

        button = tk.Button(
            shell,
            textvariable=display_var,
            command=_open_menu,
            anchor="w",
            justify="left",
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            activebackground=Theme.BUTTON_BG,
            activeforeground=Theme.FG,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=font or ("Segoe UI", 11),
            padx=12,
            pady=7,
        )
        button.pack(fill="x")

        def _hover_on(_event=None):
            try:
                button.configure(bg=Theme.BUTTON_BG)
            except Exception:
                pass

        def _hover_off(_event=None):
            try:
                button.configure(bg=Theme.INPUT_BG)
            except Exception:
                pass

        for seq, handler in (
            ("<Enter>", _hover_on),
            ("<Leave>", _hover_off),
            ("<FocusIn>", _hover_on),
            ("<FocusOut>", _hover_off),
        ):
            try:
                button.bind(seq, handler, add="+")
            except Exception:
                pass

        if isinstance(variable, tk.StringVar):
            try:
                variable.trace_add("write", _sync_label)
            except Exception:
                pass
        _sync_label()
        try:
            setattr(button, "_jarvis_select", _select)
            setattr(button, "_jarvis_values", tuple(options))
            setattr(button, "_jarvis_menu", menu)
        except Exception:
            pass
        return shell, button

    def _show_control_center_guide_popup(self):
        section = self._control_center_tab_alias(self._cfg().get_last_control_center_section())
        title, status, text, pointer = self._control_center_noob_message(section)
        body = "\n\n".join(part for part in (status, text, pointer) if str(part or "").strip())
        messagebox.showinfo(title, body, parent=self._settings_dialog_parent())

    def _ensure_control_center_page_built(self, key: str):
        pages = getattr(self, "_control_center_pages", {})
        builders = getattr(self, "_control_center_page_builders", {})
        built = getattr(self, "_control_center_built_pages", set())
        page = pages.get(key)
        builder = builders.get(key)
        if page is None or builder is None or key in built:
            return page
        try:
            setattr(page, "_jarvis_plain_scroll_host", True)
        except Exception:
            pass
        builder(page)
        try:
            self._schedule_control_center_content_scroll_refresh()
        except Exception:
            pass
        built.add(key)
        self._control_center_built_pages = built
        return page

    def _schedule_control_center_content_scroll_refresh(self, scroll_top: bool = False):
        canvas = getattr(self, "_control_center_content_canvas", None)
        if canvas is None:
            return
        if scroll_top:
            self._control_center_scroll_top_pending = True
        after_id = getattr(self, "_control_center_scroll_after_id", None)
        if after_id is not None:
            try:
                canvas.after_cancel(after_id)
            except Exception:
                pass

        def _refresh():
            self._control_center_scroll_after_id = None
            reset_scroll = bool(getattr(self, "_control_center_scroll_top_pending", False))
            self._control_center_scroll_top_pending = False
            self._refresh_control_center_content_scroll(scroll_top=reset_scroll)

        try:
            self._control_center_scroll_after_id = canvas.after(16, _refresh)
        except Exception:
            _refresh()

    def _schedule_settings_visual_refresh(self):
        try:
            self._schedule_control_center_layout_refresh()
        except Exception:
            pass
        try:
            self._schedule_control_center_content_scroll_refresh()
        except Exception:
            pass

    def _schedule_control_center_prewarm(self, preferred: Optional[str] = None):
        win = getattr(self, "settings_window", None)
        if win is None:
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        if bool(getattr(self, "_control_center_prewarm_done", False)):
            return
        if bool(getattr(self, "_control_center_prewarm_running", False)):
            return
        pages = list(getattr(self, "_control_center_pages", {}).keys())
        if not pages:
            return
        preferred_key = self._control_center_tab_alias(preferred)
        ordered = [preferred_key] if preferred_key in pages else []
        ordered.extend(key for key in pages if key not in ordered)
        self._control_center_prewarm_queue = ordered
        self._control_center_prewarm_running = True

        def _step():
            self._control_center_prewarm_after_id = None
            live_win = getattr(self, "settings_window", None)
            if live_win is None:
                self._control_center_prewarm_running = False
                return
            try:
                if not live_win.winfo_exists():
                    self._control_center_prewarm_running = False
                    return
            except Exception:
                self._control_center_prewarm_running = False
                return
            queue = list(getattr(self, "_control_center_prewarm_queue", []))
            if not queue:
                self._control_center_prewarm_running = False
                self._control_center_prewarm_done = True
                try:
                    self._schedule_control_center_content_scroll_refresh()
                except Exception:
                    pass
                return
            key = str(queue.pop(0))
            self._control_center_prewarm_queue = queue
            try:
                self._ensure_control_center_page_built(key)
            except Exception:
                pass
            try:
                self._schedule_control_center_layout_refresh()
            except Exception:
                pass
            try:
                self._control_center_prewarm_after_id = live_win.after(140, _step)
            except Exception:
                self._control_center_prewarm_running = False

        try:
            self._control_center_prewarm_after_id = win.after(140, _step)
        except Exception:
            self._control_center_prewarm_running = False

    def _create_voice_center_page(self, parent):
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

    def _show_control_center_section(self, tab_key: Optional[str] = None):
        normalized = self._control_center_tab_alias(tab_key)
        self.current_settings_subsection = normalized
        self._cfg().set_last_control_center_section(normalized)

        pages = getattr(self, "_control_center_pages", {})
        buttons = getattr(self, "_control_center_nav_buttons", {})
        if not pages:
            return
        self._ensure_control_center_page_built(normalized)

        for key, frame in pages.items():
            try:
                if key == normalized:
                    frame.pack(fill="both", expand=True)
                else:
                    frame.pack_forget()
            except Exception:
                pass
        try:
            self._schedule_control_center_content_scroll_refresh(scroll_top=True)
        except Exception:
            pass

        for key, btn in buttons.items():
            try:
                active = key == normalized
                btn.configure(
                    bg=Theme.ACCENT if active else Theme.BUTTON_BG,
                    font=("Segoe UI", 11, "bold" if active else "normal"),
                )
            except Exception:
                pass

        guide = getattr(self, "_control_center_guide", None)
        if guide is not None:
            title, status, text, pointer = self._control_center_noob_message(normalized)
            guide.set_message(title=title, status=status, text=text, pointer=pointer)

        try:
            self._refresh_memory_widgets()
        except Exception:
            pass
        try:
            self._refresh_scenario_widgets()
        except Exception:
            pass
        try:
            self._refresh_activity_widgets()
        except Exception:
            pass
        try:
            self._apply_voice_insight_widgets()
        except Exception:
            pass

    def _build_control_center_window(self):
        win = getattr(self, "settings_window", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    return win
            except Exception:
                pass

        self._set_bg_animation_paused(True, reason="settings_window")
        win = tk.Frame(self.root, bg=Theme.BG)
        self.settings_window = win
        win.bind("<Escape>", lambda _event: self.close_full_settings_view(), add="+")

        outer = tk.Frame(win, bg=Theme.BG_LIGHT, highlightbackground=Theme.BORDER, highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=14, pady=14)
        self._control_center_outer = outer

        header = tk.Frame(outer, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        header.pack(fill="x", padx=14, pady=(14, 12))
        header_body = tk.Frame(header, bg=Theme.CARD_BG)
        header_body.pack(fill="x", padx=16, pady=16)
        self._control_center_header_body = header_body

        header_left = tk.Frame(header_body, bg=Theme.CARD_BG)
        header_left.pack(side="left", fill="x", expand=True)
        self._control_center_header_left = header_left
        tk.Label(header_left, text="Центр управления JARVIS", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 19)).pack(anchor="w")
        desc = tk.Label(
            header_left,
            text="Чат остается на главном экране. Здесь открываются только настройки, голосовая диагностика, память, сценарии и релизные инструменты.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 10),
        )
        desc.pack(anchor="w", fill="x", pady=(6, 0))
        bind_dynamic_wrap(desc, header_left, padding=24, minimum=320)

        header_right = tk.Frame(header_body, bg=Theme.CARD_BG)
        header_right.pack(side="right", padx=(16, 0))
        self._control_center_header_right = header_right
        save_btn = tk.Button(header_right, text="Сохранить основные", command=self._save_settings_tab1_from_footer, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8, cursor="hand2")
        save_btn.pack(side="right")
        close_btn = tk.Button(header_right, text="Закрыть", command=self.close_full_settings_view, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8, cursor="hand2")
        close_btn.pack(side="right", padx=(0, 8))
        self._bind_control_center_guide_hint(
            save_btn,
            "Нубик JARVIS",
            "Сохранить основные",
            "Эта кнопка быстро сохраняет базовые параметры: ключи, профиль, аудио, тему и чувствительность голоса.",
            "→ Если меняли что-то важное в разделе «Основное», нажмите сначала сюда.",
        )
        self._bind_control_center_guide_hint(
            close_btn,
            "Нубик JARVIS",
            "Закрыть центр",
            "Закрывает окно настроек и возвращает вас к главному экрану без перезапуска приложения.",
            "→ Перед закрытием лучше сохранить изменения, если вы трогали базовые настройки.",
        )

        body = tk.Frame(outer, bg=Theme.BG_LIGHT)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self._control_center_body = body

        side = tk.Frame(body, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1, width=248)
        side.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        side.grid_propagate(False)
        self._control_center_side = side

        nav = tk.Frame(side, bg=Theme.CARD_BG)
        nav.pack(fill="x", padx=14, pady=(16, 10))
        self._control_center_nav = nav
        tk.Label(nav, text="Разделы", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(0, 8))

        self._control_center_nav_buttons = {}
        sections = [
            ("main", "Основное"),
            ("voice", "Центр голоса"),
            ("apps", "Приложения"),
            ("diagnostics", "Диагностика"),
            ("updates", "Релиз"),
            ("system", "Система"),
        ]
        for key, label_text in sections:
            btn = tk.Button(
                nav,
                text=label_text,
                command=lambda k=key: self._show_control_center_section(k),
                anchor="w",
                bg=Theme.BUTTON_BG,
                fg=Theme.FG,
                relief="flat",
                padx=14,
                pady=10,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
                cursor="hand2",
                font=("Segoe UI", 11),
            )
            btn.pack(fill="x", pady=(0, 8))
            self._bind_hover_bg(btn, role="button")
            self._control_center_nav_buttons[key] = btn
            title, status, text, pointer = self._control_center_noob_message(key)
            self._bind_control_center_guide_hint(btn, title, status, text, pointer)
        self.settings_nav_buttons = self._control_center_nav_buttons

        nav_note = tk.Label(
            side,
            text="Центр управления больше не зажимает контент: слева только разделы, справа рабочая область с настройками и диагностикой.",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 9),
            padx=12,
            pady=10,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        nav_note.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        bind_dynamic_wrap(nav_note, side, padding=30, minimum=160)
        self._control_center_nav_note = nav_note

        guide_host = tk.Frame(side, bg=Theme.CARD_BG, width=232, height=252)
        guide_host.pack_propagate(False)
        self._control_center_guide_host = guide_host
        noob_asset = (
            self.assets.get("noob_sidebar")
            or self.assets.get("noob_settings")
            or self.assets.get("noob2")
            or self.assets.get("noob")
        )
        noob_image = noob_asset if isinstance(noob_asset, ImageTk.PhotoImage) else None
        self._control_center_guide = GuideNoobPanel(
            guide_host,
            image=noob_image,
            title="Нубик JARVIS",
            on_click=self._show_control_center_guide_popup,
            variant="settings",
        )
        guide_host.pack(fill="x", padx=12, pady=(0, 12), before=nav_note)
        title, status, text, pointer = self._control_center_noob_message("main")
        self._set_control_center_guide_hint(title=title, status=status, text=text, pointer=pointer)

        content = tk.Frame(body, bg=Theme.BG_LIGHT, highlightbackground=Theme.BORDER, highlightthickness=1)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self._control_center_content = content

        content_canvas = tk.Canvas(content, bg=Theme.BG_LIGHT, highlightthickness=0, bd=0)
        content_scroll = ttk.Scrollbar(content, orient="vertical", command=content_canvas.yview, style="Jarvis.Vertical.TScrollbar")
        content_canvas.grid(row=0, column=0, sticky="nsew")
        content_scroll.grid(row=0, column=1, sticky="ns")
        content_inner = tk.Frame(content_canvas, bg=Theme.BG_LIGHT)
        content_inner_id = content_canvas.create_window((0, 0), window=content_inner, anchor="nw")
        content_canvas.configure(yscrollcommand=content_scroll.set)
        content_inner.bind("<Configure>", lambda _event: self._schedule_control_center_content_scroll_refresh(), add="+")
        content_canvas.bind("<Configure>", lambda _event: self._schedule_control_center_content_scroll_refresh(), add="+")
        self._register_scroll_target(content_canvas)
        self._control_center_content_canvas = content_canvas
        self._control_center_content_scroll = content_scroll
        self._control_center_content_inner = content_inner
        self._control_center_content_inner_id = content_inner_id
        self._control_center_pages = {}
        self._control_center_page_builders = {}
        self._control_center_built_pages = set()
        self._control_center_layout_signature = None
        self._control_center_prewarm_queue = []
        self._control_center_prewarm_after_id = None
        self._control_center_prewarm_running = False
        self._control_center_prewarm_done = False
        self._control_center_scroll_after_id = None
        self._control_center_scroll_signature = None
        self._control_center_scroll_top_pending = False

        def _make_page(key, builder):
            page = tk.Frame(content_inner, bg=Theme.BG_LIGHT)
            try:
                setattr(page, "_jarvis_plain_scroll_host", True)
            except Exception:
                pass
            self._control_center_pages[key] = page
            self._control_center_page_builders[key] = builder

        _make_page("main", self._create_settings_tab1)
        _make_page("voice", self._create_voice_center_page)
        _make_page("apps", self._create_settings_tab2)
        _make_page("diagnostics", self._create_diagnostic_tab)
        _make_page("updates", self._create_settings_tab4)
        _make_page("system", self._create_settings_tab5)
        self._ensure_control_center_page_built("main")

        win.bind("<Configure>", lambda _event: self._schedule_control_center_layout_refresh(), add="+")
        return win

    def open_full_settings_view(self, tab_key: Optional[str] = None, section: Optional[str] = None):
        target = self._control_center_tab_alias(section if section is not None else tab_key)
        self._hide_legacy_settings_surfaces()
        self._suspend_activation_gate_for_settings()
        self._hide_workspace_surface_for_settings()
        page = getattr(self, "embedded_settings_page", None)
        if page is not None:
            try:
                page.place_forget()
                page.pack_forget()
                page.grid_forget()
            except Exception:
                pass
        win = self._build_control_center_window()
        self._ensure_control_center_page_built(target)
        self._sync_control_center_window_to_root(win)
        self._restyle_settings_window()
        self._show_control_center_section(target)
        self._workspace_section = "settings"
        self._schedule_settings_visual_refresh()
        try:
            if isinstance(win, tk.Toplevel):
                win.deiconify()
                win.lift()
                win.focus_force()
            else:
                try:
                    if not win.winfo_manager():
                        win.pack(fill="both", expand=True)
                except tk.TclError:
                    pass
                win.lift()
                win.focus_force()
        except tk.TclError:
            pass
        try:
            win.after_idle(self._schedule_settings_visual_refresh)
        except tk.TclError:
            pass
        try:
            self._preferred_scroll_target = getattr(self, "_control_center_content_canvas", None)
        except Exception:
            pass
        try:
            win.after(850, lambda: self._schedule_control_center_prewarm(target))
        except Exception:
            pass
        if bool(getattr(self, "_startup_gate_setup", False)):
            try:
                win.after(80, lambda: getattr(self, "_settings_primary_api_entry", None).focus_set())
            except Exception:
                pass
        self.set_status("Настройки открыты", "busy")

    def close_full_settings_view(self):
        try:
            self._hide_tooltip()
        except tk.TclError:
            pass
        self._destroy_control_center_window(resume_bg=True)
        self._restore_workspace_surface_after_settings()
        self._resume_activation_gate_after_settings()
        page = getattr(self, "embedded_settings_page", None)
        if page is not None:
            try:
                page.place_forget()
                page.pack_forget()
                page.grid_forget()
            except tk.TclError:
                pass
        self._workspace_section = "chat"
        try:
            self._set_workspace_section("chat")
        except tk.TclError:
            pass
        try:
            self._preferred_scroll_target = getattr(self, "chat_canvas", None)
        except Exception:
            pass
        try:
            self._prime_after_visual_transition()
        except Exception:
            pass
        self.set_status("Готов", "ok")
        self._schedule_chat_layout_sync(scroll_to_end=True)
        self.set_status("Готов", "ok")

    def open_settings_window(self, icon=None, item=None):
        self.open_full_settings_view("main")
        return

    def _create_scrollable_settings_host(self, parent, inner_bg: Optional[str] = None):
        for child in parent.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        if bool(getattr(parent, "_jarvis_plain_scroll_host", False)):
            inner = tk.Frame(parent, bg=inner_bg or Theme.BG_LIGHT)
            inner.pack(fill="both", expand=True)
            inner.bind("<Configure>", lambda _event: self._schedule_control_center_content_scroll_refresh(), add="+")
            try:
                parent.after_idle(self._schedule_control_center_content_scroll_refresh)
            except Exception:
                pass
            return parent, getattr(self, "_control_center_content_canvas", None), inner
        host = tk.Frame(parent, bg=Theme.BG_LIGHT)
        host.pack(fill="both", expand=True)
        canvas = tk.Canvas(host, bg=Theme.BG_LIGHT, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview, style="Jarvis.Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=inner_bg or Theme.BG_LIGHT)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def _sync_scroll(_event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfigure(inner_id, width=canvas.winfo_width())
            except Exception:
                pass

        inner.bind("<Configure>", _sync_scroll, add="+")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner_id, width=e.width), add="+")
        self._register_scroll_target(canvas)
        return host, canvas, inner

    def _refresh_control_center_content_scroll(self, scroll_top: bool = False):
        canvas = getattr(self, "_control_center_content_canvas", None)
        inner_id = getattr(self, "_control_center_content_inner_id", None)
        if canvas is None or inner_id is None:
            return
        try:
            bbox = canvas.bbox("all")
        except Exception:
            bbox = None
        try:
            width = int(canvas.winfo_width() or 0)
        except Exception:
            width = 0
        signature = (width, tuple(bbox) if bbox else None)
        if not scroll_top and signature == getattr(self, "_control_center_scroll_signature", None):
            return
        self._control_center_scroll_signature = signature
        try:
            if bbox:
                canvas.configure(scrollregion=bbox)
        except Exception:
            pass
        try:
            if width > 0:
                canvas.itemconfigure(inner_id, width=width)
        except Exception:
            pass
        if scroll_top:
            try:
                canvas.yview_moveto(0.0)
            except Exception:
                pass

    def _create_settings_tab1(self, parent):
        # Вкладка "Основные" (активация, профиль, голос, микрофон)
        _, _, inner = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

        def entry_row(parent, label, value, show=None, help_text: str = ""):
            row = tk.Frame(parent, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 10))
            self._create_settings_field_header(row, label, help_text)
            var = tk.StringVar(value=value or "")
            entry = tk.Entry(
                row,
                textvariable=var,
                bg=Theme.INPUT_BG,
                fg=Theme.FG,
                insertbackground=Theme.FG,
                width=42,
                show=show or "",
                relief="flat",
                font=("Segoe UI Semibold", 12),
            )
            entry.pack(fill="x", ipady=6)
            self._setup_entry_bindings(entry)
            return var, entry

        def dropdown_row(parent, label, values, value, help_text: str = ""):
            row = tk.Frame(parent, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 10))
            self._create_settings_field_header(row, label, help_text)
            var = tk.StringVar(value=value)
            shell, button = self._create_settings_choice_control(row, var, values, font=("Segoe UI", 11))
            shell.pack(fill="x", pady=(4, 0))
            return var, button

        def slider_row(parent, label, from_, to, value, resolution, suffix="", help_text: str = ""):
            row = tk.Frame(parent, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 10))
            head = tk.Frame(row, bg=Theme.CARD_BG)
            head.pack(fill="x")
            self._create_settings_field_header(head, label, help_text)
            val_label = tk.Label(head, text="", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 11))
            val_label.pack(side="right")
            var = tk.DoubleVar(value=value)
            scale = tk.Scale(row, from_=from_, to=to, orient="horizontal", resolution=resolution, variable=var,
                             showvalue=False, bg=Theme.CARD_BG, fg=Theme.FG, troughcolor=Theme.BUTTON_BG, highlightthickness=0,
                             relief="flat", activebackground=Theme.ACCENT, length=620,
                             command=lambda _v: val_label.config(text=f"{var.get():.0f}{suffix}" if resolution >= 1 else f"{var.get():.2f}{suffix}"))
            scale.pack(fill="x", pady=(6, 0))
            self._bind_selector_wheel_guard(scale)
            val_label.config(text=f"{var.get():.0f}{suffix}" if resolution >= 1 else f"{var.get():.2f}{suffix}")
            return var, scale, val_label

        def flag_row(parent, label: str, variable, help_text: str = ""):
            row = tk.Frame(parent, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 6))
            check = tk.Checkbutton(row, text=label, variable=variable, **check_kwargs)
            check.pack(side="left", anchor="w")
            if str(help_text or "").strip():
                badge = self._make_settings_help_badge(row, help_text)
                badge.pack(side="right")
            return check

        check_kwargs = {
            "bg": Theme.CARD_BG,
            "fg": Theme.FG,
            "selectcolor": Theme.INPUT_BG,
            "activebackground": Theme.CARD_BG,
            "activeforeground": Theme.FG,
            "font": ("Segoe UI", 10),
        }

        # Секция
        access = tk.Frame(inner, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        access.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(access, text="Активация, профиль и безопасность", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=14, pady=(12,0))
        body = tk.Frame(access, bg=Theme.CARD_BG)
        body.pack(fill="x", padx=14, pady=10)

        create_note_box(
            body,
            "Здесь собраны только самые важные вещи: активация, ключи, профиль пользователя, мозг JARVIS, режимы безопасности и базовое поведение окна.",
            tone="soft",
        )
        groq_var, groq_entry = entry_row(body, "Ключ Groq API", CONFIG_MGR.get_api_key(), show="•", help_text="Главный ключ для мозга JARVIS. Без него чат и часть голосовых функций не смогут обращаться к ИИ.")
        self._settings_primary_api_entry = groq_entry
        login_var, _ = entry_row(body, "Логин пользователя", CONFIG_MGR.get_user_login(), help_text="Техническое имя профиля. Используется в конфиге, логах и некоторых интеграциях.")
        user_name_var, _ = entry_row(body, "Имя пользователя", CONFIG_MGR.get_user_name(), help_text="Как JARVIS будет обращаться к вам в чате, озвучке и подсказках.")

        avatar_quick = tk.Frame(body, bg=Theme.CARD_BG)
        avatar_quick.pack(fill="x", pady=(0, 10))
        self._create_settings_field_header(avatar_quick, "Аватар пользователя", "Быстрый выбор картинки для профиля пользователя в чате и на главном экране.")
        avatar_quick_actions = tk.Frame(avatar_quick, bg=Theme.CARD_BG)
        avatar_quick_actions.pack(anchor="w", pady=(4, 0))

        def pick_avatar_quick():
            path = filedialog.askopenfilename(
                title="Выберите аватар",
                filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("All files", "*.*")],
                parent=self._settings_dialog_parent(),
            )
            if not path:
                return
            CONFIG_MGR.set_user_avatar_path(path)
            self.load_assets()
            self._refresh_chat_theme()
            self.set_status_temp("Аватар обновлён", "ok")

        def clear_avatar_quick():
            CONFIG_MGR.set_user_avatar_path("")
            self.load_assets()
            self._refresh_chat_theme()
            self.set_status_temp("Аватар сброшен", "ok")

        tk.Button(avatar_quick_actions, text="Выбрать аватар", command=pick_avatar_quick, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8, cursor="hand2").pack(side="left")
        tk.Button(avatar_quick_actions, text="Сбросить", command=clear_avatar_quick, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8, cursor="hand2").pack(side="left", padx=(8, 0))

        tg_token_var, _ = entry_row(body, "Токен Telegram-бота", CONFIG_MGR.get_telegram_token(), show="•", help_text="Нужен только если хотите управлять JARVIS через Telegram-бота.")
        tg_id_var, _ = entry_row(body, "ID пользователя Telegram", str(CONFIG_MGR.get_telegram_user_id() or ""), help_text="Ваш числовой Telegram ID. По нему JARVIS поймёт, кому разрешено писать боту.")
        model_items = [
            ("Groq Compound Mini — рекомендуемый баланс для JARVIS", "groq/compound-mini"),
            ("Llama 3.3 70B — тяжелее, но мощнее", "llama-3.3-70b-versatile"),
            ("Llama 3.1 8B — быстрый fallback", "llama-3.1-8b-instant"),
            ("Qwen3 32B — альтернативный вариант", "qwen/qwen3-32b"),
        ]
        ai_simple_labels = bool(CONFIG_MGR.get_ai_simple_labels())
        current_model = str(CONFIG_MGR.get_model() or DEFAULT_CHAT_MODEL).strip()
        current_model_label = next((lbl for lbl, key in model_items if key == current_model), model_items[0][0])
        model_var, model_selector = dropdown_row(body, "Мозг JARVIS" if ai_simple_labels else "Модель ИИ", [x[0] for x in model_items], current_model_label, help_text="Главная модель для чата и команд. Compound Mini сейчас оптимален для повседневной работы.")
        self._settings_model_var = model_var
        self._settings_model_selector = model_selector
        temperature_var, _, _ = slider_row(
            body,
            "Строгость ответов" if ai_simple_labels else "Температура ИИ",
            0.0,
            0.6,
            float(CONFIG_MGR.get_temperature()),
            0.01,
            "",
            help_text="Ниже значение — спокойнее и точнее ответы. Выше значение — свободнее стиль, но больше риск лишней фантазии.",
        )
        max_tokens_var, _, _ = slider_row(
            body,
            "Длина ответа" if ai_simple_labels else "Лимит ответа ИИ",
            120,
            600,
            float(CONFIG_MGR.get_max_tokens()),
            1,
            " tok",
            help_text="Ограничивает максимальную длину ответа. На ум модели не влияет, только на развернутость текста.",
        )
        create_note_box(
            body,
            "Compound Mini подойдет почти всем. Это основной мозг для повседневных команд, чата и объяснений.",
            tone="soft",
        )
        create_note_box(
            body,
            "Строгость ответов: ближе к 0 — отвечает стабильнее и меньше фантазирует. Длина ответа: влияет только на развернутость, а не на ум приложения.",
            tone="soft",
        )

        flags = tk.Frame(body, bg=Theme.CARD_BG)
        flags.pack(fill="x", pady=5)
        auto_update_var = tk.BooleanVar(value=CONFIG_MGR.get_auto_update())
        single_user_var = tk.BooleanVar(value=CONFIG_MGR.get_single_user_mode())
        autostart_var = tk.BooleanVar(value=CONFIG_MGR.get_autostart())
        active_listening_var = tk.BooleanVar(value=CONFIG_MGR.get_active_listening_enabled())
        initial_active_listening = [bool(CONFIG_MGR.get_active_listening_enabled())]
        free_chat_mode_var = tk.BooleanVar(value=CONFIG_MGR.get_free_chat_mode())
        wake_word_boost_var = tk.BooleanVar(value=CONFIG_MGR.get_wake_word_boost_enabled())
        safe_mode_var = tk.BooleanVar(value=CONFIG_MGR.get_safe_mode_enabled())
        flag_row(flags, "Автообновление", auto_update_var, "JARVIS будет сам проверять новые версии и предлагать обновиться.")
        flag_row(flags, "Режим одного пользователя", single_user_var, "Ограничивает доступ под одного основного пользователя и снижает риск чужих команд.")
        flag_row(flags, "Автозапуск Windows", autostart_var, "Приложение будет запускаться вместе с Windows.")
        flag_row(flags, "Активное прослушивание по слову «Джарвис»", active_listening_var, "JARVIS постоянно ждёт слово активации. Удобно, но требует стабильного микрофона и аккуратного порога.")
        flag_row(flags, "Усилить чувствительность слова активации", wake_word_boost_var, "Помогает, если слово «Джарвис» слышно только очень близко к микрофону.")
        flag_row(flags, "Свободный стиль ответов", free_chat_mode_var, "Разрешает ИИ отвечать менее сухо и формально.")
        flag_row(flags, "Безопасный режим при старте", safe_mode_var, "Стартует без части фоновых сервисов. Полезно, если приложение падает, дёргается или странно ведёт себя на запуске.")
        tk.Label(
            flags,
            text="Усиление слова активации помогает, если «Джарвис» слышно только вплотную в микрофон. Безопасный режим урезает фоновые сервисы и лучше подходит для диагностики.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=620,
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(4, 0))

        theme_items = [("Тёмная", "dark"), ("Светлая", "light")]
        current_theme = str(CONFIG_MGR.get_theme_mode() or "dark").strip().lower()
        if current_theme not in {"dark", "light"}:
            current_theme = "dark"
        current_theme_label = next((lbl for lbl, val in theme_items if val == current_theme), theme_items[0][0])
        theme_var, theme_selector = dropdown_row(body, "Тема интерфейса", [x[0] for x in theme_items], current_theme_label, help_text="Общий цветовой режим приложения.")
        density_items = [("Комфортный — больше воздуха", "comfortable"), ("Компактный — плотнее", "compact")]
        current_density = str(CONFIG_MGR.get_ui_density() or "comfortable").strip().lower()
        current_density_label = next((lbl for lbl, val in density_items if val == current_density), density_items[0][0])
        density_var, density_selector = dropdown_row(body, "Плотность интерфейса", [x[0] for x in density_items], current_density_label, help_text="Влияет на воздух между блоками. Комфортный режим лучше читается, компактный помещает больше элементов.")
        release_channel_items = [("Стабильный — официальный релиз", "stable"), ("Бета — тестовый канал", "beta")]
        current_release_channel = str(CONFIG_MGR.get_release_channel() or "stable").strip().lower()
        current_release_channel_label = next((lbl for lbl, val in release_channel_items if val == current_release_channel), release_channel_items[0][0])
        release_channel_var, release_selector = dropdown_row(body, "Канал обновлений", [x[0] for x in release_channel_items], current_release_channel_label, help_text="Стабильный канал безопаснее. Бета нужен для ранней проверки новых функций.")
        close_behavior_items = [("Закрывать приложение полностью", "exit"), ("Убирать в трей", "tray")]
        current_close_behavior = str(CONFIG_MGR.get_close_behavior() or "exit").strip().lower()
        current_close_behavior_label = next((lbl for lbl, val in close_behavior_items if val == current_close_behavior), close_behavior_items[0][0])
        close_behavior_var, close_selector = dropdown_row(body, "Поведение при закрытии окна", [x[0] for x in close_behavior_items], current_close_behavior_label, help_text="Определяет, закрывается ли JARVIS полностью или прячется в трей.")
        self._settings_theme_var = theme_var
        self._settings_theme_selector = theme_selector
        self._settings_density_var = density_var
        self._settings_density_selector = density_selector
        self._settings_release_channel_var = release_channel_var
        self._settings_release_channel_selector = release_selector
        self._settings_close_behavior_var = close_behavior_var
        self._settings_close_behavior_selector = close_selector
        create_note_box(
            body,
            "По умолчанию безопаснее завершать приложение полностью. Режим трея нужен только если вы сознательно хотите оставлять JARVIS жить в фоне после закрытия окна.",
            tone="soft",
        )
        ui_scale_var, _, _ = slider_row(body, "Масштаб интерфейса", 90, 150, float(CONFIG_MGR.get_ui_scale_percent()), 1, "%", help_text="Увеличивает или уменьшает общий размер интерфейса. Полезно, если текст кажется слишком мелким.")

        bg_self_check_var = tk.BooleanVar(value=CONFIG_MGR.get_background_self_check())
        self_learning_var = tk.BooleanVar(value=CONFIG_MGR.get_self_learning_enabled())
        focus_mode_var = tk.BooleanVar(value=CONFIG_MGR.get_focus_mode_enabled())
        helper_guides_var = tk.BooleanVar(value=CONFIG_MGR.get_helper_guides_enabled())
        dpi_adaptation_var = tk.BooleanVar(value=CONFIG_MGR.get_dpi_adaptation_enabled())
        ai_simple_labels_var = tk.BooleanVar(value=CONFIG_MGR.get_ai_simple_labels())
        flag_row(flags, "Внутренний поиск ошибок по расписанию", bg_self_check_var, "Периодически прогоняет внутреннюю самопроверку и пишет о найденных проблемах.")
        flag_row(flags, "Самообучение на выполненных командах", self_learning_var, "Позволяет JARVIS учитывать историю удачных действий и адаптировать поведение.")
        flag_row(flags, "Фокус-режим по кнопке", focus_mode_var, "В узком и спокойном режиме убирает лишние панели и оставляет только разговор.")
        flag_row(flags, "Помощники и визуальные подсказки", helper_guides_var, "Показывает Нубика, контекстные советы и дополнительные объяснения по интерфейсу.")
        flag_row(flags, "Авто-адаптация под DPI и масштаб", dpi_adaptation_var, "Ставит более безопасный размер интерфейса на мониторах с высоким масштабом Windows.")
        flag_row(flags, "Объяснять ИИ простым языком", ai_simple_labels_var, "Меняет технические названия вроде «температура» на более понятные человеческие подписи.")
        self_check_interval_var, _ = entry_row(body, "Интервал фоновой диагностики (мин)", str(CONFIG_MGR.get_self_check_interval_min()), help_text="Как часто запускать внутреннюю самопроверку в фоне.")

        # Аудио секция
        audio = tk.Frame(inner, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        audio.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(audio, text="Микрофон, слышимость и озвучка", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=14, pady=(12,0))
        tk.Label(
            audio,
            text="Показываем только основные устройства. Системные и битые варианты скрыты, но сохранённое устройство не потеряется.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=14, pady=(2, 8))
        audio_body = tk.Frame(audio, bg=Theme.CARD_BG)
        audio_body.pack(fill="x", padx=14, pady=10)
        device_col = tk.Frame(audio_body, bg=Theme.CARD_BG)
        device_col.pack(side="left", fill="both", expand=True, padx=(0, 10))
        voice_col = tk.Frame(audio_body, bg=Theme.CARD_BG)
        voice_col.pack(side="left", fill="both", expand=True)

        mic_index_map = {}
        mic_pairs = self._microphone_names_for_settings(self._get_microphone_devices(refresh=True))
        mic_values = []
        for idx, name in mic_pairs:
            label = name
            if label in mic_index_map and idx is not None:
                label = f"{name} [#{idx}]"
            mic_values.append(label)
            mic_index_map[label] = idx
        if not mic_values:
            mic_values = ["(микрофон не найден)"]
        mic_index = CONFIG_MGR.get_mic_device_index()
        mic_value = ""
        for label, idx in mic_index_map.items():
            if idx == mic_index:
                mic_value = label
                break
        if not mic_value and mic_values:
            mic_value = mic_values[0]
        mic_var, mic_selector = dropdown_row(device_col, "Микрофон", mic_values, mic_value, help_text="Основное устройство, из которого JARVIS слушает голос.")
        self._settings_mic_var = mic_var
        self._settings_mic_selector = mic_selector

        output_option_map = {}
        output_values = []
        for idx, label in self._output_options_for_settings():
            output_values.append(label)
            output_option_map[label] = idx
        if not output_values:
            output_values = ["(вывод звука не найден)"]
        output_selected_idx = CONFIG_MGR.get_output_device_index()
        output_selected = ""
        for label, idx in output_option_map.items():
            if idx == output_selected_idx:
                output_selected = label
                break
        if not output_selected and not CONFIG_MGR.get_output_device_name().strip():
            output_selected = output_values[0]
        if not output_selected and output_values:
            output_selected = output_values[0]
        output_var, output_selector = dropdown_row(device_col, "Вывод звука", output_values, output_selected, help_text="Куда воспроизводить ответы, тесты и озвучку.")
        self._settings_output_var = output_var
        self._settings_output_selector = output_selector
        mic_test_status = tk.StringVar(value="Готов к проверке")
        tk.Label(device_col, textvariable=mic_test_status, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY).pack(anchor="w", pady=(5,0))
        tk.Button(
            device_col,
            text="Проверить микрофон",
            command=lambda: self.test_microphone_device(callback=lambda ok, msg: mic_test_status.set(msg)),
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
        ).pack(anchor="w", pady=(8,0))

        voice_values = self._voice_names()
        voice_value = self._selected_voice_label()
        voice_var, voice_selector = dropdown_row(voice_col, "Голос Windows", voice_values or ["(голоса не найдены)"], voice_value or (voice_values[0] if voice_values else ""), help_text="Системный голос для оффлайн-озвучки Windows.")
        self._settings_voice_var = voice_var
        self._settings_voice_selector = voice_selector
        rate_var, _, _ = slider_row(voice_col, "Скорость голоса", 150, 350, float(CONFIG_MGR.get_voice_rate()), 1, " символов/мин", help_text="Скорость, с которой JARVIS произносит текст.")
        volume_var, _, _ = slider_row(voice_col, "Громкость", 0.2, 1.0, float(CONFIG_MGR.get_voice_volume()), 0.01, "", help_text="Громкость озвучки JARVIS.")

        tts_provider_items = [
            ("pyttsx3 — оффлайн / Windows", "pyttsx3"),
            ("Edge-TTS — онлайн / самый быстрый", "edge-tts"),
            ("ElevenLabs — онлайн / максимум качества", "elevenlabs"),
        ]
        current_tts_provider = CONFIG_MGR.get_tts_provider()
        current_tts_provider_label = next((lbl for lbl, key in tts_provider_items if key == current_tts_provider), tts_provider_items[0][0])
        tts_provider_var, tts_provider_selector = dropdown_row(voice_col, "Движок озвучки", [x[0] for x in tts_provider_items], current_tts_provider_label, help_text="Выбор между оффлайн-озвучкой Windows и онлайн-провайдерами с более живым голосом.")
        self._settings_tts_provider_var = tts_provider_var
        self._settings_tts_provider_selector = tts_provider_selector
        tts_adv_toggle_row = tk.Frame(voice_col, bg=Theme.CARD_BG)
        tts_adv_toggle_row.pack(fill="x", pady=(0, 8))
        tts_adv_open = [False]
        tts_adv_wrap = tk.Frame(voice_col, bg=Theme.CARD_BG)
        edge_voice_var, _ = entry_row(tts_adv_wrap, "Голос Edge-TTS", CONFIG_MGR.get_edge_tts_voice(), help_text="Точное имя голоса Edge-TTS. Нужен только если используете Edge-TTS.")
        eleven_key_var, _ = entry_row(tts_adv_wrap, "API-ключ ElevenLabs", CONFIG_MGR.get_elevenlabs_api_key(), show="*", help_text="Секретный ключ ElevenLabs для онлайн-озвучки.")
        eleven_voice_var, _ = entry_row(tts_adv_wrap, "ID голоса ElevenLabs", CONFIG_MGR.get_elevenlabs_voice_id(), help_text="Идентификатор конкретного голоса в ElevenLabs.")
        eleven_model_var, _ = entry_row(tts_adv_wrap, "Модель ElevenLabs", CONFIG_MGR.get_elevenlabs_model_id(), help_text="Модель синтеза речи ElevenLabs. Можно оставить текущую рекомендацию по умолчанию.")
        tk.Label(
            tts_adv_wrap,
            text="Для ElevenLabs обязательны API-ключ и ID голоса.\nРекомендация: eleven_flash_v2_5 для минимальной задержки, eleven_v3 для максимальной выразительности.\nЕсли ключи пустые — будет авто-переход на оффлайн pyttsx3.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=360,
        ).pack(anchor="w", pady=(0, 6))

        tts_adv_btn = tk.Button(
            tts_adv_toggle_row,
            text="Показать расширенные TTS настройки",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            relief="flat",
            padx=10,
            pady=7,
            cursor="hand2",
        )
        tts_adv_btn.pack(anchor="w")

        def toggle_tts_adv():
            tts_adv_open[0] = not tts_adv_open[0]
            if tts_adv_open[0]:
                tts_adv_wrap.pack(fill="x", pady=(0, 6))
                tts_adv_btn.config(text="Скрыть расширенные TTS настройки")
            else:
                tts_adv_wrap.pack_forget()
                tts_adv_btn.config(text="Показать расширенные TTS настройки")

        tts_adv_btn.configure(command=toggle_tts_adv)

        listening_items = [
            ("1 - Базовый", "normal"),
            ("2 - Усиленный", "boost"),
            ("3 - Максимальный", "aggressive"),
        ]
        current_listening = CONFIG_MGR.get_listening_profile()
        initial_listening_profile = [current_listening]
        current_listening_label = next((lbl for lbl, key in listening_items if key == current_listening), listening_items[0][0])
        listening_var, listening_selector = dropdown_row(voice_col, "Восприятие/слышимость", [x[0] for x in listening_items], current_listening_label, help_text="Насколько агрессивно JARVIS пытается услышать и поймать голос. Чем выше, тем чувствительнее.")
        self._settings_listening_var = listening_var
        self._settings_listening_selector = listening_selector
        listening_warn_var = tk.StringVar(value="")
        tk.Label(voice_col, textvariable=listening_warn_var, bg=Theme.CARD_BG, fg=Theme.STATUS_WARN, justify="left", wraplength=330).pack(anchor="w", pady=(2, 4))

        def update_listening_warning(*_):
            selected_label = listening_var.get().strip()
            selected_key = next((key for lbl, key in listening_items if lbl == selected_label), "normal")
            if selected_key in {"boost", "aggressive"}:
                listening_warn_var.set("⚠️ Режимы 2 и 3 агрессивнее: они быстрее реагируют, но могут ловить фон, шумы и чужие голоса.")
            else:
                listening_warn_var.set("Базовый режим самый безопасный: меньше ложных срабатываний и чище захват фразы.")

        listening_var.trace_add("write", update_listening_warning)
        update_listening_warning()
        device_profile_items = [
            ("Автоопределение", "auto"),
            ("Гарнитура", "headset"),
            ("USB-микрофон", "usb_mic"),
            ("Встроенный / вебкамера", "built_in"),
            ("Универсальный", "default"),
        ]
        current_device_profile = str(CONFIG_MGR.get_device_profile_mode() or "auto").strip().lower()
        current_device_profile_label = next((lbl for lbl, key in device_profile_items if key == current_device_profile), device_profile_items[0][0])
        device_profile_var, device_profile_selector = dropdown_row(voice_col, "Профиль устройства", [x[0] for x in device_profile_items], current_device_profile_label, help_text="Подсказывает JARVIS, какой тип микрофона используется, чтобы лучше подстроить чувствительность.")
        self._settings_device_profile_var = device_profile_var
        self._settings_device_profile_selector = device_profile_selector
        noise_suppression_var = tk.BooleanVar(value=CONFIG_MGR.get_noise_suppression_enabled())
        vad_var = tk.BooleanVar(value=CONFIG_MGR.get_vad_enabled())
        flag_row(voice_col, "Шумоподавление", noise_suppression_var, "Пытается ослабить постоянный фоновый шум: вентилятор, улицу, гул комнаты.")
        flag_row(voice_col, "VAD / отсев тишины", vad_var, "Отсекает пустые участки без речи, чтобы меньше цеплять тишину и мусор.")
        create_note_box(
            voice_col,
            "Автоопределение само подбирает поведение под гарнитуру, USB-микрофон или встроенное устройство. VAD и шумоподавление помогают не цеплять лишний фон.",
            tone="soft",
        )

        # Кнопка сохранения внизу вкладки
        def save_tab1():
            try:
                notices = []
                notice_tone = "ok"
                api_key = groq_var.get().strip()
                startup_activation = bool(getattr(self, "_startup_gate_setup", False))
                if startup_activation and not api_key:
                    self.set_status("Нужен API ключ", "warn")
                    try:
                        groq_entry.focus_set()
                    except Exception:
                        pass
                    self._settings_toast("Введите Groq API ключ, чтобы открыть чат", "warn")
                    return
                try:
                    tg_id = int(tg_id_var.get().strip()) if tg_id_var.get().strip() else 0
                except Exception:
                    tg_id = 0
                def _theme_key_from_label(raw_value: str, fallback: str) -> str:
                    txt = str(raw_value or "").strip().lower()
                    if txt in {"light", "светлая"} or "свет" in txt:
                        return "light"
                    if txt in {"dark", "тёмная", "темная"} or "тем" in txt:
                        return "dark"
                    return fallback

                def _listening_key_from_label(raw_value: str, fallback: str = "normal") -> str:
                    txt = str(raw_value or "").strip().lower()
                    if txt.startswith("1") or "сейчас" in txt or "normal" in txt:
                        return "normal"
                    if txt.startswith("3") or "еще" in txt or "ещё" in txt or "aggressive" in txt:
                        return "aggressive"
                    if txt.startswith("2") or "усилен" in txt or "boost" in txt:
                        return "boost"
                    return fallback

                def _simple_choice(raw_value: str, options, fallback: str):
                    txt = str(raw_value or "").strip().lower()
                    for label, key in options:
                        if txt == str(label).strip().lower() or txt == str(key).strip().lower():
                            return key
                    return fallback

                selected_theme_label = theme_var.get().strip()
                selected_theme_key = _theme_key_from_label(selected_theme_label, current_theme)
                selected_density_key = _simple_choice(density_var.get().strip(), density_items, current_density)
                selected_release_channel = _simple_choice(release_channel_var.get().strip(), release_channel_items, current_release_channel)
                selected_close_behavior = _simple_choice(close_behavior_var.get().strip(), close_behavior_items, current_close_behavior)
                selected_model_label = model_var.get().strip()
                selected_model_key = next((key for lbl, key in model_items if lbl == selected_model_label), DEFAULT_CHAT_MODEL)
                selected_ui_scale_percent = int(ui_scale_var.get())
                selected_dpi_adaptation = bool(dpi_adaptation_var.get())
                selected_ai_simple_labels = bool(ai_simple_labels_var.get())
                try:
                    interval_min = int(self_check_interval_var.get().strip() or "10")
                except Exception:
                    interval_min = 10

                # Применение микрофона
                selected = mic_var.get().strip()
                mic_idx = None
                mic_name = ""
                mic_signature = ""
                if selected in mic_index_map:
                    mic_idx = mic_index_map[selected]
                    selected_mic_item = _get_audio_device_entry(mic_idx, refresh=False)
                    if selected_mic_item is not None:
                        mic_name = _expand_audio_device_name(selected_mic_item.get("name"), "input")
                        mic_signature = str(selected_mic_item.get("signature") or "").strip()
                elif selected:
                    marker = re.search(r"\[#(\d+)\]\s*$", selected)
                    if marker:
                        mic_idx = int(marker.group(1))
                        mic_name = re.sub(r"\s*\[#\d+\]\s*$", "", selected).strip()
                # Вывод звука
                out_sel = output_var.get().strip()
                output_idx = output_option_map.get(out_sel)
                output_name = ""
                output_signature = ""
                if output_idx is not None:
                    selected_output_item = _get_audio_device_entry(output_idx, refresh=False)
                    if selected_output_item is not None:
                        output_name = _expand_audio_device_name(selected_output_item.get("name"), "output")
                        output_signature = str(selected_output_item.get("signature") or "").strip()
                # Голос
                voice_index = CONFIG_MGR.get_voice_index()
                selected_voice = voice_var.get().strip()
                if selected_voice and voice_values and selected_voice in voice_values:
                    voice_index = voice_values.index(selected_voice)
                selected_listening_label = listening_var.get().strip()
                selected_listening_key = _listening_key_from_label(selected_listening_label, initial_listening_profile[0] or "normal")
                selected_device_profile = _simple_choice(device_profile_var.get().strip(), device_profile_items, current_device_profile)
                listening_changed = selected_listening_key != initial_listening_profile[0]
                selected_tts_provider_label = tts_provider_var.get().strip()
                selected_tts_provider = next((key for lbl, key in tts_provider_items if lbl == selected_tts_provider_label), "pyttsx3")
                eleven_key = eleven_key_var.get().strip()
                eleven_voice = eleven_voice_var.get().strip()
                if selected_tts_provider == "elevenlabs" and (not eleven_key or not eleven_voice):
                    selected_tts_provider = "pyttsx3"
                    notices.append("ElevenLabs отключен: не заполнены API-ключ и ID голоса, сохранён оффлайн-режим")
                    notice_tone = "warn"
                prev_theme_mode = str(CONFIG_MGR.get_theme_mode() or "dark").strip().lower()
                prev_theme_mode = prev_theme_mode if prev_theme_mode in {"dark", "light"} else "dark"
                prev_density_mode = str(CONFIG_MGR.get_ui_density() or "comfortable").strip().lower()
                prev_scale_percent = int(CONFIG_MGR.get_ui_scale_percent() or 100)
                prev_dpi_adaptation = bool(CONFIG_MGR.get_dpi_adaptation_enabled())
                prev_ai_simple_labels = bool(CONFIG_MGR.get_ai_simple_labels())
                previous_safe_mode = bool(getattr(self, "safe_mode", False))
                next_safe_mode = bool(safe_mode_var.get())

                CONFIG_MGR.set_many({
                    "api_key": api_key,
                    "model": selected_model_key,
                    "temperature": float(temperature_var.get()),
                    "max_tokens": int(max_tokens_var.get()),
                    "user_login": login_var.get().strip(),
                    "user_name": user_name_var.get().strip(),
                    "telegram_token": tg_token_var.get().strip(),
                    "telegram_user_id": tg_id,
                    "allowed_user_ids": [tg_id] if tg_id else [],
                    "auto_update": bool(auto_update_var.get()),
                    "update_check_on_start": True,
                    "single_user_mode": bool(single_user_var.get()),
                    "autostart": bool(autostart_var.get()),
                    "active_listening_enabled": bool(active_listening_var.get()),
                    "wake_word_boost": bool(wake_word_boost_var.get()),
                    "free_chat_mode": bool(free_chat_mode_var.get()),
                    "safe_mode_enabled": next_safe_mode,
                    "theme_mode": selected_theme_key,
                    "ui_density": selected_density_key,
                    "focus_mode_enabled": bool(focus_mode_var.get()),
                    "helper_guides_enabled": bool(helper_guides_var.get()),
                    "dpi_adaptation_enabled": selected_dpi_adaptation,
                    "ui_scale_percent": selected_ui_scale_percent,
                    "release_channel": selected_release_channel,
                    "close_behavior": selected_close_behavior,
                    "ai_simple_labels": selected_ai_simple_labels,
                    "background_self_check": bool(bg_self_check_var.get()),
                    "self_learning_enabled": bool(self_learning_var.get()),
                    "self_check_interval_min": interval_min,
                    "mic_device_index": mic_idx,
                    "mic_device_name": mic_name,
                    "mic_device_signature": mic_signature,
                    "output_device_index": output_idx,
                    "output_device_name": output_name,
                    "output_device_signature": output_signature,
                    "voice_index": int(voice_index),
                    "voice_rate": int(rate_var.get()),
                    "voice_volume": float(volume_var.get()),
                    "tts_provider": selected_tts_provider,
                    "edge_tts_voice": edge_voice_var.get().strip(),
                    "elevenlabs_api_key": eleven_key,
                    "elevenlabs_voice_id": eleven_voice,
                    "elevenlabs_model_id": eleven_model_var.get().strip(),
                    "listening_profile": selected_listening_key,
                    "device_profile_mode": selected_device_profile,
                    "noise_suppression_enabled": bool(noise_suppression_var.get()),
                    "vad_enabled": bool(vad_var.get()),
                })

                if listening_changed and selected_listening_key in {"boost", "aggressive"}:
                    notices.append("Усиленный режим слышимости может улавливать шумы и постороннюю речь")
                    notice_tone = "warn"
                initial_listening_profile[0] = selected_listening_key
                if initial_active_listening[0] and not bool(active_listening_var.get()):
                    notices.append("Активное прослушивание отключено: вызов по слову «Джарвис» больше не работает")
                    notice_tone = "warn"
                initial_active_listening[0] = bool(active_listening_var.get())
                self.safe_mode = next_safe_mode
                self._set_bg_animation_paused(next_safe_mode, reason="safe_mode")
                if not next_safe_mode and not getattr(self, "_bg_anim_started", False):
                    self.start_bg_anim()
                if previous_safe_mode != next_safe_mode:
                    notices.append("Режим запуска обновлён: часть служб перестроилась сразу, но полный режим лучше проверить после перезапуска")

                ui_rebuild_required = any((
                    prev_theme_mode != str(selected_theme_key or "").strip().lower(),
                    prev_density_mode != str(selected_density_key or "").strip().lower(),
                    prev_scale_percent != selected_ui_scale_percent,
                    prev_dpi_adaptation != selected_dpi_adaptation,
                    prev_ai_simple_labels != selected_ai_simple_labels,
                ))
                reopen_control_center_section = None
                if ui_rebuild_required and not startup_activation and self._is_full_settings_open():
                    reopen_control_center_section = str(getattr(self, "current_settings_subsection", "main") or "main")
                    self._destroy_control_center_window(resume_bg=False)

                self._voice_device_refresh_requested = True
                self.reload_services()
                self._apply_dpi_scaling()
                self.apply_theme_runtime()
                if ui_rebuild_required:
                    try:
                        self._rebuild_workspace_shell_v2()
                    except tk.TclError as exc:
                        logger.debug("Workspace rebuild warning: %s", exc)
                if hasattr(self, "refresh_workspace_layout_mode"):
                    self.refresh_workspace_layout_mode()
                if hasattr(self, "_update_guide_context"):
                    self._update_guide_context("voice")
                self.apply_autostart()
                self.refresh_mic_status_label()
                self.refresh_output_status_label()
                self.refresh_tts_status_label()
                if startup_activation:
                    CONFIG_MGR.set_first_run_done()
                    self._startup_gate_setup = False
                    self.close_full_settings_view()
                    if not self.safe_mode and not getattr(self, "_bg_anim_started", False):
                        self.start_bg_anim()
                    self._start_runtime_services()
                    if notices:
                        self._settings_toast(notices[0], notice_tone)
                    else:
                        self.set_status("Готов", "ok")
                    return
                if reopen_control_center_section:
                    self._schedule_control_center_reopen(reopen_control_center_section)
                    self._settings_toast(
                        notices[0] if notices else "Настройки сохранены, интерфейс пересобран",
                        notice_tone if notices else "ok",
                    )
                    return
                try:
                    self._schedule_settings_visual_refresh()
                except Exception:
                    pass
                self._settings_toast(notices[0] if notices else "Настройки сохранены", notice_tone if notices else "ok")
            except Exception as e:
                self.report_error("Ошибка сохранения", e, speak=False)
                self._settings_toast(f"Ошибка сохранения: {e}", "error")

        self._settings_tab1_save_callback = save_tab1
        tk.Button(inner, text="Сохранить изменения", command=save_tab1, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=10, cursor="hand2").pack(anchor="w", padx=18, pady=(0, 14))

    def _create_settings_tab2(self, parent):
        # Вкладка "Приложения" (пути, кастомные приложения, игры лаунчеров)
        _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)
        frame = tk.Frame(body, bg=Theme.BG_LIGHT)
        frame.pack(fill="x", padx=18, pady=12)

        def browse(var):
            filename = filedialog.askopenfilename(
                title="Выберите исполняемый файл",
                filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            )
            if filename:
                var.set(filename)

        paths_card = tk.Frame(frame, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        paths_card.pack(fill="x", pady=(0, 10))
        tk.Label(paths_card, text="Пути к приложениям", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))

        labels = [
            ("Яндекс.Музыка", "yandex_music_path"),
            ("Steam", "steam_path"),
            ("Epic Launcher", "epic_launcher_path"),
            ("Discord", "discord_candidates", True),
            ("Telegram Desktop", "telegram_desktop_path"),
        ]

        vars_dict = {}
        for lbl, key, *rest in labels:
            row = tk.Frame(paths_card, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=4, padx=12)
            tk.Label(row, text=lbl, bg=Theme.CARD_BG, fg=Theme.FG, width=16, anchor="w").pack(side="left")
            var = tk.StringVar()
            if key == "discord_candidates":
                val = CONFIG_MGR.get(key, [""])[0] if CONFIG_MGR.get(key) else ""
            else:
                val = CONFIG_MGR.get(key, "")
            var.set(val)
            entry = tk.Entry(row, textvariable=var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, width=42, relief="flat")
            entry.pack(side="left", fill="x", expand=True, padx=6, ipady=6)
            self._setup_entry_bindings(entry)
            tk.Button(row, text="Обзор", command=lambda v=var: browse(v), bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat").pack(side="right")
            vars_dict[key] = var

        custom_card = tk.Frame(frame, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        custom_card.pack(fill="x", pady=(0, 10))
        tk.Label(custom_card, text="Приложения и игры", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(
            custom_card,
            text="Можно добавить любые приложения. Команды: включи/запусти/закрой <название>.\nКоманды громкости работают на системном уровне.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=760,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        list_wrap = tk.Frame(custom_card, bg=Theme.CARD_BG)
        list_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        app_listbox = tk.Listbox(list_wrap, bg=Theme.INPUT_BG, fg=Theme.FG, relief="flat", selectbackground=Theme.ACCENT, height=11, bd=0, highlightthickness=0)
        app_listbox.pack(side="left", fill="both", expand=True)
        list_scroll = ttk.Scrollbar(list_wrap, command=app_listbox.yview, style="Jarvis.Vertical.TScrollbar")
        list_scroll.pack(side="right", fill="y")
        app_listbox.config(yscrollcommand=list_scroll.set)
        self._register_scroll_target(app_listbox)

        custom_apps_state = list(CONFIG_MGR.get_custom_apps() or [])
        app_index_map = []

        def refresh_app_list():
            nonlocal app_index_map
            app_index_map = []
            app_listbox.delete(0, tk.END)

            for item in custom_apps_state:
                app_listbox.insert(tk.END, f"[App] {item.get('name', '')}")
                app_index_map.append(("custom", item.get("key", "")))

            for game in CONFIG_MGR.get_launcher_games() or []:
                source = game.get("source", "launcher")
                app_listbox.insert(tk.END, f"[Game:{source}] {game.get('name', '')}")
                app_index_map.append(("launcher", game.get("key", "")))

        def add_custom_app():
            path_value = filedialog.askopenfilename(
                title="Выберите приложение",
                filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            )
            if not path_value:
                return
            default_name = os.path.splitext(os.path.basename(path_value))[0]
            name = simpledialog.askstring("Название", "Как назвать приложение в командах?", initialvalue=default_name, parent=self._settings_dialog_parent())
            if not name:
                return
            aliases_raw = simpledialog.askstring(
                "Синонимы",
                "Синонимы через запятую (необязательно):",
                initialvalue="",
                parent=self._settings_dialog_parent(),
            )
            aliases = []
            if aliases_raw:
                aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]

            key = make_dynamic_key(name, "custom")
            keys = {str(a.get("key", "")).lower() for a in custom_apps_state}
            if key in keys:
                key = f"{key}_{len(custom_apps_state) + 1}"

            custom_apps_state.append({
                "key": key,
                "name": str(name).strip(),
                "launch": path_value,
                "aliases": aliases,
                "close_exes": [os.path.basename(path_value)],
                "source": "custom",
            })
            refresh_app_list()

        def remove_selected_app():
            sel = app_listbox.curselection()
            if not sel:
                return
            idx = int(sel[0])
            if idx < 0 or idx >= len(app_index_map):
                return
            source, key = app_index_map[idx]
            if source != "custom":
                messagebox.showinfo(app_brand_name(), "Игры из лаунчеров удаляются через лаунчер. Здесь удаляются только пользовательские приложения.")
                return
            custom_apps_state[:] = [a for a in custom_apps_state if str(a.get("key", "")).lower() != str(key).lower()]
            refresh_app_list()

        def sync_games():
            try:
                self.sync_launcher_games(show_message=True)
                refresh_app_list()
            except Exception as e:
                self.report_error("Ошибка синхронизации игр", e, speak=False)

        def open_custom_actions_manifest():
            manifest_path = custom_actions_path()
            try:
                os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
                if not os.path.exists(manifest_path):
                    with open(manifest_path, "w", encoding="utf-8") as fh:
                        json.dump({"actions": custom_actions_example()}, fh, ensure_ascii=False, indent=2)
                os.startfile(manifest_path)
                self.set_status_temp("Открыл custom_actions.json", "ok")
            except Exception as e:
                self.report_error("Ошибка открытия custom_actions.json", e, speak=False)

        btn_row = tk.Frame(custom_card, bg=Theme.CARD_BG)
        btn_row.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(btn_row, text="Добавить приложение", command=add_custom_app, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10, pady=6).pack(side="left")
        tk.Button(btn_row, text="Удалить выбранное", command=remove_selected_app, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10, pady=6).pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text="Открыть custom_actions.json", command=open_custom_actions_manifest, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=10, pady=6).pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text="Подтянуть игры из лаунчеров", command=sync_games, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=10, pady=6).pack(side="right")

        refresh_app_list()

        def save_tab2():
            try:
                discord_value = vars_dict["discord_candidates"].get().strip()
                CONFIG_MGR.set_many({
                    "yandex_music_path": vars_dict["yandex_music_path"].get().strip(),
                    "steam_path": vars_dict["steam_path"].get().strip(),
                    "epic_launcher_path": vars_dict["epic_launcher_path"].get().strip(),
                    "discord_candidates": [discord_value] if discord_value else [],
                    "telegram_desktop_path": vars_dict["telegram_desktop_path"].get().strip(),
                    "custom_apps": custom_apps_state,
                })
                self.sync_launcher_games(show_message=False)
                self._settings_toast("Пути и список приложений сохранены", "ok")
            except Exception as e:
                self.report_error("Ошибка сохранения путей", e, speak=False)

        tk.Button(frame, text="Сохранить изменения", command=save_tab2, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8, cursor="hand2").pack(pady=8)

    def _scan_steam_games(self, steam_exe_path: str) -> List[Dict[str, Any]]:
        games = []
        steam_exe_path = str(steam_exe_path or "").strip()
        if not steam_exe_path:
            return games
        steam_root = os.path.dirname(steam_exe_path)
        default_library = os.path.join(steam_root, "steamapps")
        libraries = [default_library]
        libfile = os.path.join(default_library, "libraryfolders.vdf")
        if os.path.exists(libfile):
            try:
                with open(libfile, "r", encoding="utf-8", errors="ignore") as sf:
                    raw = sf.read()
                for m in re.finditer(r'"path"\\s*"([^"]+)"', raw):
                    path_value = m.group(1).replace("\\\\", "\\")
                    libraries.append(os.path.join(path_value, "steamapps"))
            except Exception as e:
                logger.warning(f"Steam library parse error: {e}")

        seen_appids = set()
        for lib in dict.fromkeys(libraries):
            if not os.path.isdir(lib):
                continue
            for manifest in glob.glob(os.path.join(lib, "appmanifest_*.acf")):
                try:
                    with open(manifest, "r", encoding="utf-8", errors="ignore") as mf:
                        raw = mf.read()
                    appid_m = re.search(r'"appid"\\s*"([^"]+)"', raw)
                    name_m = re.search(r'"name"\\s*"([^"]+)"', raw)
                    if not appid_m or not name_m:
                        continue
                    appid = appid_m.group(1).strip()
                    name = name_m.group(1).strip()
                    if not appid or not name or appid in seen_appids:
                        continue
                    seen_appids.add(appid)
                    games.append({
                        "key": make_dynamic_key(name, "steam"),
                        "name": name,
                        "launch": f"steam://rungameid/{appid}",
                        "aliases": [name],
                        "close_exes": [],
                        "source": "steam",
                    })
                except Exception:
                    continue
        return games

    def _scan_epic_games(self) -> List[Dict[str, Any]]:
        games = []
        manifests_dir = os.path.join(os.getenv("PROGRAMDATA", r"C:\\ProgramData"), "Epic", "EpicGamesLauncher", "Data", "Manifests")
        if not os.path.isdir(manifests_dir):
            return games

        for item_path in glob.glob(os.path.join(manifests_dir, "*.item")):
            try:
                with open(item_path, "r", encoding="utf-8", errors="ignore") as ef:
                    data = json.load(ef)
            except Exception:
                continue

            name = str(data.get("DisplayName", "")).strip()
            app_name = str(data.get("AppName", "")).strip()
            install_dir = str(data.get("InstallLocation", "")).strip()
            launch_exe = str(data.get("LaunchExecutable", "")).strip()
            launch_cmd = ""
            close_exes = []

            if install_dir and launch_exe:
                full_exe = os.path.join(install_dir, launch_exe)
                if os.path.exists(full_exe):
                    launch_cmd = full_exe
                    close_exes = [os.path.basename(full_exe)]
            if not launch_cmd and app_name:
                launch_cmd = f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true"

            if name and launch_cmd:
                games.append({
                    "key": make_dynamic_key(name, "epic"),
                    "name": name,
                    "launch": launch_cmd,
                    "aliases": [name, app_name] if app_name else [name],
                    "close_exes": close_exes,
                    "source": "epic",
                })
        return games

    def sync_launcher_games(self, show_message: bool = False):
        steam_games = self._scan_steam_games(CONFIG_MGR.get("steam_path", ""))
        epic_games = self._scan_epic_games()
        merged = []
        used = set()
        for game in steam_games + epic_games:
            key = str(game.get("key", "")).strip().lower()
            if not key or key in used:
                continue
            used.add(key)
            merged.append(game)
        CONFIG_MGR.set_launcher_games(merged)
        if show_message:
            self._settings_toast(f"Синхронизация завершена. Найдено игр: {len(merged)}", "ok")
        return merged

    def _create_settings_tab4(self, parent):
        # Вкладка "Обновления"
        _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)
        frame = tk.Frame(body, bg=Theme.CARD_BG)
        frame.pack(fill="x", padx=18, pady=12)

        github_var = tk.StringVar(value=DEFAULT_GITHUB_REPO)
        manifest_var = tk.StringVar(value=DEFAULT_RELEASE_API_URL)
        download_var = tk.StringVar(value=str(CONFIG_MGR.get_update_download_url() or "").strip())
        trusted_hosts_var = tk.StringVar(value=", ".join(CONFIG_MGR.get_update_trusted_hosts()))

        tk.Label(
            frame,
            text=f"Официальный канал обновлений: {DEFAULT_RELEASES_URL}\nПроверка выполняется автоматически на каждом запуске.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(frame, text="GitHub репозиторий (owner/repo)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0,3))
        github_entry = tk.Entry(frame, textvariable=github_var, bg=Theme.INPUT_BG, fg=Theme.FG, state="readonly", readonlybackground=Theme.INPUT_BG)
        github_entry.pack(fill="x", pady=(0,10))
        self._setup_entry_bindings(github_entry)
        tk.Label(frame, text="URL манифеста обновлений (JSON)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0,3))
        manifest_entry = tk.Entry(frame, textvariable=manifest_var, bg=Theme.INPUT_BG, fg=Theme.FG, state="readonly", readonlybackground=Theme.INPUT_BG)
        manifest_entry.pack(fill="x", pady=(0,10))
        self._setup_entry_bindings(manifest_entry)
        tk.Label(frame, text="Прямая ссылка на скачивание (опционально)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0,3))
        download_entry = tk.Entry(frame, textvariable=download_var, bg=Theme.INPUT_BG, fg=Theme.FG)
        download_entry.pack(fill="x", pady=(0,15))
        self._setup_entry_bindings(download_entry)
        tk.Label(frame, text="Доверенные хосты обновлений (через запятую)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0,3))
        trusted_entry = tk.Entry(frame, textvariable=trusted_hosts_var, bg=Theme.INPUT_BG, fg=Theme.FG)
        trusted_entry.pack(fill="x", pady=(0,15))
        self._setup_entry_bindings(trusted_entry)

        def save_updates():
            hosts = [h.strip().lower() for h in trusted_hosts_var.get().split(",") if h.strip()]
            default_hosts = list(dict.fromkeys((hosts or []) + list(CONFIG_MGR.default_config.get("update_trusted_hosts", []))))
            CONFIG_MGR.set_many({
                "github_repo": DEFAULT_GITHUB_REPO,
                "update_manifest_url": DEFAULT_RELEASE_API_URL,
                "update_download_url": download_var.get().strip(),
                "update_trusted_hosts": default_hosts,
                "update_check_on_start": True,
            })
            self._settings_toast("Настройки обновлений сохранены", "ok")
        tk.Button(frame, text="Сохранить настройки обновлений", command=save_updates, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(pady=(0,10))

        tk.Button(frame, text="Проверить обновления сейчас", command=self.check_for_updates_now, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(pady=5)

        publish_card = tk.Frame(frame, bg=Theme.BUTTON_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        publish_card.pack(fill="x", pady=(16, 0))
        publish_head = tk.Frame(publish_card, bg=Theme.BUTTON_BG)
        publish_head.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(
            publish_head,
            text="Публикация в 1 клик",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        tk.Label(
            publish_head,
            text=app_version_badge(),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
        ).pack(side="right")
        tk.Label(
            publish_card,
            text=f"Сборка, подготовка GitHub bundle, commit, push и tag {app_version_badge()} одной кнопкой. Используется репозиторий {DEFAULT_GITHUB_REPO}.",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=760,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        def open_publish_tools_folder():
            tools_dir = runtime_root_path("publish_tools")
            if not os.path.isdir(tools_dir):
                messagebox.showerror(app_brand_name(), f"Папка publish_tools не найдена:\n{tools_dir}")
                return
            try:
                os.startfile(tools_dir)
            except Exception as e:
                self.report_error("Ошибка открытия publish_tools", e, speak=False)

        def run_publish_one_click():
            script_path = runtime_root_path("publish_tools", "Publish-One-Click.bat")
            if not os.path.exists(script_path):
                messagebox.showerror(app_brand_name(), f"Скрипт публикации в 1 клик не найден:\n{script_path}")
                return
            if not messagebox.askyesno(
                app_brand_name(),
                "Запустить публикацию в 1 клик?\n\nЭто соберёт релиз, подготовит GitHub bundle, сделает commit, push и отправит tag в GitHub.",
            ):
                return
            try:
                os.startfile(script_path)
                self.set_status_temp("Открыл публикацию в 1 клик", "ok")
            except Exception as e:
                self.report_error("Ошибка запуска публикации в 1 клик", e, speak=False)

        publish_actions = tk.Frame(publish_card, bg=Theme.BUTTON_BG)
        publish_actions.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(
            publish_actions,
            text="Опубликовать одним кликом",
            command=run_publish_one_click,
            bg=Theme.ACCENT,
            fg=Theme.FG,
            relief="flat",
            padx=14,
            pady=9,
        ).pack(side="left")
        tk.Button(
            publish_actions,
            text="Открыть publish_tools",
            command=open_publish_tools_folder,
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            relief="flat",
            padx=14,
            pady=9,
        ).pack(side="left", padx=(8, 0))

    def _create_settings_tab5(self, parent):
        # Вкладка "Система"
        _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)
        frame = tk.Frame(body, bg=Theme.CARD_BG)
        frame.pack(fill="x", padx=18, pady=12)

        system_card = tk.Frame(frame, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        system_card.pack(fill="x", pady=(0, 10))
        tk.Label(system_card, text="Системные инструменты", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        system_note = tk.Label(
            system_card,
            text="Здесь живут служебные функции: проверка готовности, проверка релиза, экспорт диагностики и резервные копии. Домашний экран оставляем спокойным и без перегруза.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=760,
        )
        system_note.pack(fill="x", padx=12, pady=(0, 10))
        bind_dynamic_wrap(system_note, system_card, padding=28, minimum=220)
        create_action_grid(
            system_card,
            [
                {"text": "Проверка готовности", "command": self.run_readiness_master, "bg": Theme.ACCENT},
                {"text": "Проверка релиза", "command": self.run_release_lock_check},
                {"text": "Пакет поддержки", "command": self.export_diagnostics_bundle_action},
                {"text": "Резервная копия", "command": self.create_profile_backup_action},
                {"text": "Восстановить копию", "command": self.restore_profile_backup_action},
                {"text": "Набор расширений", "command": self.export_plugin_pack_action},
            ],
            columns=2,
            bg=Theme.CARD_BG,
        )

        net_card = tk.Frame(frame, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        net_card.pack(fill="x", pady=(0, 10))
        tk.Label(net_card, text="Сеть и прокси", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        proxy_var = tk.StringVar(value=CONFIG_MGR.get_proxy_url())
        proxy_entry = tk.Entry(net_card, textvariable=proxy_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG)
        proxy_entry.pack(fill="x", padx=12, pady=(0, 8), ipady=6)
        self._setup_entry_bindings(proxy_entry)

        def save_proxy():
            CONFIG_MGR.set_proxy_url(proxy_var.get().strip())
            self._apply_proxy_env_from_config()
            self.proxy_detected = self._detect_proxy_enabled()
            if self.proxy_detected:
                self._settings_toast("Прокси применен", "ok")
            else:
                self._settings_toast("Прокси отключен", "ok")

        tk.Button(net_card, text="Сохранить прокси", command=save_proxy, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(anchor="w", padx=12, pady=(0, 10))

        avatar_card = tk.Frame(frame, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        avatar_card.pack(fill="x", pady=(0, 10))
        tk.Label(avatar_card, text="Аватар пользователя", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        avatar_path_var = tk.StringVar(value=CONFIG_MGR.get_user_avatar_path())
        avatar_entry = tk.Entry(avatar_card, textvariable=avatar_path_var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG)
        avatar_entry.pack(fill="x", padx=12, pady=(0, 8), ipady=6)
        self._setup_entry_bindings(avatar_entry)

        def pick_avatar():
            path = filedialog.askopenfilename(
                title="Выберите аватар",
                filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("All files", "*.*")],
                parent=self._settings_dialog_parent(),
            )
            if path:
                avatar_path_var.set(path)

        def save_avatar():
            CONFIG_MGR.set_user_avatar_path(avatar_path_var.get().strip())
            self.load_assets()
            self._refresh_chat_theme()
            self.set_status_temp("Аватар обновлён", "ok")

        def clear_avatar():
            avatar_path_var.set("")
            CONFIG_MGR.set_user_avatar_path("")
            self.load_assets()
            self._refresh_chat_theme()
            self.set_status_temp("Аватар сброшен", "ok")

        avatar_btns = tk.Frame(avatar_card, bg=Theme.CARD_BG)
        avatar_btns.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(avatar_btns, text="Выбрать", command=pick_avatar, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left")
        tk.Button(avatar_btns, text="Применить", command=save_avatar, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))
        tk.Button(avatar_btns, text="Сбросить", command=clear_avatar, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))

        clean_card = tk.Frame(frame, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        clean_card.pack(fill="x")
        tk.Label(clean_card, text="Обслуживание", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))

        def clear_temp_cache():
            import tempfile
            removed = 0
            for path in glob.glob(os.path.join(tempfile.gettempdir(), "jarvis_tts_*")):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        removed += 1
                except Exception:
                    pass
            self.set_status_temp(f"Кэш очищен: {removed}", "ok")
            messagebox.showinfo(app_brand_name(), f"Очищено временных папок: {removed}")

        def clear_logs():
            try:
                with open(LOG_FILE, "w", encoding="utf-8") as lf:
                    lf.write("")
                self.set_status_temp("Лог очищен", "ok")
            except Exception as e:
                self.report_error("Ошибка очистки лога", e, speak=False)

        def clear_memory():
            try:
                db.clear_context()
            except Exception:
                pass
            try:
                with self.context_lock:
                    self.context_messages.clear()
            except Exception:
                pass
            self.set_status_temp("Память очищена", "ok")

        def reset_settings_only():
            if not messagebox.askyesno(app_brand_name(), "Сбросить только настройки (config.json)?"):
                return
            try:
                cfg_path = get_config_path()
                if os.path.exists(cfg_path):
                    os.remove(cfg_path)
                messagebox.showinfo(app_brand_name(), "Настройки сброшены. Перезапустите приложение.")
            except Exception as e:
                self.report_error("Ошибка сброса настроек", e, speak=False)

        actions = tk.Frame(clean_card, bg=Theme.CARD_BG)
        actions.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(actions, text="Очистить кэш", command=clear_temp_cache, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left")
        tk.Button(actions, text="Очистить память", command=clear_memory, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))
        tk.Button(actions, text="Очистить лог", command=clear_logs, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))
        tk.Button(actions, text="Сбросить настройки", command=reset_settings_only, bg="#7f1d1d", fg="#f8fafc", relief="flat", padx=12, pady=8).pack(side="left", padx=(8, 0))
def _patched_create_settings_tab4(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    _, updates_body = create_section_card(
        body,
        "Обновления",
        f"Официальный канал обновлений: {DEFAULT_RELEASES_URL}. До первой GitHub-публикации latest-release может отвечать 404 — это не считается критической поломкой.",
    )

    github_var = tk.StringVar(value=DEFAULT_GITHUB_REPO)
    manifest_var = tk.StringVar(value=DEFAULT_RELEASE_API_URL)
    download_var = tk.StringVar(value=str(CONFIG_MGR.get_update_download_url() or "").strip())
    trusted_hosts_var = tk.StringVar(value=", ".join(CONFIG_MGR.get_update_trusted_hosts()))

    def _labeled_entry(container, label_text, variable, readonly=False):
        row = tk.Frame(container, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=(0, 10))
        tk.Label(row, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 3))
        entry = tk.Entry(
            row,
            textvariable=variable,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            readonlybackground=Theme.INPUT_BG,
            state="readonly" if readonly else "normal",
        )
        entry.pack(fill="x", ipady=6)
        self._setup_entry_bindings(entry)
        return entry

    _labeled_entry(updates_body, "GitHub репозиторий (owner/repo)", github_var, readonly=True)
    _labeled_entry(updates_body, "URL манифеста обновлений (JSON/API)", manifest_var, readonly=True)
    _labeled_entry(updates_body, "Прямая ссылка на скачивание (опционально)", download_var, readonly=False)
    _labeled_entry(updates_body, "Доверенные хосты обновлений", trusted_hosts_var, readonly=False)

    def save_updates():
        hosts = [h.strip().lower() for h in trusted_hosts_var.get().split(",") if h.strip()]
        default_hosts = list(dict.fromkeys((hosts or []) + list(CONFIG_MGR.default_config.get("update_trusted_hosts", []))))
        CONFIG_MGR.set_many({
            "github_repo": DEFAULT_GITHUB_REPO,
            "update_manifest_url": DEFAULT_RELEASE_API_URL,
            "update_download_url": download_var.get().strip(),
            "update_trusted_hosts": default_hosts,
            "update_check_on_start": True,
        })
        self.set_status_temp("Настройки обновлений сохранены", "ok")
        messagebox.showinfo(app_brand_name(), f"Источник обновлений зафиксирован:\n{DEFAULT_RELEASES_URL}")

    update_actions = tk.Frame(updates_body, bg=Theme.CARD_BG)
    update_actions.pack(fill="x", pady=(4, 0))
    create_action_button(update_actions, "Сохранить настройки обновлений", save_updates, bg=Theme.ACCENT, side="left")
    create_action_button(update_actions, "Проверить обновления сейчас", self.check_for_updates_now, side="left", padx=(8, 0))

    tools_dir = runtime_root_path("publish_tools")
    publish_script = runtime_root_path("publish_tools", "Publish-One-Click.bat")
    tools_available = os.path.isdir(tools_dir) and os.path.exists(publish_script)

    _, publish_body = create_section_card(
        body,
        "Публикация в 1 клик",
        f"Сборка, GitHub bundle, commit, push и tag {app_version_badge()} одной кнопкой. Репозиторий: {DEFAULT_GITHUB_REPO}.",
    )

    if tools_available:
        def open_publish_tools_folder():
            try:
                os.startfile(tools_dir)
            except Exception as e:
                self.report_error("Ошибка открытия инструментов публикации", e, speak=False)

        def run_publish_one_click():
            if not messagebox.askyesno(
                app_brand_name(),
                "Запустить публикацию в 1 клик?\n\nЭто соберет релиз, подготовит GitHub bundle, сделает commit, push и отправит tag в GitHub.",
            ):
                return
            try:
                os.startfile(publish_script)
                self.set_status_temp("Открыл публикацию в 1 клик", "ok")
            except Exception as e:
                self.report_error("Ошибка запуска публикации в 1 клик", e, speak=False)

        actions = tk.Frame(publish_body, bg=Theme.CARD_BG)
        actions.pack(fill="x")
        create_action_button(actions, "Опубликовать одним кликом", run_publish_one_click, bg=Theme.ACCENT, side="left")
        create_action_button(actions, "Открыть publish_tools", open_publish_tools_folder, side="left", padx=(8, 0))
    else:
        tk.Label(
            publish_body,
            text=(
                "Инструменты publish не найдены рядом с текущим запуском.\n"
                "Это нормально для установленной/frozen-копии: publish доступен в исходной папке проекта."
            ),
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            wraplength=760,
        ).pack(anchor="w")


SettingsUiMixin._create_settings_tab4 = _patched_create_settings_tab4

from ..settings_ui_polish import apply_settings_ui_polish

apply_settings_ui_polish(SettingsUiMixin)


def _patched_create_settings_tab4_v2(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    _, updates_body = create_section_card(
        body,
        "Обновления",
        f"Официальный канал обновлений: {DEFAULT_RELEASES_URL}. До первой GitHub-публикации latest-release может отвечать 404 — это не считается критической поломкой.",
    )

    github_var = tk.StringVar(value=DEFAULT_GITHUB_REPO)
    manifest_var = tk.StringVar(value=DEFAULT_RELEASE_API_URL)
    download_var = tk.StringVar(value=str(CONFIG_MGR.get_update_download_url() or "").strip())
    trusted_hosts_var = tk.StringVar(value=", ".join(CONFIG_MGR.get_update_trusted_hosts()))

    def _labeled_entry(container, label_text, variable, readonly=False, help_text: str = ""):
        row = tk.Frame(container, bg=Theme.CARD_BG)
        row.pack(fill="x", pady=(0, 10))
        self._create_settings_field_header(row, label_text, help_text, font=("Segoe UI Semibold", 10))
        entry = tk.Entry(
            row,
            textvariable=variable,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            readonlybackground=Theme.INPUT_BG,
            state="readonly" if readonly else "normal",
        )
        entry.pack(fill="x", ipady=6)
        self._setup_entry_bindings(entry)
        return entry

    _labeled_entry(updates_body, "GitHub-репозиторий (owner/repo)", github_var, readonly=True, help_text="Основной репозиторий, из которого JARVIS читает официальный релиз.")
    _labeled_entry(updates_body, "URL манифеста обновлений (JSON/API)", manifest_var, readonly=True, help_text="Адрес манифеста, где лежит версия, ссылки на файлы и release notes.")
    _labeled_entry(updates_body, "Прямая ссылка на скачивание (опционально)", download_var, readonly=False, help_text="Необязательная прямая ссылка на инсталлятор, если хотите переопределить стандартный путь.")
    _labeled_entry(updates_body, "Доверенные хосты обновлений", trusted_hosts_var, readonly=False, help_text="Список доменов, с которых JARVIS разрешено принимать релизные файлы.")

    def save_updates():
        hosts = [h.strip().lower() for h in trusted_hosts_var.get().split(",") if h.strip()]
        default_hosts = list(dict.fromkeys((hosts or []) + list(CONFIG_MGR.default_config.get("update_trusted_hosts", []))))
        CONFIG_MGR.set_many({
            "github_repo": DEFAULT_GITHUB_REPO,
            "update_manifest_url": DEFAULT_RELEASE_API_URL,
            "update_download_url": download_var.get().strip(),
            "update_trusted_hosts": default_hosts,
            "update_check_on_start": True,
        })
        self.set_status_temp("Настройки обновлений сохранены", "ok")
        messagebox.showinfo(app_brand_name(), f"Источник обновлений зафиксирован:\n{DEFAULT_RELEASES_URL}")

    create_action_grid(
        updates_body,
        [
            {"text": "Сохранить настройки обновлений", "command": save_updates, "bg": Theme.ACCENT},
            {"text": "Проверить обновления сейчас", "command": self.check_for_updates_now},
        ],
        columns=2,
    )

    tools_dir = runtime_root_path("publish_tools")
    publish_script = runtime_root_path("publish_tools", "Publish-One-Click.bat")
    tools_available = os.path.isdir(tools_dir) and os.path.exists(publish_script)

    _, publish_body = create_section_card(
        body,
        "Публикация в 1 клик",
        f"Сборка, GitHub bundle, commit, push и tag {app_version_badge()} одной кнопкой. Репозиторий: {DEFAULT_GITHUB_REPO}.",
    )

    if tools_available:
        def open_publish_tools_folder():
            try:
                os.startfile(tools_dir)
            except Exception as e:
                self.report_error("Ошибка открытия publish_tools", e, speak=False)

        def run_publish_one_click():
            if not messagebox.askyesno(
                app_brand_name(),
                "Запустить публикацию в 1 клик?\n\nЭто соберет релиз, подготовит GitHub bundle, сделает commit, push и отправит tag в GitHub.",
            ):
                return
            try:
                os.startfile(publish_script)
                self.set_status_temp("Открыл публикацию в 1 клик", "ok")
            except Exception as e:
                self.report_error("Ошибка запуска публикации в 1 клик", e, speak=False)

        create_action_grid(
            publish_body,
            [
                {"text": "Опубликовать одним кликом", "command": run_publish_one_click, "bg": Theme.ACCENT},
                {"text": "Открыть инструменты публикации", "command": open_publish_tools_folder},
            ],
            columns=2,
        )
    else:
        note = tk.Label(
            publish_body,
            text=(
                "Инструменты публикации не найдены рядом с текущим запуском.\n"
                "Это нормально для установленной или frozen-копии: публикация доступна в исходной папке проекта."
            ),
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
        )
        note.pack(anchor="w")
        bind_dynamic_wrap(note, publish_body, padding=28, minimum=220)


SettingsUiMixin._create_settings_tab4 = _patched_create_settings_tab4_v2

from .settings_sections import (
    build_apps_settings_section,
    build_diagnostics_settings_section,
    build_main_settings_section,
    build_system_settings_section,
    build_updates_settings_section,
    build_voice_settings_section,
)


SettingsUiMixin._legacy_create_settings_tab1 = SettingsUiMixin._create_settings_tab1
SettingsUiMixin._legacy_create_settings_tab2 = SettingsUiMixin._create_settings_tab2


def _delegated_create_settings_tab1(self, parent):
    return build_main_settings_section(self, parent)


def _delegated_create_settings_tab2(self, parent):
    return build_apps_settings_section(self, parent)


def _delegated_create_voice_center_page(self, parent):
    return build_voice_settings_section(self, parent)


def _delegated_create_diagnostic_tab(self, parent):
    return build_diagnostics_settings_section(self, parent)


def _delegated_create_settings_tab4(self, parent):
    return build_updates_settings_section(self, parent)


def _delegated_create_settings_tab5(self, parent):
    return build_system_settings_section(self, parent)


SettingsUiMixin._create_settings_tab1 = _delegated_create_settings_tab1
SettingsUiMixin._create_settings_tab2 = _delegated_create_settings_tab2
SettingsUiMixin._create_voice_center_page = _delegated_create_voice_center_page
SettingsUiMixin._create_diagnostic_tab = _delegated_create_diagnostic_tab
SettingsUiMixin._create_settings_tab4 = _delegated_create_settings_tab4
SettingsUiMixin._create_settings_tab5 = _delegated_create_settings_tab5

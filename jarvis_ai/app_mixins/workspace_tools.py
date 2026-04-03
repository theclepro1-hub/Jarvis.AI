import os
import tkinter as tk
from tkinter import filedialog, messagebox

from ..branding import APP_EXECUTABLE_NAME, APP_INSTALLER_NAME, APP_VERSION, app_brand_name, app_dialog_title
from ..profile_tools import (
    create_profile_backup,
    export_diagnostics_bundle,
    export_plugin_pack,
    import_plugin_pack,
    restore_profile_backup,
)
from ..readiness import build_readiness_report, format_readiness_report
from ..release_lock import format_release_lock_report, run_release_lock
from ..runtime import runtime_root_path
from ..state import CONFIG_MGR
from ..theme import Theme
from ..ui_factory import bind_dynamic_wrap
from ..voice_profiles import device_profile_kind


class WorkspaceToolsMixin:
    def _cfg(self):
        return getattr(self, "config_mgr", CONFIG_MGR)

    def _workspace_scale_percent(self) -> int:
        try:
            scale_percent = int(self._cfg().get_ui_scale_percent() or 100)
        except Exception:
            scale_percent = 100
        return max(90, min(150, scale_percent))

    def _workspace_scale_factor(self) -> float:
        return float(self._workspace_scale_percent()) / 100.0

    def _workspace_font(self, family: str, size_px: int):
        return (family, -abs(int(size_px)))

    def _workspace_dpi_multiplier(self) -> float:
        multiplier = 1.0
        if not self._cfg().get_dpi_adaptation_enabled():
            return multiplier
        try:
            screen_w = int(self.root.winfo_screenwidth() or 0)
            screen_h = int(self.root.winfo_screenheight() or 0)
        except Exception:
            screen_w = screen_h = 0
        if screen_w and screen_w <= 1440:
            multiplier *= 1.03
        if screen_h and screen_h <= 900:
            multiplier *= 0.98
        return max(0.9, min(1.12, float(multiplier)))

    def _workspace_density_key(self) -> str:
        value = str(self._cfg().get_ui_density() or "comfortable").strip().lower()
        return value if value in {"compact", "comfortable"} else "comfortable"

    def _workspace_metrics(self):
        compact = self._workspace_density_key() == "compact"
        scale = self._workspace_scale_factor()

        def s(value: int, minimum: int = 1) -> int:
            return max(minimum, int(round(float(value) * scale)))

        return {
            "compact": compact,
            "scale": scale,
            "shell_pad": s(10 if compact else 14),
            "card_pad": s(13 if compact else 16),
            "sidebar_width": s(208 if compact else 228, minimum=168),
            "rail_width": 0,
            "brand_font": self._workspace_font("Bahnschrift SemiBold", s(20 if compact else 24, minimum=14)),
            "title_font": self._workspace_font("Bahnschrift SemiBold", s(28 if compact else 34, minimum=18)),
            "body_font": self._workspace_font("Segoe UI", s(12 if compact else 14, minimum=10)),
            "small_font": self._workspace_font("Segoe UI", s(11 if compact else 12, minimum=9)),
            "input_font": self._workspace_font("Segoe UI", s(15 if compact else 17, minimum=11)),
            "entry_height": s(90 if compact else 104, minimum=76),
        }

    def _apply_dpi_scaling(self):
        if not getattr(self, "root", None):
            return
        base_tk_scaling = getattr(self, "_base_tk_scaling", None)
        if not isinstance(base_tk_scaling, (int, float)) or float(base_tk_scaling) <= 0:
            try:
                base_tk_scaling = float(self.root.tk.call("tk", "scaling") or 1.0)
            except Exception:
                base_tk_scaling = 1.0
            self._base_tk_scaling = float(base_tk_scaling)
        user_scale = self._workspace_scale_factor()
        dpi_multiplier = self._workspace_dpi_multiplier()
        target_scale = max(0.75, min(3.0, float(base_tk_scaling) * user_scale * dpi_multiplier))
        last_scale = getattr(self, "_last_applied_dpi_scale", None)
        if isinstance(last_scale, (int, float)) and abs(float(last_scale) - float(target_scale)) < 0.001:
            return
        try:
            self.root.tk.call("tk", "scaling", round(target_scale, 3))
            self._last_applied_dpi_scale = float(target_scale)
        except Exception:
            pass

    def _show_text_report_window(self, title: str, text: str, geometry: str = "760x620"):
        win = tk.Toplevel(self.root)
        win.title(app_dialog_title(title))
        win.geometry(geometry)
        win.configure(bg=Theme.BG)
        win.transient(self.root)

        outer = tk.Frame(win, bg=Theme.BG)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        header = tk.Frame(outer, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        header.pack(fill="x")
        tk.Label(header, text=title, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(
            anchor="w", padx=14, pady=(14, 4)
        )
        desc = tk.Label(
            header,
            text="Этот отчет можно сохранить и перечитать перед релизом или перед разбором проблем с голосом и обновлениями.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 9),
        )
        desc.pack(fill="x", padx=14, pady=(0, 12))
        bind_dynamic_wrap(desc, header, padding=28, minimum=220)

        body = tk.Frame(outer, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True, pady=(10, 0))
        text_box = tk.Text(
            body,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            insertbackground=Theme.FG,
            wrap="word",
            relief="flat",
            bd=0,
            font=("Consolas", 10),
        )
        text_box.pack(fill="both", expand=True, padx=12, pady=12)
        text_box.insert("1.0", text)
        text_box.configure(state="disabled")
        try:
            self._register_scroll_target(text_box)
        except Exception:
            pass
        return win

    def run_readiness_master(self):
        report = build_readiness_report(self)
        self._cfg().set_readiness_last_report(report.get("checks", []))
        self._cfg().set_readiness_last_summary(report.get("summary", ""))
        text = format_readiness_report(report)
        self.add_msg(report.get("summary", "Проверка готовности завершена."), "bot")
        self._show_text_report_window("Проверка готовности", text, geometry="780x640")
        self.set_status("Проверка готовности завершена", "ok")

    def run_release_lock_check(self):
        root = runtime_root_path()
        result = run_release_lock(root, APP_VERSION, APP_EXECUTABLE_NAME, APP_INSTALLER_NAME)
        text = format_release_lock_report(result)
        self._show_text_report_window("Проверка релиза", text, geometry="760x600")
        passed = int(result.get("passed", 0) or 0)
        total = int(result.get("total", 0) or 0)
        tone = "ok" if passed == total else "warn"
        self.set_status(f"Проверка релиза {passed}/{total}", tone)

    def create_profile_backup_action(self):
        backup_path = create_profile_backup()
        self.add_msg(f"Резервная копия профиля создана: {backup_path}", "bot")
        messagebox.showinfo(app_brand_name(), f"Резервная копия создана:\n{backup_path}", parent=self.root)
        self.set_status("Резервная копия создана", "ok")

    def restore_profile_backup_action(self):
        initial_dir = os.path.join(runtime_root_path(), "release")
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Выберите резервную копию профиля",
            initialdir=initial_dir if os.path.isdir(initial_dir) else runtime_root_path(),
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
        )
        if not path:
            return
        ok, message = restore_profile_backup(path)
        if ok:
            self.reload_services()
            self.add_msg("Профиль восстановлен из резервной копии.", "bot")
            self.set_status("Профиль восстановлен", "ok")
            messagebox.showinfo(app_brand_name(), message, parent=self.root)
        else:
            self.set_status("Ошибка восстановления", "error")
            messagebox.showerror(app_brand_name(), str(message), parent=self.root)

    def export_diagnostics_bundle_action(self):
        extra = []
        for candidate in [
            runtime_root_path("release", "CRASH_TEST_REPORT.txt"),
            runtime_root_path("release", "manifest.json"),
            runtime_root_path("release", "RELEASE_NOTES.md"),
        ]:
            if os.path.exists(candidate):
                extra.append(candidate)
        bundle = export_diagnostics_bundle(extra)
        self.add_msg(f"Пакет поддержки готов: {bundle}", "bot")
        messagebox.showinfo(app_brand_name(), f"Пакет поддержки экспортирован:\n{bundle}", parent=self.root)
        self.set_status("Пакет поддержки экспортирован", "ok")

    def export_plugin_pack_action(self):
        payload = {
            "custom_apps": list(self._cfg().get_custom_apps() or []),
            "launcher_games": list(self._cfg().get_launcher_games() or []),
            "learned_commands": list(self._cfg().get_learned_commands() or []),
            "scenarios": list(self._cfg().get_scenarios() or []),
            "memory": list(self._cfg().get_user_memory_items() or []),
        }
        pack_path = export_plugin_pack(payload, name_hint="jarvis_ai_2_plugin_pack")
        self._cfg().set_plugin_pack_last_path(pack_path)
        self.add_msg(f"Набор пользовательских действий сохранен: {pack_path}", "bot")
        messagebox.showinfo(app_brand_name(), f"Набор сохранен:\n{pack_path}", parent=self.root)
        self.set_status("Набор сохранен", "ok")

    def import_plugin_pack_action(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Импорт пользовательского набора",
            initialdir=os.path.dirname(self._cfg().get_plugin_pack_last_path() or runtime_root_path()),
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        ok, payload = import_plugin_pack(path)
        if not ok:
            self.set_status("Ошибка импорта набора", "error")
            messagebox.showerror(app_brand_name(), str(payload), parent=self.root)
            return
        self._cfg().update(
            {
                "custom_apps": payload.get("custom_apps", []),
                "launcher_games": payload.get("launcher_games", []),
                "learned_commands": payload.get("learned_commands", []),
                "scenarios": payload.get("scenarios", []),
                "user_memory_items": payload.get("memory", []),
            }
        )
        self._cfg().set_plugin_pack_last_path(path)
        self.add_msg("Пользовательский набор импортирован и применен.", "bot")
        self.set_status("Набор импортирован", "ok")
        messagebox.showinfo(app_brand_name(), "Набор успешно загружен.", parent=self.root)

    def _workspace_command_palette_items(self):
        items = [
            ("Новая беседа", lambda: self.clear_chat()),
            ("Проверка готовности", self.run_readiness_master),
            ("Центр голоса", lambda: self.open_full_settings_view("voice")),
            ("Открыть настройки", lambda: self.open_full_settings_view("main")),
            ("Приложения и игры", lambda: self.open_full_settings_view("apps")),
            ("Система", lambda: self.open_full_settings_view("system")),
            ("История команд", self.show_history),
            ("Подсказки", self.show_quick_tips),
            ("Диагностика", self.run_runtime_diagnostic),
            ("Краш-тест", self.run_external_crash_test),
            ("Проверить обновления", self.check_for_updates_now),
            ("Проверка релиза", self.run_release_lock_check),
            ("Резервная копия профиля", self.create_profile_backup_action),
            ("Восстановить профиль", self.restore_profile_backup_action),
            ("Экспорт диагностики", self.export_diagnostics_bundle_action),
            ("Экспорт пользовательского набора", self.export_plugin_pack_action),
            ("Импорт пользовательского набора", self.import_plugin_pack_action),
            ("Комфортный интерфейс", lambda: self.set_density_mode("comfortable")),
            ("Компактный интерфейс", lambda: self.set_density_mode("compact")),
            ("Фокус-режим", self.toggle_focus_mode),
            ("Полный экран", self.toggle_fs),
        ]
        rollback_action = getattr(self, "rollback_last_update_action", None)
        if callable(rollback_action):
            items.insert(12, ("Откатить последнее обновление", rollback_action))
        return items

    def open_command_palette(self, _event=None):
        if getattr(self, "_command_palette_window", None) and self._command_palette_window.winfo_exists():
            self._command_palette_window.lift()
            self._command_palette_query.focus_set()
            return "break"

        win = tk.Toplevel(self.root)
        self._command_palette_window = win
        win.title(app_dialog_title("Быстрый поиск"))
        win.geometry("640x480")
        win.configure(bg=Theme.BG)
        win.transient(self.root)

        outer = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(outer, text="Быстрый поиск", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(
            anchor="w", padx=14, pady=(14, 6)
        )
        note = tk.Label(
            outer,
            text="Начните печатать действие или раздел. Enter запускает выбранный пункт.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 9),
        )
        note.pack(fill="x", padx=14, pady=(0, 10))
        bind_dynamic_wrap(note, outer, padding=28, minimum=220)

        query_var = tk.StringVar()
        self._command_palette_query = tk.Entry(
            outer,
            textvariable=query_var,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            insertbackground=Theme.FG,
            relief="flat",
            bd=0,
            font=("Segoe UI", 11),
        )
        self._command_palette_query.pack(fill="x", padx=14, ipady=8)

        listbox = tk.Listbox(
            outer,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            selectbackground=Theme.ACCENT,
            selectforeground=Theme.FG,
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=("Segoe UI", 10),
        )
        listbox.pack(fill="both", expand=True, padx=14, pady=14)
        self._command_palette_listbox = listbox

        actions = self._workspace_command_palette_items()
        self._command_palette_actions = actions

        def refresh():
            query = str(query_var.get() or "").strip().lower()
            listbox.delete(0, tk.END)
            visible = []
            for label, command in actions:
                if not query or query in label.lower():
                    listbox.insert(tk.END, label)
                    visible.append((label, command))
            self._command_palette_visible = visible
            if visible:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(0)

        def activate(_event=None):
            selection = listbox.curselection()
            if not selection:
                return "break"
            index = int(selection[0])
            visible = getattr(self, "_command_palette_visible", [])
            if 0 <= index < len(visible):
                _, callback = visible[index]
                try:
                    win.destroy()
                finally:
                    self._command_palette_window = None
                callback()
            return "break"

        query_var.trace_add("write", lambda *_args: refresh())
        self._command_palette_query.bind("<Return>", activate)
        listbox.bind("<Double-Button-1>", activate)
        listbox.bind("<Return>", activate)
        win.bind("<Escape>", lambda _e: win.destroy())
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_command_palette())
        refresh()
        self._command_palette_query.focus_set()
        return "break"

    def _close_command_palette(self):
        try:
            if getattr(self, "_command_palette_window", None) and self._command_palette_window.winfo_exists():
                self._command_palette_window.destroy()
        except Exception:
            pass
        self._command_palette_window = None

    def _set_focus_layout_visible(self, sidebar: bool, rail: bool):
        if hasattr(self, "sidebar"):
            try:
                if sidebar:
                    self.sidebar.grid()
                else:
                    self.sidebar.grid_remove()
            except Exception:
                pass
        if hasattr(self, "side_panel"):
            try:
                if rail:
                    self.side_panel.grid()
                else:
                    self.side_panel.grid_remove()
            except Exception:
                pass

    def refresh_workspace_layout_mode(self, *_args):
        if not hasattr(self, "shell"):
            return
        try:
            width = int(self.main_container.winfo_width() or self.root.winfo_width() or 0)
        except Exception:
            width = 0
        focus = bool(self._cfg().get_focus_mode_enabled())
        if focus:
            self._set_focus_layout_visible(False, False)
            utility_visible = False
        else:
            sidebar_visible = width >= 1120
            self._set_focus_layout_visible(sidebar_visible, False)
            utility_visible = width >= 1420

        utility_shell = getattr(self, "utility_shell", None)
        if utility_shell is not None:
            try:
                visible = bool(utility_shell.winfo_ismapped())
                if utility_visible and not visible:
                    utility_shell.grid()
                elif not utility_visible and visible:
                    utility_shell.grid_remove()
            except Exception:
                pass

        if hasattr(self, "workspace_mode_var") and str(self.workspace_mode_var.get() or "") != "":
            self.workspace_mode_var.set("")

        if hasattr(self, "quick_desc_label"):
            if focus:
                copy = "Фокус-режим убирает боковые панели и оставляет чат, верхние статусы, кнопку настроек и быстрый ввод."
            elif utility_visible:
                copy = "Чат в центре, быстрые входы слева, голос и последние действия справа. Все глубокие инструменты открываются отдельно."
            else:
                copy = "Чат остается главным. Вторичные панели скрываются на узком окне, а нужные разделы открываются кнопками."
            if str(self.quick_desc_label.cget("text") or "") != copy:
                self.quick_desc_label.configure(text=copy)

        if hasattr(self, "workspace_mode_badge") and getattr(self, "workspace_mode_badge", None):
            try:
                self.workspace_mode_badge.pack_forget()
            except Exception:
                pass

        self._update_guide_context("focus" if focus else "")

    def toggle_focus_mode(self):
        enabled = not bool(self._cfg().get_focus_mode_enabled())
        self._cfg().set_focus_mode_enabled(enabled)
        self.refresh_workspace_layout_mode()
        self.set_status("Фокус-режим включен" if enabled else "Фокус-режим выключен", "ok")

    def set_density_mode(self, mode: str):
        mode = str(mode or "comfortable").strip().lower()
        if mode not in {"compact", "comfortable"}:
            mode = "comfortable"
        self._cfg().set_ui_density(mode)
        self._apply_dpi_scaling()
        try:
            self._rebuild_workspace_shell_v2()
        except Exception:
            pass
        self.refresh_workspace_layout_mode()
        labels = {"compact": "компактный", "comfortable": "комфортный"}
        self.set_status(f"Интерфейс: {labels.get(mode, mode)}", "ok")
        self._update_guide_context()

    def _device_profile_summary(self) -> str:
        mic_name = str(getattr(self, "get_selected_microphone_name", lambda: "")() or "").strip()
        profile_mode = str(self._cfg().get_device_profile_mode() or "auto").strip().lower()
        kind = device_profile_kind(mic_name)
        labels = {
            "headset": "гарнитура",
            "usb_mic": "USB-микрофон",
            "built_in": "встроенный микрофон",
            "webcam": "веб-камера",
            "default": "универсальный профиль",
        }
        base = labels.get(kind, "универсальный профиль")
        if profile_mode != "auto":
            return f"{base}  •  вручную: {profile_mode}"
        return f"{base}  •  авто"

    def _update_guide_context(self, section: str = ""):
        panel = getattr(self, "guide_panel", None)
        if not panel:
            return
        summary = self._cfg().get_readiness_last_summary() or "Готов подсказать, куда идти дальше."
        mapping = {
            "chat": (
                "Нубик JARVIS",
                "Чат в центре",
                "Главный экран снова построен вокруг разговора. Здесь ты пишешь, диктуешь и получаешь ответ без лишнего шума.",
                "→ Все редкие системные и релизные действия вынесены глубже.",
            ),
            "readiness": (
                "Нубик JARVIS",
                "Проверка готовности",
                "Перед релизом удобно сначала прогнать проверку готовности: сеть, микрофон, голос, ключ и канал обновлений.",
                "→ Подробная проверка живет в системе и не засоряет домашний экран.",
            ),
            "voice": (
                "Нубик JARVIS",
                "Голос и слышимость",
                f"Сейчас для устройства подобран профиль: {self._device_profile_summary()}. На главном экране оставлены только живые индикаторы без лишней панели управления.",
                "→ Полная калибровка и профили устройств доступны в системном разделе.",
            ),
            "apps": (
                "Нубик JARVIS",
                "Приложения и игры",
                "Приложения и пользовательские ярлыки открываются отдельно, чтобы чат не тонул в служебных кнопках.",
                "→ Добавляй новые действия через системные инструменты только когда это нужно.",
            ),
            "system": (
                "Нубик JARVIS",
                "Система",
                "Здесь живут резервные копии, память, сценарии, диагностика, обновления и релизный контроль.",
                "→ Главный экран остается спокойным именно потому, что все это вынесено сюда.",
            ),
            "focus": (
                "Нубик JARVIS",
                "Фокус-режим",
                "Фокус-режим убирает боковые панели и оставляет только чат, ввод и голос. Это самый чистый рабочий сценарий.",
                "→ Включай его, когда не хочется видеть вообще ничего лишнего.",
            ),
        }
        title, status, text, pointer = mapping.get(
            section or "chat",
            (
                "Нубик JARVIS",
                summary,
                "Я рядом, чтобы разгружать интерфейс и подсказывать, какой раздел нужен именно сейчас.",
                "→ Выбери раздел слева или нажми Ctrl+K для быстрого поиска.",
            ),
        )
        panel.set_message(title=title, status=status, text=text, pointer=pointer)


__all__ = ["WorkspaceToolsMixin"]

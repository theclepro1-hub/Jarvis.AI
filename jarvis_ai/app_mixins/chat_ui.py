import logging
import threading
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk
from PIL import ImageTk

from ..action_permissions import category_label
from ..branding import APP_LOGGER_NAME, app_dialog_title, app_title, app_version_badge
from ..commands import get_dynamic_entries
from ..state import CONFIG_MGR, db
from ..theme import Theme
from ..ui_factory import bind_dynamic_wrap
from ..utils import short_exc

logger = logging.getLogger(APP_LOGGER_NAME)


class ChatUiMixin:
    def _cfg(self):
        return getattr(self, "config_mgr", CONFIG_MGR)

    def _db(self):
        return getattr(self, "db", db)

    def show_quick_tips(self):
        dynamic_count = len(get_dynamic_entries())
        tips = (
            "Быстрые команды:\n"
            "• открой youtube / steam / discord / ozon / wb\n"
            "• закрой <приложение>\n"
            "• громче / тише / пауза / продолжи\n"
            "• найди <запрос>\n\n"
            f"Пользовательских приложений и игр: {dynamic_count}\n"
            "Подсказка: в оффлайне голос автоматически переключается на pyttsx3."
        )
        messagebox.showinfo(app_dialog_title("Подсказки"), tips, parent=self.root)

    def clear_chat(self):
        for child in self.chat_frame.winfo_children():
            child.destroy()
        self.chat_history.clear()
        if hasattr(self, "_refresh_chat_empty_state"):
            try:
                self._refresh_chat_empty_state()
            except Exception:
                pass
        self._schedule_chat_layout_sync(scroll_to_end=True)
        self.set_status("Чат очищен", "ok")
        self.root.after(2000, lambda: self.set_status("Готов", "ok"))

    def copy_chat(self):
        texts = []
        for item in getattr(self, "chat_history", []):
            text = str(item.get("text", "") or "").strip()
            if not text:
                continue
            sender = str(item.get("sender", "bot") or "bot").strip().lower()
            time_text = str(item.get("time", "") or "").strip()
            prefix = "Вы" if sender == "user" else "JARVIS"
            rendered = f"{prefix}: {text}" if not time_text else f"{prefix} [{time_text}]: {text}"
            texts.append(rendered)
        if not texts:
            for child in self.chat_frame.winfo_children():
                for inner in child.winfo_children():
                    if isinstance(inner, tk.Frame):
                        for label in inner.winfo_children():
                            if isinstance(label, tk.Label):
                                text = str(label.cget("text") or "").strip()
                                if text and text not in texts:
                                    texts.append(text)
        if texts:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(texts))
            self.set_status("Чат скопирован", "ok")
            self.root.after(2000, lambda: self.set_status("Готов", "ok"))

    def paste_text(self):
        try:
            text = str(self.root.clipboard_get() or "")
            if text:
                if bool(getattr(self, "_entry_placeholder_active", False)):
                    try:
                        self._clear_entry_placeholder()
                    except Exception:
                        pass
                try:
                    if self.entry.selection_present():
                        self.entry.delete("sel.first", "sel.last")
                except Exception:
                    pass
                self.entry.insert(tk.INSERT, text)
                try:
                    self.entry.icursor(tk.END)
                except Exception:
                    pass
                self.entry.focus_set()
                self.set_status("Текст вставлен", "ok")
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))
        except tk.TclError:
            self.set_status("Буфер обмена пуст", "warn")
            self.root.after(2000, lambda: self.set_status("Готов", "ok"))

    def show_history(self):
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.history_window = win
        win.title(app_title("История команд", with_version=True))
        win.geometry("470x520")
        win.configure(bg=Theme.BG)
        win.resizable(False, False)

        header = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        header.pack(fill="x", padx=14, pady=(14, 10))
        header_top = tk.Frame(header, bg=Theme.CARD_BG)
        header_top.pack(fill="x", padx=14, pady=(14, 4))
        tk.Label(header_top, text="Последние команды", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(
            header_top,
            text=app_version_badge(),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
        ).pack(side="right")
        desc = tk.Label(
            header,
            text="Недавние голосовые и текстовые команды в одном списке, чтобы быстро понять, что уже запускалось.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 10),
            justify="left",
            wraplength=410,
        )
        desc.pack(anchor="w", padx=14, pady=(0, 14))
        bind_dynamic_wrap(desc, header, padding=28, minimum=220)

        list_frame = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        scroll = ttk.Scrollbar(list_frame, style="Jarvis.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        lb = tk.Listbox(
            list_frame,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            selectbackground=Theme.ACCENT,
            selectforeground=Theme.FG,
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=("Segoe UI", 11),
            yscrollcommand=scroll.set,
        )
        lb.pack(side="left", fill="both", expand=True)
        scroll.config(command=lb.yview)

        rows = self._db().get_recent_history(30)
        for ts, cmd, result in reversed(rows):
            lb.insert("end", f"{ts[:16]} {cmd} → {result or ''}")
        if not rows:
            lb.insert("end", "История пока пустая.")
        def on_close():
            self.history_window = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

    def quick_action(self, cmd):
        if self._startup_gate_setup and not bool(str(self._cfg().get_api_key() or "").strip()):
            self.set_status("Нужна активация", "warn")
            try:
                self.root.after(0, lambda: self.run_setup_wizard(True))
            except Exception:
                pass
            return
        self.set_status("Быстрый запуск...", "busy")
        self.executor.submit(self.process_query, cmd)

    def _render_chat_message(self, text: str, sender: str = "bot", time_text: str = "", store: bool = True):
        sender = "user" if sender == "user" else "bot"
        time_text = time_text or datetime.now().strftime("%H:%M")
        if hasattr(self, "_chat_empty_state") and getattr(self, "_chat_empty_state", None):
            try:
                if self._chat_empty_state.winfo_exists():
                    self._chat_empty_state.destroy()
            except Exception:
                pass
            self._chat_empty_state = None
        if store:
            self.chat_history.append({
                "text": text,
                "sender": sender,
                "time": time_text,
            })
            self._trim_chat_render_cache()

        f = tk.Frame(self.chat_frame, bg=Theme.BG_LIGHT, pady=7)
        f.pack(fill="x")
        color = Theme.BOT_MSG if sender == "bot" else Theme.USER_MSG
        align = "left" if sender == "bot" else "right"
        icon = self.assets.get("ai" if sender == "bot" else "user")
        bubble_border = Theme.BORDER if sender == "bot" else Theme.ACCENT

        wrapper = tk.Frame(f, bg=Theme.BG_LIGHT)
        wrapper.pack(side=align, padx=8)

        if icon and sender == "bot":
            if isinstance(icon, ImageTk.PhotoImage):
                tk.Label(wrapper, image=icon, bg=Theme.BG_LIGHT).pack(side="left", padx=5, anchor="n")
            else:
                tk.Label(wrapper, text=icon, bg=Theme.BG_LIGHT, font=("Segoe UI", 22)).pack(side="left", padx=5, anchor="n")

        inner = tk.Frame(
            wrapper,
            bg=color,
            padx=14,
            pady=10,
            relief="flat",
            bd=1,
            highlightbackground=bubble_border,
            highlightthickness=1,
        )
        inner.pack(side=align)

        label = tk.Label(
            inner,
            text=text,
            bg=color,
            fg=Theme.FG,
            font=("Segoe UI", 12),
            wraplength=420,
            justify="left",
        )
        label.pack(anchor="w")
        bind_dynamic_wrap(label, inner, padding=24, minimum=220)
        time_label = tk.Label(inner, text=time_text, bg=color, fg=Theme.CHAT_TIME_FG, font=("Segoe UI", 9))
        time_label.pack(anchor="e", pady=(5, 0))

        def copy_text(event):
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.set_status("Скопировано", "ok")

        label.bind("<Button-3>", copy_text)
        time_label.bind("<Button-3>", copy_text)
        inner.bind("<Button-3>", copy_text)

        if icon and sender == "user":
            if isinstance(icon, ImageTk.PhotoImage):
                tk.Label(wrapper, image=icon, bg=Theme.BG_LIGHT).pack(side="right", padx=5, anchor="n")
            else:
                tk.Label(wrapper, text=icon, bg=Theme.BG_LIGHT, font=("Segoe UI", 22)).pack(side="right", padx=5, anchor="n")

        self._trim_chat_render_cache()
        self._schedule_chat_layout_sync(scroll_to_end=True)

    def add_msg(self, text, sender="bot"):
        message_text = str(text or "").strip()
        if not message_text:
            return
        history = getattr(self, "chat_history", [])
        if history:
            last = history[-1]
            if str(last.get("sender") or "") == str(sender or "") and str(last.get("text") or "").strip() == message_text:
                return
        self._render_chat_message(text=message_text, sender=sender, time_text=datetime.now().strftime("%H:%M"), store=True)
        if hasattr(self, "_refresh_chat_empty_state"):
            try:
                self._refresh_chat_empty_state()
            except Exception:
                pass

    def _copy_text_to_clipboard(self, text: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(text or ""))
            self.set_status("Отчёт скопирован", "ok")
        except Exception:
            self.set_status("Не удалось скопировать отчёт", "warn")

    def _render_chat_prompt_card(
        self,
        *,
        title: str,
        lines,
        actions=None,
        tone: str = "accent",
    ):
        if hasattr(self, "_chat_empty_state") and getattr(self, "_chat_empty_state", None):
            try:
                if self._chat_empty_state.winfo_exists():
                    self._chat_empty_state.destroy()
            except Exception:
                pass
            self._chat_empty_state = None

        border_map = {
            "accent": Theme.ACCENT,
            "warn": Theme.STATUS_WARN,
            "error": Theme.STATUS_ERROR,
        }
        fg_map = {
            "accent": Theme.ACCENT,
            "warn": Theme.STATUS_WARN,
            "error": Theme.STATUS_ERROR,
        }

        card_wrap = tk.Frame(self.chat_frame, bg=Theme.BG_LIGHT, pady=7)
        card_wrap.pack(fill="x")
        shell = tk.Frame(card_wrap, bg=Theme.BG_LIGHT)
        shell.pack(side="left", padx=8, fill="x")
        card = tk.Frame(
            shell,
            bg=Theme.CARD_BG,
            padx=16,
            pady=14,
            relief="flat",
            bd=1,
            highlightbackground=border_map.get(tone, Theme.BORDER),
            highlightthickness=1,
        )
        card.pack(fill="x")

        tk.Label(
            card,
            text=title,
            bg=Theme.CARD_BG,
            fg=fg_map.get(tone, Theme.FG),
            font=("Segoe UI Semibold", 12),
            justify="left",
        ).pack(anchor="w")

        text_widgets = []
        for line in [str(item or "").strip() for item in (lines or []) if str(item or "").strip()]:
            label = tk.Label(
                card,
                text=line,
                bg=Theme.CARD_BG,
                fg=Theme.FG,
                font=("Segoe UI", 11),
                justify="left",
            )
            label.pack(anchor="w", fill="x", pady=(8 if not text_widgets else 4, 0))
            bind_dynamic_wrap(label, card, padding=30, minimum=260)
            text_widgets.append(label)

        buttons = []
        if actions:
            row = tk.Frame(card, bg=Theme.CARD_BG)
            row.pack(anchor="w", pady=(12, 0))
            for action in actions:
                text = str(action.get("text") or "").strip()
                command = action.get("command")
                if not text or not callable(command):
                    continue
                btn = tk.Button(
                    row,
                    text=text,
                    command=command,
                    bg=action.get("bg", Theme.BUTTON_BG),
                    fg=Theme.FG,
                    relief="flat",
                    padx=12,
                    pady=8,
                    highlightbackground=Theme.BORDER,
                    highlightthickness=1,
                    font=("Segoe UI Semibold", 10),
                    cursor="hand2",
                )
                btn.pack(side="left", padx=(0, 8))
                buttons.append(btn)

        self._schedule_chat_layout_sync(scroll_to_end=True)
        return card_wrap, card, buttons

    def request_action_confirmation(self, *, action: str, arg=None, label: str, category: str, origin: str, description: str = "") -> bool:
        result = {"allowed": False}
        decision = threading.Event()

        def _finish(allowed: bool):
            result["allowed"] = bool(allowed)
            if hasattr(self, "_human_log_summary_var"):
                try:
                    self._human_log_summary_var.set("Подтверждение выдано." if allowed else "Подтверждение отклонено.")
                except Exception:
                    pass
            if hasattr(self, "_last_action_card_var"):
                try:
                    self._last_action_card_var.set(
                        f"Подтверждено: {label}" if allowed else f"Подтверждение отклонено: {label}"
                    )
                except Exception:
                    pass
            for button in list(getattr(self, "_pending_confirmation_buttons", []) or []):
                try:
                    button.configure(state="disabled")
                except Exception:
                    pass
            self._pending_confirmation_buttons = []
            decision.set()

        def _open_settings():
            try:
                self.open_full_settings_view("system")
            except Exception:
                pass

        def _render():
            if hasattr(self, "_last_action_card_var"):
                try:
                    self._last_action_card_var.set(f"Ожидаю подтверждение: {label}")
                except Exception:
                    pass
            if hasattr(self, "_human_log_summary_var"):
                try:
                    self._human_log_summary_var.set("Нужно подтверждение пользователя.")
                except Exception:
                    pass
            lines = [
                f"Понял как: {label}",
                f"Собираюсь сделать: {label}.",
                "Подтвердить?",
                f"Категория: {category_label(category)}",
            ]
            if description:
                lines.append(description)
            if origin:
                lines.append(f"Источник: {origin}")
            _card_wrap, _card, buttons = self._render_chat_prompt_card(
                title="Нужно подтверждение",
                lines=lines,
                actions=[
                    {"text": "Подтвердить", "command": lambda: _finish(True), "bg": Theme.ACCENT},
                    {"text": "Отмена", "command": lambda: _finish(False)},
                    {"text": "Настройки", "command": _open_settings},
                ],
                tone="warn",
            )
            self._pending_confirmation_buttons = buttons

        try:
            self.root.after(0, _render)
        except Exception:
            return False

        answered = decision.wait(timeout=180.0)
        if not answered:
            if hasattr(self, "_human_log_summary_var"):
                try:
                    self._human_log_summary_var.set("Подтверждение не было получено вовремя.")
                except Exception:
                    pass
            if hasattr(self, "_last_action_card_var"):
                try:
                    self._last_action_card_var.set(f"Истекло время подтверждения: {label}")
                except Exception:
                    pass
            self._pending_confirmation_buttons = []
            return False
        return bool(result.get("allowed"))

    def initial_greeting(self):
        now = datetime.now().strftime("%H:%M")
        user_name = str(self._cfg().get_user_name() or "").strip()
        if user_name:
            msg = f"Системы онлайн. Время {now}. Слушаю вас, {user_name}."
        else:
            msg = f"Системы онлайн. Время {now}. Слушаю вас."
        self.root.after(0, lambda: self.add_msg(msg))
        self.say(msg)
        self.set_status("Готов", "ok")

    def speak_msg(self, text):
        if not text:
            return
        self.root.after(0, lambda: self.add_msg(text))
        self.say(text)

    def start_typing_indicator(self):
        self._typing_animating = True
        self._typing_tick = 0
        def tick():
            if not self._typing_animating:
                return
            dots = "." * (self._typing_tick % 4)
            self.status_var.set(f"ИИ печатает{dots}")
            self._typing_tick += 1
            self.root.after(300, tick)
        self.root.after(0, tick)

    def stop_typing_indicator(self):
        self._typing_animating = False

    def report_error(self, context, exc, speak=True):
        msg = f"{context}: {short_exc(exc)}"
        self.root.after(0, lambda: self.add_msg(msg))
        if speak:
            self.say(msg)
        self.set_status("Ошибка", "error")
        logger.error(msg, exc_info=exc)
        return msg

    def send_text(self):
        if self._startup_gate_setup and not bool(str(self._cfg().get_api_key() or "").strip()):
            self.set_status("Нужна активация", "warn")
            try:
                self.root.after(0, lambda: self.run_setup_wizard(True))
            except Exception:
                pass
            return
        if bool(getattr(self, "_entry_placeholder_active", False)):
            try:
                self._clear_entry_placeholder()
            except Exception:
                pass
        q = self.entry.get().strip()
        if q:
            self.add_msg(q, "user")
            self.entry.delete(0, tk.END)
            try:
                self._show_entry_placeholder()
            except Exception:
                pass
            self.set_status("Обрабатываю...", "busy")
            self.executor.submit(self.process_query, q)
            return
        try:
            self._show_entry_placeholder()
        except Exception:
            pass


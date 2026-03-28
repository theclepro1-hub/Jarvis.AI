import logging
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk
from PIL import ImageTk

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
        for child in self.chat_frame.winfo_children():
            for inner in child.winfo_children():
                if isinstance(inner, tk.Frame):
                    for label in inner.winfo_children():
                        if isinstance(label, tk.Label):
                            t = label.cget("text")
                            if t and t not in texts:
                                texts.append(t)
        if texts:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(texts))
            self.set_status("Чат скопирован", "ok")
            self.root.after(2000, lambda: self.set_status("Готов", "ok"))

    def paste_text(self):
        try:
            text = self.root.clipboard_get()
            if text:
                self.entry.insert(tk.INSERT, text)
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
            self._show_embedded_activation_gate()
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
        self._render_chat_message(text=text, sender=sender, time_text=datetime.now().strftime("%H:%M"), store=True)
        if hasattr(self, "_refresh_chat_empty_state"):
            try:
                self._refresh_chat_empty_state()
            except Exception:
                pass

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
            self._show_embedded_activation_gate()
            return
        q = self.entry.get().strip()
        if q:
            self.add_msg(q, "user")
            self.entry.delete(0, tk.END)
            self.set_status("Обрабатываю...", "busy")
            self.executor.submit(self.process_query, q)


import textwrap
import tkinter as tk
from typing import Callable, Optional

from .theme import Theme
from .ui_factory import bind_dynamic_wrap


class GuideNoobPanel:
    def __init__(
        self,
        parent,
        image=None,
        title: str = "Noob Guide",
        on_click: Optional[Callable[[], None]] = None,
        variant: str = "default",
    ):
        self.parent = parent
        self.image = image
        self._click_callback = on_click
        self.variant = str(variant or "default").strip().lower()
        self.is_hero = self.variant == "hero"
        self.is_settings = self.variant == "settings"

        outer_pad = 22 if self.is_hero else 11 if self.is_settings else 14
        title_font = ("Segoe UI Semibold", 18 if self.is_hero else 12 if self.is_settings else 12)
        status_font = ("Segoe UI", 12 if self.is_hero else 9 if self.is_settings else 9)
        message_font = ("Segoe UI", 12 if self.is_hero else 9 if self.is_settings else 10)
        pointer_font = ("Segoe UI Semibold", 12 if self.is_hero else 9 if self.is_settings else 10)
        avatar_font = ("Segoe UI", 52 if self.is_hero else 28, "bold")
        wave_font = ("Segoe UI Emoji", 22 if self.is_hero else 14 if self.is_settings else 16)
        initial_wrap = 220 if self.is_hero else 166 if self.is_settings else 180
        self._wave_anchor_relx = 1.0
        self._wave_anchor = "ne"
        self._wave_base_x = -12 if self.is_hero else -4
        self._wave_base_y = -2 if self.is_hero else 1
        self._outer_pad = outer_pad
        self._layout_after = None
        self._layout_signature = None
        self._message_wraplength = initial_wrap
        self._pointer_wraplength = initial_wrap
        self._message_line_limit = 4 if self.is_settings else 0
        self._pointer_line_limit = 0 if self.is_settings else 3
        self._show_pointer = not self.is_settings
        self._title_text = str(title or "Noob Guide")
        self._status_text = "Готов помочь"
        self._message_text = "Подскажу, что делает выбранная функция, и покажу, с чего лучше начать."
        self._pointer_text = "→ Кликните по помощнику, чтобы переключать подсказки"

        self.frame = tk.Frame(
            parent,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            cursor="hand2",
        )
        self.frame.pack(fill="x", expand=False)

        self.top = tk.Frame(self.frame, bg=Theme.CARD_BG, cursor="hand2")
        self.top.pack(fill="x", padx=outer_pad, pady=(outer_pad, 8 if self.is_settings else 10))

        self.avatar_wrap = tk.Frame(self.top, bg=Theme.CARD_BG, cursor="hand2")
        if self.is_hero:
            self.avatar_wrap.pack(anchor="center")
        else:
            self.avatar_wrap.pack(side="left", anchor="n")

        if image:
            self.avatar = tk.Label(self.avatar_wrap, image=image, bg=Theme.CARD_BG, cursor="hand2")
        else:
            self.avatar = tk.Label(self.avatar_wrap, text="J", bg=Theme.CARD_BG, fg=Theme.ACCENT, font=avatar_font, cursor="hand2")
        self.avatar.pack(anchor="center")

        self.wave = tk.Label(self.avatar_wrap, text="👋", bg=Theme.CARD_BG, fg=Theme.ACCENT, font=wave_font, cursor="hand2")
        self.wave.place(relx=self._wave_anchor_relx, x=self._wave_base_x, y=self._wave_base_y, anchor=self._wave_anchor)

        self.text_wrap = tk.Frame(self.top, bg=Theme.CARD_BG, cursor="hand2")
        if self.is_hero:
            self.text_wrap.pack(fill="x", expand=True, pady=(14, 0))
        else:
            self.text_wrap.pack(side="left", fill="x", expand=True, padx=(12, 0))

        title_anchor = "center" if self.is_hero else "w"
        self.title_label = tk.Label(
            self.text_wrap,
            text=self._title_text,
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=title_font,
            justify="center" if self.is_hero else "left",
            cursor="hand2",
        )
        self.title_label.pack(anchor=title_anchor)

        self.status_label = tk.Label(
            self.text_wrap,
            text=self._status_text,
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=status_font,
            justify="center" if self.is_hero else "left",
            cursor="hand2",
        )
        self.status_label.pack(anchor=title_anchor, pady=(6, 0))

        self.message_box = tk.Frame(
            self.frame,
            bg=Theme.BUTTON_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            cursor="hand2",
        )
        self.message_box.pack(fill="x", padx=outer_pad, pady=(0, 8 if self.is_settings else 10))

        self.message_label = tk.Label(
            self.message_box,
            text=self._message_text,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            justify="left",
            font=message_font,
            cursor="hand2",
            wraplength=initial_wrap,
        )
        self.message_label.pack(fill="x", padx=12, pady=10 if self.is_settings else 12)
        bind_dynamic_wrap(self.message_label, self.message_box, padding=28 if self.is_settings else 36, minimum=150)

        self.pointer_label = tk.Label(
            self.frame,
            text=self._pointer_text,
            bg=Theme.CARD_BG,
            fg=Theme.ACCENT,
            font=pointer_font,
            justify="left",
            cursor="hand2",
            wraplength=initial_wrap,
        )
        if self._show_pointer:
            self.pointer_label.pack(anchor="w", padx=outer_pad, pady=(0, outer_pad))
            bind_dynamic_wrap(self.pointer_label, self.frame, padding=(outer_pad * 2) + 8, minimum=150)

        self._wave_tick = 0
        self._wave_after = None
        self._bind_clicks()
        self.start_wave()
        self.frame.bind("<Configure>", lambda _event: self._schedule_layout_refresh(), add="+")
        try:
            self.parent.bind("<Configure>", lambda _event: self._schedule_layout_refresh(), add="+")
        except Exception:
            pass
        self._refresh_text_content()
        self._schedule_layout_refresh()

    def _compress_text(self, text: str, wraplength: int, max_lines: int) -> str:
        raw = " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())
        if not raw or max_lines <= 0:
            return raw
        chars_per_line = max(int(max(int(wraplength or 0), 120) / 7), 14)
        lines = textwrap.wrap(raw, width=chars_per_line, break_long_words=False, break_on_hyphens=False)
        if len(lines) <= max_lines:
            return "\n".join(lines)
        clipped = list(lines[:max_lines])
        tail = clipped[-1].rstrip(" .,;:-")
        if len(tail) > chars_per_line - 1:
            tail = tail[: chars_per_line - 1].rstrip(" .,;:-")
        clipped[-1] = f"{tail or clipped[-1].rstrip()}…"
        return "\n".join(clipped)

    def _refresh_text_content(self):
        self.title_label.configure(text=self._title_text)
        self.status_label.configure(text=self._status_text)
        message_text = self._message_text
        pointer_text = self._pointer_text
        if self.is_settings:
            message_text = self._compress_text(message_text, self._message_wraplength, self._message_line_limit)
            pointer_text = self._compress_text(pointer_text, self._pointer_wraplength, self._pointer_line_limit)
        self.message_label.configure(text=message_text)
        self.pointer_label.configure(text=pointer_text)

    def _apply_wrap_constraints(self):
        try:
            frame_w = int(self.frame.winfo_width() or self.parent.winfo_width() or 0)
        except Exception:
            frame_w = 0
        if frame_w <= 0:
            return
        try:
            message_wrap = max(150, frame_w - (self._outer_pad * 2) - 28)
            pointer_wrap = max(150, frame_w - (self._outer_pad * 2) - 16)
            if self.is_settings:
                message_wrap = min(message_wrap, 178)
                pointer_wrap = min(pointer_wrap, 182)
            self._message_wraplength = message_wrap
            self._pointer_wraplength = pointer_wrap
            self.message_label.configure(wraplength=message_wrap)
            self.pointer_label.configure(wraplength=pointer_wrap)
            self._refresh_text_content()
        except Exception:
            pass

    def _bind_clicks(self):
        for widget in (
            self.frame,
            self.top,
            self.avatar_wrap,
            self.avatar,
            self.wave,
            self.text_wrap,
            self.title_label,
            self.status_label,
            self.message_box,
            self.message_label,
            self.pointer_label,
        ):
            try:
                widget.bind("<Button-1>", self._handle_click, add="+")
            except Exception:
                pass

    def _handle_click(self, _event=None):
        if callable(self._click_callback):
            try:
                self._click_callback()
            except Exception:
                pass

    def set_click_callback(self, callback: Optional[Callable[[], None]]):
        self._click_callback = callback

    def set_message(self, title: str = "", status: str = "", text: str = "", pointer: str = ""):
        if title:
            self._title_text = str(title)
        if status:
            self._status_text = str(status)
        if text:
            self._message_text = str(text)
        if pointer:
            self._pointer_text = str(pointer)
        self._refresh_text_content()
        self._apply_wrap_constraints()
        self._schedule_layout_refresh()

    def apply_theme(self):
        self.frame.configure(bg=Theme.CARD_BG, highlightbackground=Theme.BORDER)
        self.top.configure(bg=Theme.CARD_BG)
        self.avatar_wrap.configure(bg=Theme.CARD_BG)
        self.text_wrap.configure(bg=Theme.CARD_BG)
        self.title_label.configure(bg=Theme.CARD_BG, fg=Theme.FG)
        self.status_label.configure(bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY)
        self.message_box.configure(bg=Theme.BUTTON_BG, highlightbackground=Theme.BORDER)
        self.message_label.configure(bg=Theme.BUTTON_BG, fg=Theme.FG)
        self.pointer_label.configure(bg=Theme.CARD_BG, fg=Theme.ACCENT)
        self.wave.configure(bg=Theme.CARD_BG, fg=Theme.ACCENT)
        if not self.image:
            self.avatar.configure(bg=Theme.CARD_BG, fg=Theme.ACCENT)
        self._schedule_layout_refresh()

    def _schedule_layout_refresh(self):
        if self.is_hero:
            return
        after_id = self._layout_after
        if after_id is not None:
            try:
                self.frame.after_cancel(after_id)
            except Exception:
                pass

        def _refresh():
            self._layout_after = None
            self._refresh_layout()

        try:
            self._layout_after = self.frame.after(24, _refresh)
        except Exception:
            self._refresh_layout()

    def _refresh_layout(self):
        if self.is_hero:
            return
        self._apply_wrap_constraints()
        try:
            width = max(int(self.frame.winfo_width() or self.parent.winfo_width() or 0), 1)
        except Exception:
            return
        stacked = self.is_settings or width < 240
        centered = stacked or self.is_settings
        layout_signature = (stacked, centered)
        if layout_signature == self._layout_signature:
            return
        self._layout_signature = layout_signature

        try:
            self.avatar_wrap.pack_forget()
            self.text_wrap.pack_forget()
        except Exception:
            pass

        if stacked:
            self.avatar_wrap.pack(anchor="center", pady=(0, 6 if self.is_settings else 8))
            self.text_wrap.pack(fill="x", expand=True, pady=(2, 0))
        else:
            self.avatar_wrap.pack(side="left", anchor="n")
            self.text_wrap.pack(side="left", fill="x", expand=True, padx=(12, 0))

        anchor = "center" if centered else "w"
        justify = "center" if centered else "left"
        try:
            self.title_label.pack_configure(anchor=anchor)
            self.status_label.pack_configure(anchor=anchor, pady=(4 if self.is_settings else 6, 0))
            if self._show_pointer:
                self.pointer_label.pack_configure(anchor=anchor, padx=self._outer_pad, pady=(0, self._outer_pad))
        except Exception:
            pass
        self.title_label.configure(justify=justify)
        self.status_label.configure(justify=justify)
        self.pointer_label.configure(justify=justify)

    def start_wave(self):
        if self._wave_after is not None:
            return

        def _tick():
            self._wave_after = None
            if not self.wave.winfo_exists():
                return
            offset_y = -3 if self._wave_tick % 2 == 0 else 3
            offset_x = self._wave_base_x - 2 if self._wave_tick % 2 == 0 else self._wave_base_x + 2
            try:
                self.wave.place_configure(
                    relx=self._wave_anchor_relx,
                    x=offset_x,
                    y=self._wave_base_y + offset_y,
                    anchor=self._wave_anchor,
                )
            except Exception:
                return
            self._wave_tick += 1
            self._wave_after = self.wave.after(420, _tick)

        self._wave_after = self.wave.after(420, _tick)

    def stop(self):
        if self._wave_after is not None:
            try:
                self.wave.after_cancel(self._wave_after)
            except Exception:
                pass
            self._wave_after = None
        if self._layout_after is not None:
            try:
                self.frame.after_cancel(self._layout_after)
            except Exception:
                pass
            self._layout_after = None


__all__ = ["GuideNoobPanel"]

from typing import List

import tkinter as tk
from tkinter import ttk

from .theme import Theme
from .ui_factory import bind_dynamic_wrap


def field_entry(owner, parent, label_text: str, value: str = "", show: str = "", hint: str = ""):
    row = tk.Frame(parent, bg=Theme.CARD_BG)
    row.pack(fill="x", pady=(0, 10))
    tk.Label(row, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 10)).pack(anchor="w")
    var = tk.StringVar(value=value or "")
    entry = tk.Entry(row, textvariable=var, bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG, relief="flat")
    if show:
        entry.configure(show=show)
    entry.pack(fill="x", ipady=7, pady=(4, 0))
    owner._setup_entry_bindings(entry)
    if hint:
        note = tk.Label(row, text=hint, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        note.pack(fill="x", pady=(4, 0))
        bind_dynamic_wrap(note, row, padding=18, minimum=220)
    return var, entry


def field_dropdown(owner, parent, label_text: str, values: List[str], value: str, hint: str = ""):
    row = tk.Frame(parent, bg=Theme.CARD_BG)
    row.pack(fill="x", pady=(0, 10))
    tk.Label(row, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 10)).pack(anchor="w")
    var = tk.StringVar(value=value or (values[0] if values else ""))
    box = ttk.Combobox(row, textvariable=var, values=values, state="readonly", style="Jarvis.TCombobox")
    box.pack(fill="x", ipady=6, pady=(4, 0))
    owner._bind_selector_wheel_guard(box)
    if hint:
        note = tk.Label(row, text=hint, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        note.pack(fill="x", pady=(4, 0))
        bind_dynamic_wrap(note, row, padding=18, minimum=220)
    return var, box


def field_slider(owner, parent, label_text: str, from_: float, to: float, value: float, resolution: float, suffix: str = "", hint: str = ""):
    row = tk.Frame(parent, bg=Theme.CARD_BG)
    row.pack(fill="x", pady=(0, 12))
    head = tk.Frame(row, bg=Theme.CARD_BG)
    head.pack(fill="x")
    tk.Label(head, text=label_text, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 10)).pack(side="left")
    value_label = tk.Label(head, text="", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 9))
    value_label.pack(side="right")
    var = tk.DoubleVar(value=value)

    def _fmt():
        current = float(var.get())
        if resolution >= 1:
            return f"{int(round(current))}{suffix}"
        return f"{current:.2f}{suffix}"

    scale = tk.Scale(
        row,
        from_=from_,
        to=to,
        orient="horizontal",
        resolution=resolution,
        variable=var,
        showvalue=False,
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        troughcolor=Theme.BUTTON_BG,
        highlightthickness=0,
        relief="flat",
        bd=0,
        sliderlength=20,
        activebackground=Theme.ACCENT,
        command=lambda _v: value_label.configure(text=_fmt()),
    )
    scale.pack(fill="x", pady=(6, 0))
    owner._bind_selector_wheel_guard(scale)
    value_label.configure(text=_fmt())
    if hint:
        note = tk.Label(row, text=hint, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        note.pack(fill="x", pady=(5, 0))
        bind_dynamic_wrap(note, row, padding=18, minimum=220)
    return var, scale, value_label


def flag_row(parent, text: str, variable, hint: str = ""):
    row = tk.Frame(parent, bg=Theme.CARD_BG)
    row.pack(fill="x", pady=(0, 8))
    cb = tk.Checkbutton(
        row,
        text=text,
        variable=variable,
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        activebackground=Theme.CARD_BG,
        activeforeground=Theme.FG,
        selectcolor=Theme.INPUT_BG,
        anchor="w",
        justify="left",
    )
    cb.pack(anchor="w")
    if hint:
        note = tk.Label(row, text=hint, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        note.pack(fill="x", padx=(22, 0), pady=(2, 0))
        bind_dynamic_wrap(note, row, padding=32, minimum=220)
    return cb


__all__ = ["field_dropdown", "field_entry", "field_slider", "flag_row"]

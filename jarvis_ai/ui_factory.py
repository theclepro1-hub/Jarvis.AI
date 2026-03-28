import tkinter as tk

from .theme import Theme


def bind_dynamic_wrap(label, parent=None, padding: int = 28, minimum: int = 180):
    host = parent or getattr(label, "master", None)
    if host is None:
        return label

    def _sync_wrap(_event=None):
        try:
            width = int(host.winfo_width() or 0)
        except Exception:
            width = 0
        wrap = max(minimum, width - padding)
        try:
            label.configure(wraplength=wrap)
        except Exception:
            pass

    try:
        host.bind("<Configure>", _sync_wrap, add="+")
        label.after(0, _sync_wrap)
    except Exception:
        pass
    return label


def create_section_card(parent, title: str, description: str = "", padx: int = 14, pady: int = 12):
    card = tk.Frame(parent, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    card.pack(fill="x", padx=18, pady=(0, 14))
    tk.Label(card, text=title, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 13)).pack(anchor="w", padx=padx, pady=(pady, 0))
    if description:
        desc = tk.Label(
            card,
            text=description,
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9),
            justify="left",
        )
        desc.pack(anchor="w", fill="x", padx=padx, pady=(6, 10))
        bind_dynamic_wrap(desc, card, padding=(padx * 2) + 12, minimum=220)
    body = tk.Frame(card, bg=Theme.CARD_BG)
    body.pack(fill="x", padx=padx, pady=(0, pady))
    return card, body


def create_action_button(parent, text: str, command, bg: str = "", fg: str = "", **pack_kwargs):
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg or Theme.BUTTON_BG,
        fg=fg or Theme.FG,
        relief="flat",
        padx=14,
        pady=8,
    )
    btn.pack(**pack_kwargs)
    return btn


def create_action_grid(parent, items, columns: int = 2, bg: str = ""):
    bg = bg or Theme.CARD_BG
    grid = tk.Frame(parent, bg=bg)
    grid.pack(fill="x")
    columns = max(1, int(columns or 1))
    for column in range(columns):
        grid.grid_columnconfigure(column, weight=1)

    buttons = []
    normalized_items = list(items or [])
    for index, item in enumerate(normalized_items):
        row = index // columns
        column = index % columns
        text = str(item.get("text", "") or "")
        command = item.get("command")
        button_bg = item.get("bg") or Theme.BUTTON_BG
        button_fg = item.get("fg") or Theme.FG
        padx = (0 if column == 0 else 6, 0 if column == columns - 1 else 6)
        pady = (0, 8 if index < len(normalized_items) - columns else 0)
        btn = tk.Button(
            grid,
            text=text,
            command=command,
            bg=button_bg,
            fg=button_fg,
            relief="flat",
            padx=14,
            pady=8,
            anchor="center",
        )
        btn.grid(row=row, column=column, sticky="ew", padx=padx, pady=pady)
        buttons.append(btn)
    return grid, buttons


def create_note_box(parent, text: str, tone: str = "soft"):
    palette = {
        "soft": (Theme.BUTTON_BG, Theme.FG_SECONDARY),
        "accent": (Theme.BOT_MSG, Theme.FG),
        "warn": (Theme.BUTTON_BG, Theme.STATUS_WARN),
    }
    bg, fg = palette.get(str(tone or "soft").strip().lower(), palette["soft"])
    box = tk.Frame(parent, bg=bg, highlightbackground=Theme.BORDER, highlightthickness=1)
    box.pack(fill="x", pady=(4, 10))
    label = tk.Label(
        box,
        text=text,
        bg=bg,
        fg=fg,
        justify="left",
        font=("Segoe UI", 9),
    )
    label.pack(fill="x", padx=12, pady=10)
    bind_dynamic_wrap(label, box, padding=28, minimum=220)
    return box, label


def create_text_panel(parent, height: int = 10):
    panel = tk.Text(parent, bg=Theme.INPUT_BG, fg=Theme.FG, wrap="word", height=height, font=("Consolas", 10))
    panel.pack(fill="both", expand=True, pady=5)
    return panel

__all__ = [
    "bind_dynamic_wrap",
    "create_action_button",
    "create_action_grid",
    "create_note_box",
    "create_section_card",
    "create_text_panel",
]

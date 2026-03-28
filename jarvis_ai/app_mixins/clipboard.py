import tkinter as tk

from ..theme import Theme


class ClipboardMixin:
    def _insert_clipboard_into_widget(self, widget) -> bool:
        try:
            text = str(self.root.clipboard_get() or "")
        except Exception:
            return False
        if not text:
            return False
        try:
            state = str(widget.cget("state") or "").strip().lower()
            if state in {"disabled", "readonly"}:
                return False
        except Exception:
            pass
        widget_class = ""
        try:
            widget_class = str(widget.winfo_class() or "").strip().lower()
        except Exception:
            widget_class = ""
        is_text = isinstance(widget, tk.Text) or widget_class == "text"
        is_entry_like = (not is_text) and hasattr(widget, "insert") and hasattr(widget, "delete") and widget_class in {"entry", "tentry", "spinbox"}
        try:
            if is_entry_like or isinstance(widget, tk.Entry):
                try:
                    if hasattr(widget, "selection_present") and widget.selection_present():
                        widget.delete("sel.first", "sel.last")
                except Exception:
                    pass
                widget.insert(tk.INSERT, text)
                widget.focus_set()
                return True
            if is_text:
                try:
                    widget.delete("sel.first", "sel.last")
                except Exception:
                    pass
                widget.insert(tk.INSERT, text)
                widget.focus_set()
                return True
        except Exception:
            pass
        try:
            widget.event_generate("<<Paste>>")
            widget.focus_set()
            return True
        except Exception:
            return False

    def _paste_to_focused_widget(self, _event=None):
        target = None
        try:
            target = self.root.focus_get() or self.root.focus_displayof()
        except Exception:
            target = None
        if target is not None:
            try:
                if self._insert_clipboard_into_widget(target):
                    return "break"
            except Exception:
                pass
        return None

    def _install_global_clipboard_shortcuts(self):
        if self._global_clipboard_bound:
            return
        try:
            for seq in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
                self.root.bind_all(seq, self._paste_to_focused_widget, add="+")
            self.root.bind_all("<Control-KeyPress>", self._handle_layout_aware_global_shortcuts, add="+")
            self._global_clipboard_bound = True
        except Exception:
            self._global_clipboard_bound = False

    def _setup_entry_bindings(self, entry):
        def _emit(sequence):
            def _handler(_e):
                try:
                    entry.event_generate(sequence)
                except Exception:
                    pass
                return "break"
            return _handler

        def _paste(_e):
            if not self._insert_clipboard_into_widget(entry):
                try:
                    entry.event_generate("<<Paste>>")
                except Exception:
                    pass
            return "break"

        def _select_all(_e):
            try:
                if isinstance(entry, tk.Text):
                    entry.tag_add("sel", "1.0", "end-1c")
                    entry.mark_set("insert", "end-1c")
                else:
                    entry.select_range(0, tk.END)
                    entry.icursor(tk.END)
            except Exception:
                pass
            return "break"

        entry.bind("<Control-c>", _emit("<<Copy>>"), add="+")
        entry.bind("<Control-C>", _emit("<<Copy>>"), add="+")
        entry.bind("<Control-Insert>", _emit("<<Copy>>"), add="+")
        entry.bind("<Control-v>", _paste, add="+")
        entry.bind("<Control-V>", _paste, add="+")
        entry.bind("<Shift-Insert>", _paste, add="+")
        entry.bind("<Control-x>", _emit("<<Cut>>"), add="+")
        entry.bind("<Control-X>", _emit("<<Cut>>"), add="+")
        entry.bind("<Shift-Delete>", _emit("<<Cut>>"), add="+")
        entry.bind("<Control-a>", _select_all, add="+")
        entry.bind("<Control-A>", _select_all, add="+")
        entry.bind("<Control-KeyPress>", lambda e, w=entry: self._handle_layout_aware_entry_shortcuts(w, e), add="+")
        entry.bind("<Button-3>", self._show_entry_context_menu, add="+")
        entry.bind("<Button-2>", self._show_entry_context_menu, add="+")
        return entry

    def _show_entry_context_menu(self, event):
        entry = event.widget
        menu = tk.Menu(self.root, tearoff=0, bg=Theme.CARD_BG, fg=Theme.FG, activebackground=Theme.ACCENT)
        menu.add_command(label="Копировать", command=lambda: entry.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda w=entry: self._insert_clipboard_into_widget(w))
        menu.add_command(label="Вырезать", command=lambda: entry.event_generate("<<Cut>>"))
        menu.add_separator()
        if isinstance(entry, tk.Text):
            menu.add_command(label="Выделить всё", command=lambda: entry.tag_add("sel", "1.0", "end-1c"))
        else:
            menu.add_command(label="Выделить всё", command=lambda: entry.select_range(0, tk.END))
        menu.post(event.x_root, event.y_root)

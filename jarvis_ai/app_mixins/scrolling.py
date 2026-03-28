import logging

from ..branding import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


class ScrollingMixin:
    def _cleanup_scroll_targets(self):
        cleaned = []
        for widget in list(self._scroll_targets):
            try:
                if widget and widget.winfo_exists():
                    cleaned.append(widget)
            except Exception:
                continue
        self._scroll_targets = cleaned
        try:
            live = {str(widget) for widget in cleaned}
            self._wheel_delta_accum = {
                key: val for key, val in self._wheel_delta_accum.items()
                if key in live
            }
        except Exception:
            self._wheel_delta_accum = {}

    def _is_descendant_of(self, widget, parent) -> bool:
        current = widget
        while current:
            if current == parent:
                return True
            try:
                current = current.master
            except Exception:
                break
        return False

    def _collect_scroll_target_chain(self, widget):
        self._cleanup_scroll_targets()
        if widget is None or not self._scroll_targets:
            return []
        live_targets = {}
        for target in self._scroll_targets:
            try:
                live_targets[str(target)] = target
            except Exception:
                continue
        chain = []
        seen = set()
        current = widget
        while current:
            try:
                key = str(current)
            except Exception:
                key = None
            if key and key in live_targets and key not in seen:
                chain.append(live_targets[key])
                seen.add(key)
            try:
                current = current.master
            except Exception:
                break
        return chain

    def _resolve_scroll_targets(self, event):
        self._cleanup_scroll_targets()
        if not self._scroll_targets:
            return []
        ordered = []
        seen = set()
        candidates = []
        if getattr(event, "widget", None):
            candidates.append(event.widget)
        try:
            hovered = self.root.winfo_containing(event.x_root, event.y_root)
            if hovered:
                candidates.append(hovered)
        except Exception:
            pass
        active_target = getattr(self, "_active_scroll_target", None)
        if active_target is not None:
            candidates.append(active_target)
        for candidate in candidates:
            for target in self._collect_scroll_target_chain(candidate):
                try:
                    key = str(target)
                except Exception:
                    continue
                if key in seen:
                    continue
                ordered.append(target)
                seen.add(key)
        return ordered

    def _resolve_scroll_target(self, event):
        targets = self._resolve_scroll_targets(event)
        return targets[0] if targets else None

    def _target_yview_state(self, target):
        try:
            view = target.yview()
        except Exception:
            return None
        if not isinstance(view, (tuple, list)) or len(view) < 2:
            return None
        try:
            return float(view[0]), float(view[1])
        except Exception:
            return None

    def _can_scroll_target(self, target, steps):
        if not steps:
            return False
        state = self._target_yview_state(target)
        if state is None:
            return False
        first, last = state
        if (last - first) >= 0.999:
            return False
        edge_eps = 0.001
        if steps > 0:
            return last < (1.0 - edge_eps)
        return first > edge_eps

    def _scroll_target(self, target, steps):
        if not steps:
            return False
        before = self._target_yview_state(target)
        try:
            target.yview_scroll(steps, "units")
        except Exception:
            return False
        after = self._target_yview_state(target)
        if before is None or after is None:
            return True
        return abs(after[0] - before[0]) > 1e-6 or abs(after[1] - before[1]) > 1e-6

    def _mousewheel_steps_for_event(self, event, primary_target=None):
        if getattr(event, "num", None) == 4:
            return -1
        if getattr(event, "num", None) == 5:
            return 1
        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return None
        try:
            target_key = str(primary_target or getattr(event, "widget", None) or "global")
        except Exception:
            target_key = "global"
        accum = float(self._wheel_delta_accum.get(target_key, 0.0)) + (-delta / 120.0)
        if abs(accum) < 1.0:
            self._wheel_delta_accum[target_key] = accum
            return None
        steps = int(accum)
        self._wheel_delta_accum[target_key] = accum - steps
        return steps

    def _handle_global_mousewheel(self, event):
        targets = self._resolve_scroll_targets(event)
        primary_target = targets[0] if targets else getattr(self, "_active_scroll_target", None)
        steps = self._mousewheel_steps_for_event(event, primary_target=primary_target)
        if steps is None:
            return "break"
        try:
            if steps > 6:
                steps = 6
            elif steps < -6:
                steps = -6
            if not targets and primary_target is not None:
                targets = self._collect_scroll_target_chain(primary_target)
            for target in targets:
                if not self._can_scroll_target(target, steps):
                    continue
                if self._scroll_target(target, steps):
                    self._active_scroll_target = target
                    return "break"
            for target in targets:
                if self._scroll_target(target, steps):
                    self._active_scroll_target = target
                    return "break"
            return "break"
        except Exception:
            return "break"

    def _ensure_mousewheel_bindings(self):
        if self._mousewheel_bound:
            return
        try:
            self.root.bind_all("<MouseWheel>", self._handle_global_mousewheel, add="+")
            self.root.bind_all("<Button-4>", self._handle_global_mousewheel, add="+")
            self.root.bind_all("<Button-5>", self._handle_global_mousewheel, add="+")
            self._mousewheel_bound = True
        except Exception as e:
            logger.debug(f"Mousewheel global bind error: {e}")

    def _register_scroll_target(self, widget):
        if widget is None:
            return
        self._cleanup_scroll_targets()
        if widget not in self._scroll_targets:
            self._scroll_targets.append(widget)
        try:
            widget.bind("<Enter>", lambda _e, w=widget: setattr(self, "_active_scroll_target", w), add="+")
            widget.bind(
                "<Leave>",
                lambda _e, w=widget: setattr(self, "_active_scroll_target", None)
                if self._active_scroll_target == w else None,
                add="+",
            )
        except Exception:
            pass
        self._ensure_mousewheel_bindings()

    def _bind_selector_wheel_guard(self, widget):
        if widget is None:
            return
        if getattr(widget, "_jarvis_wheel_guard_bound", False):
            return

        def _guard(event):
            try:
                self._handle_global_mousewheel(event)
            except Exception:
                pass
            return "break"

        try:
            widget.bind("<MouseWheel>", _guard, add="+")
            widget.bind("<Button-4>", _guard, add="+")
            widget.bind("<Button-5>", _guard, add="+")
            widget.bind("<Shift-MouseWheel>", _guard, add="+")
            widget.bind("<Shift-Button-4>", _guard, add="+")
            widget.bind("<Shift-Button-5>", _guard, add="+")
        except Exception:
            pass

        try:
            if widget.winfo_class() == "TCombobox":
                popdown = widget.tk.call("ttk::combobox::PopdownWindow", str(widget))
                listbox_path = f"{popdown}.f.l"
                for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>", "<Shift-Button-4>", "<Shift-Button-5>"):
                    widget.tk.call("bind", listbox_path, seq, "break")
        except Exception:
            pass

        try:
            setattr(widget, "_jarvis_wheel_guard_bound", True)
        except Exception:
            pass

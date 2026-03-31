from .utils import short_exc


INLINE_STATUS_DEFAULT = "JARVIS коротко покажет, что понял, перед сложным действием."


def _set_inline_action_status(self, stage: str, detail: str = "", *, level: str = "info", hold_ms: int = 5200):
    text = str(stage or "").strip()
    extra = str(detail or "").strip()
    if extra:
        text = f"{text}: {extra}"
    text = text[:220] or INLINE_STATUS_DEFAULT

    var = getattr(self, "action_explainer_var", None)
    if var is not None:
        try:
            var.set(text)
        except Exception:
            pass

    try:
        self.set_status_temp(text, {"error": "error", "warn": "warn", "ok": "ok"}.get(level, "ok"), duration_ms=max(1200, int(hold_ms or 0)))
    except Exception:
        pass

    after_id = getattr(self, "_inline_status_after_id", None)
    if after_id is not None:
        try:
            self.root.after_cancel(after_id)
        except Exception:
            pass
        self._inline_status_after_id = None

    if hold_ms <= 0:
        return text

    def _clear():
        self._inline_status_after_id = None
        current = getattr(self, "action_explainer_var", None)
        if current is None:
            return
        try:
            if str(current.get() or "").strip() == text:
                current.set(INLINE_STATUS_DEFAULT)
        except Exception:
            pass

    try:
        self._inline_status_after_id = self.root.after(int(hold_ms), _clear)
    except Exception:
        pass
    return text


def _process_query_with_inline_status(self, query: str, reply_callback=None):
    text = str(query or "").strip()
    if text:
        self._set_inline_action_status("Услышал", text, hold_ms=4200)
    try:
        return type(self)._base_process_query_inline_status(self, query, reply_callback=reply_callback)
    except Exception as exc:
        self._set_inline_action_status("Ошибка", short_exc(exc), level="error", hold_ms=7000)
        raise


def _execute_action_with_inline_status(self, action: str, arg=None, raw_cmd: str = "", speak: bool = True, reply_callback=None):
    label = str(raw_cmd or action or "").strip()
    if arg and not raw_cmd:
        label = f"{action}: {arg}"
    self._set_inline_action_status("Выполняю", label, hold_ms=5200)
    try:
        result = type(self)._base_execute_action_inline_status(self, action, arg, raw_cmd, speak, reply_callback)
    except Exception as exc:
        self._set_inline_action_status("Ошибка", short_exc(exc), level="error", hold_ms=7000)
        raise
    summary = str(result or label or "Действие выполнено").strip()
    self._set_inline_action_status("Успешно", summary, level="ok", hold_ms=5600)
    return result


def _request_action_confirmation_with_inline_status(self, *, action: str, arg=None, label: str, category: str, origin: str, description: str = "") -> bool:
    self._set_inline_action_status("Жду подтверждение", label, level="warn", hold_ms=0)
    allowed = type(self)._base_request_action_confirmation_inline_status(
        self,
        action=action,
        arg=arg,
        label=label,
        category=category,
        origin=origin,
        description=description,
    )
    self._set_inline_action_status("Подтверждено" if allowed else "Отменено", label, level="ok" if allowed else "warn", hold_ms=5600)
    return bool(allowed)


def _announce_route_explanation_with_inline_status(self, route, reply_callback=None):
    type(self)._base_announce_route_explanation_inline_status(self, route, reply_callback=reply_callback)
    var = getattr(self, "action_explainer_var", None)
    if var is None:
        return
    try:
        current = str(var.get() or "").strip()
    except Exception:
        current = ""
    if not current:
        return
    prefixes = (
        "Услышал",
        "Распознал",
        "Жду подтверждение",
        "Выполняю",
        "Успешно",
        "Ошибка",
        "Подтверждено",
        "Отменено",
    )
    if any(current.startswith(prefix) for prefix in prefixes):
        return
    self._set_inline_action_status("Распознал", current, hold_ms=6200)


def _report_error_with_inline_status(self, context, exc, speak=True):
    self._set_inline_action_status("Ошибка", short_exc(exc), level="error", hold_ms=7600)
    return type(self)._base_report_error_inline_status(self, context, exc, speak=speak)


def apply_inline_status_runtime(app_cls):
    if getattr(app_cls, "_inline_status_runtime_applied", False):
        return
    app_cls._inline_status_runtime_applied = True
    app_cls._base_process_query_inline_status = app_cls.process_query
    app_cls._base_execute_action_inline_status = app_cls.execute_action
    app_cls._base_request_action_confirmation_inline_status = app_cls.request_action_confirmation
    app_cls._base_announce_route_explanation_inline_status = app_cls._announce_route_explanation
    app_cls._base_report_error_inline_status = app_cls.report_error
    app_cls._set_inline_action_status = _set_inline_action_status
    app_cls.process_query = _process_query_with_inline_status
    app_cls.execute_action = _execute_action_with_inline_status
    app_cls.request_action_confirmation = _request_action_confirmation_with_inline_status
    app_cls._announce_route_explanation = _announce_route_explanation_with_inline_status
    app_cls.report_error = _report_error_with_inline_status


__all__ = ["apply_inline_status_runtime"]

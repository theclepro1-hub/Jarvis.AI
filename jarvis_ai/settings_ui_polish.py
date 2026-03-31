def apply_settings_ui_polish(SettingsUiMixin):
    """Legacy polish hook kept for compatibility.

    The app now uses the dedicated control-center window from
    settings_ui.py as the single source of truth. The old embedded
    notebook layer caused duplicate settings surfaces and broken tab
    routing, so this hook intentionally does nothing.
    """

    if getattr(SettingsUiMixin, "_polish_20260329_noop_applied", False):
        return
    SettingsUiMixin._polish_20260329_noop_applied = True


__all__ = ["apply_settings_ui_polish"]

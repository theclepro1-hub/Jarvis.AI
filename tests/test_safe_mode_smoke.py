import sys
import time
import tkinter as tk

import pytest

import jarvis


def _pump(root, steps: int = 4, delay: float = 0.05):
    for _ in range(max(int(steps), 1)):
        root.update_idletasks()
        root.update()
        time.sleep(max(float(delay), 0.0))


def _make_app(monkeypatch, api_key: str):
    monkeypatch.setattr(sys, "argv", ["jarvis.py", "--safe-mode"])
    monkeypatch.setattr(jarvis.CONFIG_MGR, "get_api_key", lambda: api_key)

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is unavailable: {exc}")

    root.withdraw()
    root.geometry("1440x960+40+40")
    app = jarvis.JarvisApp(root)
    root.deiconify()
    _pump(root)
    return root, app


def test_safe_mode_startup_smoke(monkeypatch):
    root, app = _make_app(monkeypatch, "smoke-key")
    try:
        assert app.safe_mode is True
        assert app.action_executor is app.controllers.actions
        assert app.app_context.controllers is app.controllers
        assert app.ui_rewrite is None
        assert app.chat_shell.winfo_ismapped()
        assert app.activation_gate.winfo_exists()
        assert not app.activation_gate.winfo_ismapped()
        assert getattr(app, "settings_window", None) is None or not app.settings_window.winfo_ismapped()
        assert app.entry.winfo_exists()
        assert app.send_btn.winfo_exists()
        assert app.chat_noob_button.winfo_exists()
    finally:
        app.shutdown()
        root.destroy()


def test_startup_activation_uses_embedded_gate(monkeypatch):
    root, app = _make_app(monkeypatch, "")
    try:
        assert app._startup_gate_setup is True
        assert app.activation_gate.winfo_ismapped()
        assert getattr(app, "settings_window", None) is None or not app.settings_window.winfo_ismapped()
        assert app._activation_gate_submit_btn.cget("text") == "Активировать и открыть чат"
        assert str(app.entry.cget("state")) == "disabled"
        assert str(app.send_btn.cget("state")) == "disabled"
    finally:
        app.shutdown()
        root.destroy()


def test_settings_open_as_full_screen_state(monkeypatch):
    root, app = _make_app(monkeypatch, "ready-key")
    try:
        app.open_full_settings_view("main")
        root.update_idletasks()
        root.update()
        assert app._workspace_section == "settings"
        assert app.settings_window.winfo_ismapped()
        assert app.settings_nav_buttons["main"].cget("text") == "Основное"
        assert app.current_settings_subsection == "main"

        app.close_full_settings_view()
        root.update_idletasks()
        root.update()
        assert app._workspace_section == "chat"
        assert getattr(app, "settings_window", None) is None or not app.settings_window.winfo_ismapped()
    finally:
        app.shutdown()
        root.destroy()


def test_settings_suspend_startup_gate_overlay(monkeypatch):
    root, app = _make_app(monkeypatch, "")
    try:
        assert app._startup_gate_setup is True
        assert app.activation_gate.winfo_ismapped()

        app.open_full_settings_view("main")
        _pump(root)

        assert app._workspace_section == "settings"
        assert app.settings_window.winfo_ismapped()
        assert not app.activation_gate.winfo_ismapped()
        assert not app.bg_canvas.winfo_ismapped()

        app.close_full_settings_view()
        _pump(root)

        assert app._workspace_section == "chat"
        assert app.activation_gate.winfo_ismapped()
        assert app.bg_canvas.winfo_ismapped()
    finally:
        app.shutdown()
        root.destroy()


def test_primary_controls_are_hit_testable(monkeypatch):
    root, app = _make_app(monkeypatch, "ready-key")
    try:
        seen_queries = []
        app.process_query = lambda query: seen_queries.append(query)
        app.entry.delete(0, tk.END)
        app.entry.insert(0, "smoke send")
        app.send_btn.invoke()
        root.update_idletasks()
        root.update()
        assert any(item.get("text") == "smoke send" for item in app.chat_history)

        before = str(app.chat_noob_message.cget("text") or "")
        app.chat_noob_button.event_generate("<Button-1>", x=8, y=8)
        root.update_idletasks()
        root.update()
        after = str(app.chat_noob_message.cget("text") or "")
        assert after and after != before

        app.open_full_settings_view("voice")
        root.update_idletasks()
        root.update()
        app.settings_nav_buttons["apps"].invoke()
        root.update_idletasks()
        root.update()
        assert app.current_settings_subsection == "apps"
    finally:
        app.shutdown()
        root.destroy()


def test_settings_selectors_use_button_runtime(monkeypatch):
    root, app = _make_app(monkeypatch, "ready-key")
    try:
        app.open_full_settings_view("main")
        root.update_idletasks()
        root.update()

        assert app._settings_model_selector.winfo_class() == "Button"
        assert hasattr(app._settings_model_selector, "_jarvis_select")
        assert app._settings_theme_selector.winfo_class() == "Button"

        model_values = list(getattr(app._settings_model_selector, "_jarvis_values", ()))
        if len(model_values) > 1:
            target = next(value for value in model_values if value != app._settings_model_var.get())
            app._settings_model_selector._jarvis_select(target)
            root.update_idletasks()
            root.update()
            assert app._settings_model_var.get() == target

        app.open_full_settings_view("voice")
        root.update_idletasks()
        root.update()

        assert app._settings_mic_selector.winfo_class() == "Button"
        assert app._settings_output_selector.winfo_class() == "Button"
        assert app._settings_tts_provider_selector.winfo_class() == "Button"
        assert app._settings_listening_selector.winfo_class() == "Button"
    finally:
        app.shutdown()
        root.destroy()


def test_system_settings_controls_are_button_driven(monkeypatch):
    root, app = _make_app(monkeypatch, "ready-key")
    try:
        app.open_full_settings_view("system")
        _pump(root)

        assert app._settings_system_interface_selector.winfo_class() == "Button"
        assert app._settings_system_memory_mode_selector.winfo_class() == "Button"
        assert isinstance(app._settings_system_permission_selectors, dict)
        assert app._settings_system_permission_selectors
        assert all(widget.winfo_class() == "Button" for widget in app._settings_system_permission_selectors.values())

        app._settings_system_interface_selector._jarvis_select("Фокус")
        app._settings_system_save_interface_btn.invoke()
        _pump(root)
        assert str(app.config_mgr.get_workspace_view_mode() or "") == "focus"

        first_category = next(iter(app._settings_system_permission_selectors))
        app._settings_system_permission_selectors[first_category]._jarvis_select("Всегда выполнять")
        app._settings_system_save_permissions_btn.invoke()
        _pump(root)
        assert app.config_mgr.get_dangerous_action_modes().get(first_category) == "trust"
    finally:
        app.shutdown()
        root.destroy()


def test_control_center_noob_panel_keeps_sidebar_size(monkeypatch):
    root, app = _make_app(monkeypatch, "ready-key")
    try:
        app.open_full_settings_view("main")
        _pump(root)

        side = app._control_center_side
        guide_host = app._control_center_guide_host
        base_side_width = int(side.winfo_width() or 0)
        base_guide_height = int(guide_host.winfo_height() or 0)

        assert base_side_width >= 240
        assert base_guide_height >= 280

        for section in ("updates", "system", "voice", "main"):
            app._show_control_center_section(section)
            _pump(root)
            assert abs(int(side.winfo_width() or 0) - base_side_width) <= 2
            assert abs(int(guide_host.winfo_height() or 0) - base_guide_height) <= 2
    finally:
        app.shutdown()
        root.destroy()

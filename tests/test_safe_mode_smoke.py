import sys
import tkinter as tk

import pytest

import jarvis


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
    root.update_idletasks()
    root.update()
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
        assert not app.settings_window.winfo_ismapped()
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

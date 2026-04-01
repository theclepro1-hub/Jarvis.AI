#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import copy
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jarvis  # noqa: E402


REPORT_PATH = ROOT / "release" / "CRASH_TEST_REPORT.txt"


class CrashReport:
    def __init__(self):
        self.passed = []
        self.failed = []

    def ok(self, name, details=""):
        self.passed.append((name, details))

    def fail(self, name, details):
        self.failed.append((name, details))

    def assert_true(self, name, condition, details=""):
        if condition:
            self.ok(name, details)
        else:
            self.fail(name, details or "assertion failed")

    @property
    def total(self):
        return len(self.passed) + len(self.failed)

    def render(self):
        lines = [
            "JARVIS AI crash test report",
            "=" * 32,
            f"Passed: {len(self.passed)}",
            f"Failed: {len(self.failed)}",
            f"Total:  {self.total}",
            "",
        ]
        if self.passed:
            lines.append("PASS")
            for name, details in self.passed:
                suffix = f" :: {details}" if details else ""
                lines.append(f"- {name}{suffix}")
            lines.append("")
        if self.failed:
            lines.append("FAIL")
            for name, details in self.failed:
                suffix = f" :: {details}" if details else ""
                lines.append(f"- {name}{suffix}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"


def patch_runtime():
    tk.Misc.update = tk.Misc.update_idletasks
    jarvis.keyboard = None
    jarvis.pystray = None
    jarvis.JarvisApp.create_tray_icon = lambda self, icon_path: None
    jarvis.JarvisApp._setup_hotkey = lambda self: None
    jarvis.JarvisApp.start_bg_anim = lambda self: None
    jarvis.JarvisApp.restart_bg_anim = lambda self, *args, **kwargs: None
    jarvis.JarvisApp.mic_pulse_tick = lambda self: None
    jarvis.JarvisApp._start_audio_meter_monitor = lambda self: None
    jarvis.JarvisApp.run_voice_training_wizard = lambda self: None
    jarvis.JarvisApp._drain_ui_tasks = lambda self: None
    jarvis.JarvisApp._schedule_window_activity_sync = lambda self, *args, **kwargs: None
    jarvis.JarvisApp._sync_window_activity_state = lambda self: None
    jarvis.JarvisApp.listen_task = lambda self: None
    jarvis.JarvisApp.initial_greeting = lambda self: None
    jarvis.JarvisApp.check_for_updates = lambda self: None
    jarvis.JarvisApp.check_update_notification = lambda self: None
    jarvis.JarvisApp.update_net_status = lambda self: None
    jarvis.JarvisApp._start_background_self_check_loop = lambda self: None
    jarvis.JarvisApp.request_action_confirmation = lambda self, *args, **kwargs: True
    jarvis.TelegramBot.start = lambda self: None
    jarvis.TelegramBot.stop = lambda self: None
    jarvis.messagebox.showinfo = lambda *args, **kwargs: None
    jarvis.messagebox.showwarning = lambda *args, **kwargs: None
    jarvis.messagebox.showerror = lambda *args, **kwargs: None
    jarvis.messagebox.askyesno = lambda *args, **kwargs: True
    jarvis.CONFIG_MGR.set_many(
        {
            "api_key": "test-key",
            "first_run_done": True,
            "telegram_user_id": 0,
        }
    )


def make_fake_ai_reply(text):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def collect_widgets(root_widget):
    items = []
    stack = [root_widget]
    while stack:
        widget = stack.pop()
        items.append(widget)
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            continue
    return items


def collect_button_texts(root_widget):
    texts = []
    for widget in collect_widgets(root_widget):
        if getattr(widget, "winfo_class", lambda: "")() != "Button":
            continue
        try:
            text = str(widget.cget("text") or "").strip()
        except Exception:
            text = ""
        if text:
            texts.append(text)
    return texts


def first_visible_canvas(root_widget):
    for widget in collect_widgets(root_widget):
        if getattr(widget, "winfo_class", lambda: "")() != "Canvas":
            continue
        try:
            if widget.winfo_height() > 40 and widget.winfo_ismapped():
                return widget
        except Exception:
            continue
    return None


def pump_ui(root_widget, cycles=4):
    for _ in range(max(1, int(cycles or 1))):
        root_widget.update_idletasks()
        root_widget.update()


def main():
    patch_runtime()
    report = CrashReport()
    opened = []
    replies = []

    original_open_funcs = dict(jarvis.APP_OPEN_FUNCS)
    original_config_snapshot = copy.deepcopy(getattr(jarvis.CONFIG_MGR, "_config", {}))
    for key in list(jarvis.APP_OPEN_FUNCS.keys()):
        jarvis.APP_OPEN_FUNCS[key] = (lambda action_key=key: opened.append(action_key))

    jarvis.close_app = lambda arg=None: True
    jarvis.open_url_search = lambda query="": opened.append(f"search:{query}")
    jarvis.open_weather = lambda: opened.append("weather")
    jarvis.shutdown_pc = lambda: opened.append("shutdown")
    jarvis.restart_pc = lambda: opened.append("restart_pc")
    jarvis.lock_pc = lambda: opened.append("lock")

    root = tk.Tk()
    root.withdraw()
    app = None

    try:
        app = jarvis.JarvisApp(root)
        app._startup_gate_setup = False
        try:
            app._hide_embedded_activation_gate()
        except Exception:
            pass
        try:
            app._set_workspace_section("chat")
        except Exception:
            pass
        root.deiconify()
        root.geometry("1440x960+20+20")
        pump_ui(root, 4)

        report.assert_true("chat shell built", app.chat_shell.winfo_exists())
        report.assert_true("settings screen hidden", getattr(app, "settings_window", None) is None or not app.settings_window.winfo_ismapped())
        report.assert_true("registration hidden", not app.activation_gate.winfo_ismapped())
        report.assert_true("chat has sidebar", getattr(app, "sidebar", None) is not None and app.sidebar.winfo_exists())
        report.assert_true(
            "chat has no right helper panel",
            getattr(app, "side_panel", None) is not None and not app.side_panel.winfo_ismapped(),
        )
        report.assert_true("top bar buttons exist", len(collect_button_texts(app.top_bar)) >= 3, str(collect_button_texts(app.top_bar)))
        report.assert_true("chat controls ready", all(widget.winfo_exists() for widget in (app.entry, app.send_btn, app.mic_btn)))
        report.assert_true("chat noob available", getattr(app, "guide_panel", None) is not None and app.chat_noob_button.winfo_exists())

        pump_ui(root, 2)
        guide_width_before = int(app.guide_panel.frame.winfo_width() or 0)
        guide_height_before = int(app.guide_panel.frame.winfo_height() or 0)
        original_message = str(app.chat_noob_message.cget("text") or "")
        app._advance_guide_hint()
        pump_ui(root, 1)
        report.assert_true("chat noob changes message", str(app.chat_noob_message.cget("text") or "") != original_message)
        guide_width_after = int(app.guide_panel.frame.winfo_width() or 0)
        guide_height_after = int(app.guide_panel.frame.winfo_height() or 0)
        if guide_width_before > 10 and guide_height_before > 10:
            report.assert_true(
                "chat noob width stable",
                guide_width_after == guide_width_before,
                f"{guide_width_before} -> {guide_width_after}",
            )
            report.assert_true(
                "chat noob height stable",
                abs(guide_height_after - guide_height_before) <= 2,
                f"{guide_height_before} -> {guide_height_after}",
            )
        else:
            report.ok("chat noob size probe skipped", f"{guide_width_before}x{guide_height_before} -> {guide_width_after}x{guide_height_after}")

        app.open_command_palette()
        pump_ui(root, 2)
        report.assert_true("command palette items", app._command_palette_listbox.size() >= 6, str(app._command_palette_listbox.size()))
        app._close_command_palette()
        pump_ui(root, 2)

        app.run_readiness_master()
        pump_ui(root, 2)
        report.assert_true("readiness summary saved", bool(jarvis.CONFIG_MGR.get_readiness_last_summary()), jarvis.CONFIG_MGR.get_readiness_last_summary())
        app.run_release_lock_check()
        pump_ui(root, 2)
        report.ok("release lock invoked")

        app.set_density_mode("comfortable")
        pump_ui(root, 2)
        report.assert_true("density comfortable", str(jarvis.CONFIG_MGR.get_ui_density() or "") == "comfortable", str(jarvis.CONFIG_MGR.get_ui_density()))
        app.set_density_mode("compact")
        pump_ui(root, 2)
        report.assert_true("density compact", str(jarvis.CONFIG_MGR.get_ui_density() or "") == "compact", str(jarvis.CONFIG_MGR.get_ui_density()))

        app.open_full_settings_view("main")
        pump_ui(root, 3)
        report.assert_true(
            "settings open full screen",
            app.settings_window is not None and app.settings_window.winfo_ismapped() and app._workspace_section == "settings",
        )
        report.assert_true("settings target main", app.current_settings_subsection == "main", str(app.current_settings_subsection))
        report.assert_true("settings nav tabs", len(getattr(app, "settings_nav_buttons", {})) == 6, str(sorted(getattr(app, "settings_nav_buttons", {}).keys())))
        report.assert_true(
            "settings host visible",
            getattr(app, "_control_center_content", None) is not None and app._control_center_content.winfo_ismapped(),
        )
        report.assert_true(
            "settings main selectors button-driven",
            all(
                getattr(widget, "winfo_class", lambda: "")() == "Button"
                for widget in (
                    getattr(app, "_settings_model_selector", None),
                    getattr(app, "_settings_theme_selector", None),
                )
                if widget is not None
            ),
        )
        selector = getattr(app, "_settings_model_selector", None)
        selector_values = list(getattr(selector, "_jarvis_values", ())) if selector is not None else []
        if selector is not None and len(selector_values) > 1 and hasattr(selector, "_jarvis_select"):
            target_model = next(value for value in selector_values if value != app._settings_model_var.get())
            selector._jarvis_select(target_model)
            pump_ui(root, 1)
            report.assert_true("settings model selector changes value", app._settings_model_var.get() == target_model, app._settings_model_var.get())

        for target in ("voice", "apps", "diagnostics", "system", "updates"):
            app.open_full_settings_view(target)
            pump_ui(root, 2)
            report.assert_true(f"settings route {target}", app.current_settings_subsection == target, str(app.current_settings_subsection))
        report.assert_true(
            "settings voice selectors button-driven",
            all(
                getattr(widget, "winfo_class", lambda: "")() == "Button"
                for widget in (
                    getattr(app, "_settings_mic_selector", None),
                    getattr(app, "_settings_output_selector", None),
                    getattr(app, "_settings_tts_provider_selector", None),
                )
                if widget is not None
            ),
        )

        app.close_full_settings_view()
        pump_ui(root, 2)
        report.assert_true(
            "settings close returns chat",
            app.chat_shell.winfo_ismapped()
            and (getattr(app, "settings_window", None) is None or not app.settings_window.winfo_ismapped())
            and app._workspace_section == "chat",
        )

        app.run_setup_wizard(True)
        pump_ui(root, 2)
        report.assert_true(
            "activation opens embedded registration",
            app.activation_gate.winfo_ismapped(),
            f"registration={app.activation_gate.winfo_ismapped()} chat_state={app.entry.cget('state')}",
        )
        report.assert_true("registration submit available", getattr(app, "_activation_gate_submit_btn", None) is not None)
        report.assert_true("registration disables chat input", str(app.entry.cget("state")) == "disabled", str(app.entry.cget("state")))
        report.assert_true(
            "registration selectors button-driven",
            all(
                getattr(widget, "winfo_class", lambda: "")() == "Button"
                for widget in (
                    getattr(app, "_gate_theme_box", None),
                    getattr(app, "_gate_dangerous_mode_box", None),
                )
                if widget is not None
            ),
        )
        gate_theme_selector = getattr(app, "_gate_theme_box", None)
        gate_theme_values = list(getattr(gate_theme_selector, "_jarvis_values", ())) if gate_theme_selector is not None else []
        if gate_theme_selector is not None and len(gate_theme_values) > 1 and hasattr(gate_theme_selector, "_jarvis_select"):
            target_theme = next(value for value in gate_theme_values if value != app._gate_theme_var.get())
            gate_theme_selector._jarvis_select(target_theme)
            pump_ui(root, 1)
            report.assert_true("registration theme selector changes value", app._gate_theme_var.get() == target_theme, app._gate_theme_var.get())
        gate_danger_selector = getattr(app, "_gate_dangerous_mode_box", None)
        gate_danger_values = list(getattr(gate_danger_selector, "_jarvis_values", ())) if gate_danger_selector is not None else []
        if gate_danger_selector is not None and len(gate_danger_values) > 1 and hasattr(gate_danger_selector, "_jarvis_select"):
            target_danger = next(value for value in gate_danger_values if value != app._gate_dangerous_mode_var.get())
            gate_danger_selector._jarvis_select(target_danger)
            pump_ui(root, 1)
            report.assert_true(
                "registration dangerous selector changes value",
                app._gate_dangerous_mode_var.get() == target_danger,
                app._gate_dangerous_mode_var.get(),
            )
        app._startup_gate_setup = False
        app._hide_embedded_activation_gate()
        pump_ui(root, 2)

        jarvis.CONFIG_MGR.set_theme_mode("light")
        app.apply_theme_runtime()
        pump_ui(root, 2)
        report.assert_true("light theme entry surface", app.entry.cget("bg") == jarvis.Theme.INPUT_BG, app.entry.cget("bg"))

        jarvis.CONFIG_MGR.set_theme_mode("dark")
        app.apply_theme_runtime()
        pump_ui(root, 2)
        report.assert_true("dark theme entry surface", app.entry.cget("bg") == jarvis.Theme.INPUT_BG, app.entry.cget("bg"))

        for idx in range(6):
            root.geometry("980x820+20+20" if idx % 2 == 0 else "1520x980+20+20")
            pump_ui(root, 2)
            if idx % 3 == 0:
                app.open_full_settings_view("main")
            elif idx % 3 == 1:
                app.open_full_settings_view("voice")
            else:
                app.close_full_settings_view()
                app._set_workspace_section("chat")
            pump_ui(root, 2)
        report.ok("resize/open-close stress", "6 loops")

        for action in ("youtube", "steam", "discord", "shutdown"):
            try:
                app.execute_action(action, raw_cmd=action, speak=False)
            except TypeError:
                app.execute_action(action)
            pump_ui(root, 1)
        report.assert_true("local actions executed", len(opened) >= 3, str(opened))

        dry_run_preview = app.build_action_dry_run_lines(action="shutdown", category="power", origin="crash_test")
        report.assert_true(
            "dry run preview present",
            isinstance(dry_run_preview, list) and len(dry_run_preview) >= 3 and any("crash_test" in item for item in dry_run_preview),
            str(dry_run_preview),
        )

        app.groq_client = object()
        fake_ai_responses = iter(
            [
                make_fake_ai_reply("Simple answer without JSON."),
                make_fake_ai_reply('{"items":[{"type":"command","action":"youtube","reply":"Opening YouTube"}]}'),
                make_fake_ai_reply('{"reply":"Accepted"}'),
            ]
        )
        app._ai_call = lambda messages: next(fake_ai_responses)
        app.ai_handler("say hello", reply_callback=replies.append)
        app.ai_handler("open youtube through ai", reply_callback=replies.append)
        app.ai_handler("just answer", reply_callback=replies.append)
        pump_ui(root, 2)
        report.assert_true(
            "ai handler replies",
            any("Simple answer" in item for item in replies) and any("Opening YouTube" in item for item in replies),
            str(replies[-6:]),
        )

        tts_calls = []
        app._speak_with_pyttsx3 = lambda text: tts_calls.append(("pyttsx3", text))
        app._speak_with_edge_tts = lambda text: tts_calls.append(("edge-tts", text))
        app._speak_with_elevenlabs = lambda text: tts_calls.append(("elevenlabs", text))
        app._tts_provider_ready_details = lambda provider: (True, "")

        jarvis.CONFIG_MGR.set_tts_provider("pyttsx3")
        app._speak_by_provider("alpha")
        jarvis.CONFIG_MGR.set_tts_provider("edge-tts")
        app.is_online = True
        app._speak_by_provider("beta " + ("long text " * 8))
        jarvis.CONFIG_MGR.set_tts_provider("elevenlabs")
        jarvis.CONFIG_MGR.set_elevenlabs_api_key("test_key")
        jarvis.CONFIG_MGR.set_elevenlabs_voice_id("voice_test")
        app._speak_by_provider("gamma " + ("long text " * 8))
        app.is_online = False
        jarvis.CONFIG_MGR.set_tts_provider("edge-tts")
        app._speak_by_provider("delta")
        report.assert_true(
            "tts routing",
            any(provider == "pyttsx3" and text == "alpha" for provider, text in tts_calls)
            and any(provider == "edge-tts" and text.startswith("beta ") for provider, text in tts_calls)
            and any(provider == "elevenlabs" and text.startswith("gamma ") for provider, text in tts_calls)
            and any(provider == "pyttsx3" and text == "delta" for provider, text in tts_calls),
            str(tts_calls),
        )

        paths = {
            "steam": jarvis.find_steam_path(),
            "discord": jarvis.find_discord_path(),
            "telegram": jarvis.find_telegram_path(),
        }
        report.assert_true("launcher path repair", all(value not in {"", ".", None} for value in paths.values()), str(paths))

        output_pick = jarvis.pick_output_device()
        report.assert_true("output auto-pick", isinstance(output_pick, tuple) and output_pick[0] is not None, str(output_pick))

    except Exception as exc:
        report.fail("crash test runtime", "".join(traceback.format_exception_only(type(exc), exc)).strip())
        report.fail("traceback", "".join(traceback.format_exc().splitlines(True)[-12:]).strip())
    finally:
        if app is not None:
            try:
                app.shutdown()
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass
        jarvis.APP_OPEN_FUNCS.clear()
        jarvis.APP_OPEN_FUNCS.update(original_open_funcs)
        try:
            with jarvis.CONFIG_MGR._lock:
                jarvis.CONFIG_MGR._config = copy.deepcopy(original_config_snapshot)
                jarvis.CONFIG_MGR._validate()
            jarvis.CONFIG_MGR.save()
        except Exception:
            pass

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rendered = report.render()
    REPORT_PATH.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if not report.failed else 1)


if __name__ == "__main__":
    main()

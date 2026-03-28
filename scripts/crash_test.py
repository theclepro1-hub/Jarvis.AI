#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import traceback
import copy
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
        lines = []
        lines.append("JARVIS AI crash test report")
        lines.append("=" * 32)
        lines.append(f"Passed: {len(self.passed)}")
        lines.append(f"Failed: {len(self.failed)}")
        lines.append(f"Total:  {self.total}")
        lines.append("")
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
    jarvis.GuideNoobPanel.start_wave = lambda self: None
    jarvis.GuideNoobPanel.stop = lambda self: None
    jarvis.TelegramBot.start = lambda self: None
    jarvis.TelegramBot.stop = lambda self: None
    jarvis.messagebox.showinfo = lambda *args, **kwargs: None
    jarvis.messagebox.showwarning = lambda *args, **kwargs: None
    jarvis.messagebox.showerror = lambda *args, **kwargs: None
    jarvis.messagebox.askyesno = lambda *args, **kwargs: True
    jarvis.CONFIG_MGR.set_many({
        "api_key": "test-key",
        "first_run_done": True,
        "telegram_user_id": 0,
    })


def make_fake_ai_reply(text):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def collect_button_texts(root_widget):
    texts = []
    stack = [root_widget]
    while stack:
        widget = stack.pop()
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            continue
        if getattr(widget, "winfo_class", lambda: "")() == "Button":
            try:
                texts.append(widget.cget("text"))
            except Exception:
                pass
    return texts


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


def first_visible_canvas(root_widget):
    for widget in collect_widgets(root_widget):
        if getattr(widget, "winfo_class", lambda: "")() != "Canvas":
            continue
        try:
            if widget.winfo_height() > 40 and float(widget.yview()[1]) < 1.0:
                return widget
        except Exception:
            continue
    return None


def first_widget_by_class(root_widget, class_name):
    for widget in collect_widgets(root_widget):
        if getattr(widget, "winfo_class", lambda: "")() == class_name:
            return widget
    return None


def main():
    patch_runtime()
    report = CrashReport()
    opened = []
    pressed = []
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
    jarvis.maybe_press = lambda key, amount=1: pressed.append((key, amount)) or True

    root = tk.Tk()
    root.withdraw()
    app = None

    try:
        app = jarvis.JarvisApp(root)
        root.update_idletasks()
        root.deiconify()
        root.geometry("620x780+20+20")
        root.update()
        app._apply_main_container_bounds()
        app.refresh_workspace_layout_mode()
        root.update()

        quick_texts = collect_button_texts(app.sidebar)
        report.assert_true("workspace shell ready", hasattr(app, "sidebar") and hasattr(app, "side_panel") and hasattr(app, "guide_panel"))
        report.assert_true("quick buttons present", all(name in quick_texts for name in ["Новая беседа", "Центр голоса", "Настройки", "Приложения и игры", "Система"]), str(quick_texts))
        report.assert_true("guide panel default", bool(app.guide_panel.message_label.cget("text").strip()) and "→" in app.guide_panel.pointer_label.cget("text"), app.guide_panel.message_label.cget("text"))

        app.open_command_palette()
        root.update()
        palette_texts = [app._command_palette_listbox.get(i) for i in range(app._command_palette_listbox.size())]
        report.assert_true("command palette items", "Проверка готовности" in palette_texts and "Проверка релиза" in palette_texts and "Система" in palette_texts, str(palette_texts[:8]))
        app._close_command_palette()
        root.update()

        app.run_readiness_master()
        root.update()
        report.assert_true("readiness summary saved", bool(jarvis.CONFIG_MGR.get_readiness_last_summary()), jarvis.CONFIG_MGR.get_readiness_last_summary())
        app.run_release_lock_check()
        root.update()
        report.ok("release lock invoked")

        app.set_density_mode("comfortable")
        root.update()
        report.assert_true("density scale comfortable", int(jarvis.CONFIG_MGR.get_ui_scale_percent()) >= 126, str(jarvis.CONFIG_MGR.get_ui_scale_percent()))
        app.toggle_focus_mode()
        root.update()
        report.assert_true("focus mode hides side panels", not app.sidebar.winfo_ismapped() and not app.side_panel.winfo_ismapped())
        app.toggle_focus_mode()
        root.update()

        app.toggle_quick_settings_panel(True)
        root.update()
        report.assert_true(
            "legacy settings route opens control center",
            getattr(app, "settings_window", None) is not None and app.settings_window.winfo_exists(),
            str(getattr(app, "settings_window", None)),
        )

        app.open_full_settings_view()
        root.update()
        full_texts = collect_button_texts(app.settings_window)
        report.assert_true("control center buttons", all(name in full_texts for name in ["Сохранить основные", "Закрыть", "ИИ и профиль", "Центр голоса", "Система"]), str(full_texts))

        settings_canvases = [w for w in collect_widgets(app._control_center_content) if getattr(w, "winfo_class", lambda: "")() == "Canvas"]
        report.assert_true("settings tabs scroll hosts", len(settings_canvases) >= 5, str(len(settings_canvases)))
        app._show_control_center_section("main")
        root.update()
        settings_scroll_canvas = first_visible_canvas(app._control_center_pages["main"])
        if settings_scroll_canvas is not None:
            settings_scroll_canvas.yview_moveto(0.0)
            root.update()
            before_scroll = float(settings_scroll_canvas.yview()[0])
            wheel_event = SimpleNamespace(
                widget=settings_scroll_canvas,
                delta=-120,
                x_root=root.winfo_rootx() + 40,
                y_root=root.winfo_rooty() + 200,
            )
            app._handle_global_mousewheel(wheel_event)
            root.update()
            after_scroll = float(settings_scroll_canvas.yview()[0])
            report.assert_true("settings panel mousewheel", after_scroll > before_scroll, f"{before_scroll} -> {after_scroll}")

        app._show_control_center_section("apps")
        root.update()
        apps_canvas = first_visible_canvas(app._control_center_pages["apps"])
        if apps_canvas is None:
            apps_canvas = first_widget_by_class(app._control_center_pages["apps"], "Canvas")
        report.assert_true("apps tab visible canvas", apps_canvas is not None, str(apps_canvas))
        apps_listbox = first_widget_by_class(app._control_center_pages["apps"], "Listbox")
        if apps_canvas is not None and apps_listbox is not None:
            try:
                apps_listbox.delete(0, tk.END)
            except Exception:
                pass
            apps_canvas.yview_moveto(0.0)
            root.update()
            before_scroll = float(apps_canvas.yview()[0])
            wheel_event = SimpleNamespace(
                widget=apps_listbox,
                delta=-120,
                x_root=apps_listbox.winfo_rootx() + 12,
                y_root=apps_listbox.winfo_rooty() + 12,
            )
            app._handle_global_mousewheel(wheel_event)
            root.update()
            after_scroll = float(apps_canvas.yview()[0])
            scroll_range = apps_canvas.yview()
            can_scroll = float(scroll_range[1]) - float(scroll_range[0]) < 0.999
            report.assert_true(
                "apps listbox wheel fallback",
                (after_scroll > before_scroll) or not can_scroll,
                f"{before_scroll} -> {after_scroll}",
            )

        app._show_control_center_section("diagnostics")
        root.update()
        diagnostics_canvas = first_visible_canvas(app._control_center_pages["diagnostics"])
        report.assert_true("diagnostics tab visible canvas", diagnostics_canvas is not None, str(diagnostics_canvas))
        if diagnostics_canvas is not None and getattr(app, "diagnostic_text", None) is not None:
            try:
                app.diagnostic_text.delete("1.0", tk.END)
            except Exception:
                pass
            diagnostics_canvas.yview_moveto(0.0)
            root.update()
            before_scroll = float(diagnostics_canvas.yview()[0])
            wheel_event = SimpleNamespace(
                widget=app.diagnostic_text,
                delta=-120,
                x_root=app.diagnostic_text.winfo_rootx() + 12,
                y_root=app.diagnostic_text.winfo_rooty() + 12,
            )
            app._handle_global_mousewheel(wheel_event)
            root.update()
            after_scroll = float(diagnostics_canvas.yview()[0])
            report.assert_true("diagnostic text wheel fallback", after_scroll > before_scroll, f"{before_scroll} -> {after_scroll}")

        app._show_control_center_section("voice")
        root.update()
        voice_canvas = first_visible_canvas(app._control_center_pages["voice"])
        report.assert_true("voice tab visible canvas", voice_canvas is not None, str(voice_canvas))
        voice_texts = collect_button_texts(app._control_center_pages["voice"])
        report.assert_true(
            "voice center tools",
            all(name in voice_texts for name in ["Тестовая запись", "Что услышал JARVIS", "Прослушать запись", "Автоподбор профиля", "Сохранить профили"]),
            str(voice_texts),
        )

        system_tab = app._control_center_pages.get("system")
        report.assert_true("system tab registered", system_tab is not None, str(getattr(app, "_control_center_pages", {})))
        if system_tab is not None:
            app._show_control_center_section("system")
            root.update()
            system_texts = collect_button_texts(system_tab)
            report.assert_true(
                "system tab advanced tools",
                all(name in system_texts for name in ["Добавить", "Применить", "Открыть журнал", "Проверка релиза", "Резервная копия"]),
                str(system_texts),
            )

            replies.clear()
            app.process_query("запомни что любимая платформа стим", reply_callback=replies.append)
            root.update()
            memory_items = app._get_memory_items()
            report.assert_true(
                "memory route remember",
                any("стим" in str(item.get("value", "")).lower() for item in memory_items),
                str(memory_items),
            )
            app.process_query("что ты помнишь", reply_callback=replies.append)
            root.update()
            report.assert_true(
                "memory route show",
                any("стим" in str(item).lower() for item in replies),
                str(replies[-4:]),
            )

            app._set_scenario_items(
                [
                    {
                        "name": "Ночной режим",
                        "summary": "Включает фокус и компактный интерфейс",
                        "trigger_phrases": ["ночной режим"],
                        "enabled": True,
                        "changes": {"focus_mode_enabled": True, "ui_density": "compact"},
                    }
                ]
            )
            replies.clear()
            app.process_query("включи ночной режим", reply_callback=replies.append)
            root.update()
            report.assert_true(
                "scenario route apply",
                jarvis.CONFIG_MGR.get_current_scenario() == "Ночной режим" and jarvis.CONFIG_MGR.get_focus_mode_enabled(),
                str((jarvis.CONFIG_MGR.get_current_scenario(), jarvis.CONFIG_MGR.get_focus_mode_enabled())),
            )
            report.assert_true(
                "route explanation updated",
                "понял" in str(app.action_explainer_var.get() or "").lower(),
                str(app.action_explainer_var.get()),
            )

        app._show_control_center_section("main")
        root.update()

        jarvis.CONFIG_MGR.set_theme_mode("light")
        app.apply_theme_runtime()
        root.update()
        light_snapshot = (app.main_container.cget("bg"), app.quick_bar.cget("bg"), app.entry.cget("bg"))
        report.assert_true(
            "light theme recolor",
            light_snapshot == (jarvis.Theme.BG_LIGHT, jarvis.Theme.CARD_BG, jarvis.Theme.INPUT_BG),
            str(light_snapshot),
        )
        light_chip_snapshot = (app.voice_insight_card.cget("bg"), app.sidebar.cget("bg"), app.utility_shell.cget("bg"))
        report.assert_true(
            "light theme cards",
            light_chip_snapshot == (jarvis.Theme.CARD_BG, jarvis.Theme.CARD_BG, jarvis.Theme.BG_LIGHT),
            str(light_chip_snapshot),
        )
        report.assert_true("light theme sidebar", app.sidebar.cget("bg") == jarvis.Theme.CARD_BG, app.sidebar.cget("bg"))

        jarvis.CONFIG_MGR.set_theme_mode("dark")
        app.apply_theme_runtime()
        root.update()
        dark_snapshot = (app.main_container.cget("bg"), app.quick_bar.cget("bg"), app.entry.cget("bg"))
        report.assert_true(
            "dark theme recolor",
            dark_snapshot == (jarvis.Theme.BG_LIGHT, jarvis.Theme.CARD_BG, jarvis.Theme.INPUT_BG),
            str(dark_snapshot),
        )
        dark_chip_snapshot = (app.voice_insight_card.cget("bg"), app.sidebar.cget("bg"), app.utility_shell.cget("bg"))
        report.assert_true(
            "dark theme cards",
            dark_chip_snapshot == (jarvis.Theme.CARD_BG, jarvis.Theme.CARD_BG, jarvis.Theme.BG_LIGHT),
            str(dark_chip_snapshot),
        )
        report.assert_true("dark theme rail", app.side_panel.cget("bg") == jarvis.Theme.BG_LIGHT, app.side_panel.cget("bg"))

        for idx in range(16):
            root.geometry("620x780+20+20" if idx % 2 == 0 else "920x940+20+20")
            root.update()
            app.on_resize()
            root.update()
            if idx % 2 == 0:
                app.toggle_quick_settings_panel(True)
                root.update()
                app.toggle_quick_settings_panel(False)
                root.update()
            else:
                app.close_full_settings_view()
                root.update()
                app.open_full_settings_view()
                root.update()
        report.ok("resize/open-close stress", "16 loops")

        app.close_full_settings_view()
        root.update()

        command_cases = [
            "открой ютуб",
            "открой стим",
            "открой дискорд",
            "открой озон",
            "открой вб",
            "время",
            "дата",
            "громче и тише и пауза и продолжи и дальше и назад",
            "открой ютуб и открой стим и открой дискорд и открой озон",
        ]
        for cmd in command_cases:
            app.process_query(cmd, reply_callback=replies.append)
            root.update()
        report.assert_true("local commands executed", len(opened) >= 5, str(opened[:12]))
        report.assert_true("media key commands executed", len(pressed) >= 4, str(pressed))

        app.groq_client = object()
        fake_ai_responses = iter(
            [
                make_fake_ai_reply("Простой ответ без JSON."),
                make_fake_ai_reply('{"items":[{"type":"command","action":"youtube","reply":"Открываю YouTube"}]}'),
                make_fake_ai_reply('{"reply":"Принято"}'),
            ]
        )
        app._ai_call = lambda messages: next(fake_ai_responses)
        app.ai_handler("скажи привет", reply_callback=replies.append)
        app.ai_handler("открой ютуб через ai", reply_callback=replies.append)
        app.ai_handler("просто ответ", reply_callback=replies.append)
        root.update()
        report.assert_true("ai handler replies", any("Простой" in item for item in replies) and any("Открываю YouTube" in item for item in replies), str(replies[-6:]))

        tts_calls = []
        app._speak_with_pyttsx3 = lambda text: tts_calls.append(("pyttsx3", text))
        app._speak_with_edge_tts = lambda text: tts_calls.append(("edge-tts", text))
        app._speak_with_elevenlabs = lambda text: tts_calls.append(("elevenlabs", text))
        app._tts_provider_ready_details = lambda provider: (True, "")

        jarvis.CONFIG_MGR.set_tts_provider("pyttsx3")
        app._speak_by_provider("alpha")
        jarvis.CONFIG_MGR.set_tts_provider("edge-tts")
        app.is_online = True
        app._speak_by_provider("beta " + ("длинный текст " * 8))
        jarvis.CONFIG_MGR.set_tts_provider("elevenlabs")
        jarvis.CONFIG_MGR.set_elevenlabs_api_key("test_key")
        jarvis.CONFIG_MGR.set_elevenlabs_voice_id("voice_test")
        app._speak_by_provider("gamma " + ("длинный текст " * 8))
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

        app.run_runtime_diagnostic()
        root.update()
        report.ok("runtime diagnostic invoked")

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
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stdout.write(rendered)
    except Exception:
        safe_rendered = rendered.encode("ascii", "backslashreplace").decode("ascii", "replace")
        sys.stdout.write(safe_rendered)
    sys.exit(1 if report.failed else 0)


if __name__ == "__main__":
    main()

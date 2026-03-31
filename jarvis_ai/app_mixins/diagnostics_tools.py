import logging
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import messagebox

from ..branding import APP_LOGGER_NAME, APP_USER_AGENT, app_brand_name
from ..commands import normalize_text
from ..runtime import runtime_root_path
from ..state import CONFIG_MGR, get_db_path
from ..storage import app_log_dir
from ..theme import Theme
from ..ui_factory import create_action_button, create_action_grid, create_section_card, create_text_panel
from ..utils import short_exc

logger = logging.getLogger(APP_LOGGER_NAME)
LOG_FILE = os.path.join(app_log_dir(), "jarvis.log")

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    import pygame
except Exception:
    pygame = None

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    from elevenlabs.client import ElevenLabs
except Exception:
    ElevenLabs = None

try:
    from pydub import AudioSegment
except Exception:
    AudioSegment = None


class DiagnosticsToolsMixin:
    def _diagnostic_text_widget(self):
        widget = getattr(self, "diagnostic_text", None)
        if widget is None:
            return None
        try:
            if widget.winfo_exists():
                return widget
        except Exception:
            pass
        return None

    def _history_text_widget(self):
        widget = getattr(self, "history_text", None)
        if widget is None:
            return None
        try:
            if widget.winfo_exists():
                return widget
        except Exception:
            pass
        return None

    def _create_diagnostic_tab(self, parent):
        # Вкладка "Диагностика"
        _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)
        frame = tk.Frame(body, bg=Theme.CARD_BG)
        frame.pack(fill="x", padx=18, pady=12)

        tk.Button(frame, text="Проанализировать код", command=self.run_diagnostic, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(pady=5)
        tk.Button(frame, text="Проверить внутренние ошибки сейчас", command=self.run_runtime_diagnostic, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(pady=(0,5))
        tk.Button(frame, text="Запустить жесткий краш-тест", command=self.run_external_crash_test, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(pady=(0,5))

        self.diagnostic_text = tk.Text(frame, bg=Theme.INPUT_BG, fg=Theme.FG, wrap="word", height=10, font=("Segoe UI", 9))
        self.diagnostic_text.pack(fill="both", expand=True, pady=5)
        self._register_scroll_target(self.diagnostic_text)

        tk.Button(frame, text="Сбросить все пользовательские данные", command=self.reset_user_data, bg="#aa2222", fg=Theme.FG, relief="flat", padx=14, pady=8).pack(pady=5)

        tk.Label(frame, text="История исправлений", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10,0))
        self.history_text = tk.Text(frame, bg=Theme.INPUT_BG, fg=Theme.FG, wrap="word", height=8, font=("Segoe UI", 9))
        self.history_text.pack(fill="both", expand=True, pady=5)
        self._register_scroll_target(self.history_text)
        self.refresh_fix_history()

    def run_diagnostic(self):
        suggestions = self.diagnostic_assistant.analyze_code()
        output_lines = [
            f"Проверка выполнена: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Найдено пунктов: {len(suggestions)}",
            "",
        ]
        for idx, s in enumerate(suggestions, 1):
            output_lines.append(f"{idx}. {s}")
            output_lines.append("")
        text = "\n".join(output_lines).strip()
        box = self._diagnostic_text_widget()
        if box is not None:
            box.delete(1.0, tk.END)
            box.insert(tk.END, text)
        else:
            self._show_text_report_window("Диагностика", text, geometry="760x560")
        should_offer_fix = any(
            "не найдено" not in normalize_text(s) and "корректно" not in normalize_text(s)
            for s in suggestions
        )
        if should_offer_fix:
            if messagebox.askyesno("Применить исправления", "Обнаружены потенциальные проблемы. Применить автоматические исправления?"):
                for s in suggestions:
                    self.diagnostic_assistant.apply_fix(s)
                self.refresh_fix_history()
                messagebox.showinfo("Диагностика", "Исправления записаны в историю. Для полного применения перезапустите приложение.")

    def run_runtime_diagnostic(self):
        findings = self.run_internal_diagnostics()
        box = self._diagnostic_text_widget()
        lines = []
        if findings:
            lines.extend(
                [
                    f"Внутренняя диагностика: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "Режим проверки: текущая сессия приложения",
                    f"Обнаружено замечаний: {len(findings)}",
                    "",
                ]
            )
            for idx, s in enumerate(findings, 1):
                lines.append(f"{idx}. {s}")
                lines.append("")
            self.set_status("Диагностика: найдены замечания", "warn")
            self.root.after(2000, lambda: self.set_status("Готов", "ok"))
        else:
            lines.append("• Критичных ошибок в текущей сессии не найдено.")
            self.set_status("Диагностика: ошибок не найдено", "ok")
            self.root.after(2000, lambda: self.set_status("Готов", "ok"))
        text = "\n".join(lines).strip()
        if box is not None:
            box.delete(1.0, tk.END)
            box.insert(tk.END, text)
        else:
            self._show_text_report_window("Внутренняя диагностика", text, geometry="760x560")

    def run_external_crash_test(self):
        script_path = runtime_root_path("scripts", "crash_test.py")
        report_path = runtime_root_path("release", "CRASH_TEST_REPORT.txt")
        if not os.path.exists(script_path):
            messagebox.showerror(app_brand_name(), f"Скрипт краш-теста не найден:\n{script_path}")
            return

        python_cmd = None
        if not getattr(sys, "frozen", False) and sys.executable and os.path.exists(sys.executable):
            python_cmd = [sys.executable]
        else:
            py_launcher = shutil.which("py")
            if py_launcher:
                python_cmd = [py_launcher, "-3"]
            else:
                python_bin = shutil.which("python")
                if python_bin:
                    python_cmd = [python_bin]
        if not python_cmd:
            messagebox.showerror(app_brand_name(), "Python не найден. Внешний краш-тест доступен только в dev-окружении.")
            return

        self.set_status("Краш-тест...", "busy")
        box = self._diagnostic_text_widget()
        if box is not None:
            box.delete(1.0, tk.END)
            box.insert(tk.END, "Запускаю жесткий краш-тест...\n")

        def _worker():
            cmd = list(python_cmd) + [script_path]
            try:
                result = subprocess.run(
                    cmd,
                    cwd=runtime_root_path(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=900,
                )
                output = (result.stdout or "").strip()
                errors = (result.stderr or "").strip()
                report_note = f"\n\nОтчёт: {report_path}" if os.path.exists(report_path) else ""
                combined = output or "Crash test finished without stdout."
                if errors:
                    combined = f"{combined}\n\nSTDERR:\n{errors}"
                combined = f"{combined}{report_note}"
                ok = result.returncode == 0
            except Exception as e:
                combined = f"Crash test launch error: {e}"
                ok = False

            def _apply():
                box_local = self._diagnostic_text_widget()
                if box_local is not None:
                    box_local.delete(1.0, tk.END)
                    box_local.insert(tk.END, combined)
                else:
                    self._show_text_report_window("Краш-тест", combined, geometry="760x560")
                if ok:
                    self.set_status("Краш-тест завершён", "ok")
                else:
                    self.set_status("Краш-тест нашёл проблемы", "warn")
                self.root.after(2500, lambda: self.set_status("Готов", "ok"))

            self.root.after(0, _apply)

        self.executor.submit(_worker)

    def refresh_fix_history(self):
        box = self._history_text_widget()
        if box is None:
            return
        box.delete(1.0, tk.END)
        for entry in self.diagnostic_assistant.get_history()[-10:]:
            self.history_text.insert(tk.END, f"{entry['timestamp'][:19]}: {entry['fix']}\n")

    def _tail_log_lines(self, max_lines: int = 160):
        if not os.path.exists(LOG_FILE):
            return []
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as lf:
                lines = lf.readlines()
            return lines[-max_lines:]
        except Exception:
            return []

    def _parse_log_datetime(self, line: str):
        row = str(line or "")
        if len(row) < 23:
            return None
        stamp = row[:23]
        try:
            return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f")
        except Exception:
            return None

    def _collect_session_error_lines(self, max_lines: int = 1200):
        lines = self._tail_log_lines(max_lines)
        if not lines:
            return []

        session_start = getattr(self, "_session_started_at", None)
        if isinstance(session_start, datetime):
            cutoff = session_start - timedelta(seconds=5)
        else:
            cutoff = None

        errors = []
        for line in lines:
            if " - ERROR - " not in line:
                continue
            ts = self._parse_log_datetime(line)
            if cutoff:
                # Для диагностики текущей сессии игнорируем строки без корректного timestamp.
                if ts is None or ts < cutoff:
                    continue
            errors.append(line.strip())
        return errors

    def _diagnostic_hint_for_error(self, error_text: str) -> str:
        low = normalize_text(error_text or "")
        if "error code: 409" in low or "getupdates request" in low or "terminated by other getupdates request" in low:
            return "Низкая/средняя серьёзность: конфликт Telegram polling. Обычно запущен второй клиент с тем же токеном. Оставьте один polling-процесс или отключите Telegram токен в настройках."
        if "break infinity polling" in low or "infinity polling: polling exited" in low:
            return "Служебное сообщение Telegram polling. Само по себе не критично; проверьте соседние ошибки (обычно 409 conflict)."
        if "exception traceback" in low:
            return "Это заголовок стека ошибок, а не первопричина. Смотрите строки до/после него в логе."
        if "401" in low or "403" in low or "api key" in low or "invalid_api_key" in low:
            return "Проверьте API-ключ в Настройки -> Доступ и безопасность. Убедитесь, что ключ действителен."
        if "timeout" in low or "timed out" in low or "connection" in low or "network" in low:
            return "Проверьте интернет, DNS и VPN/proxy. При нестабильной сети временно отключите VPN."
        if "no module named" in low or "importerror" in low:
            return "Пакет не установлен или повреждён. Переустановите зависимости и пересоберите приложение."
        if "sqlite" in low or "database is locked" in low:
            return "Закройте другие процессы Jarvis, затем перезапустите приложение. При необходимости очистите БД."
        if "not found" in low or "file not found" in low or "winerror 2" in low:
            return "Проверьте путь в Настройки -> Приложения и наличие файла по этому пути."
        if "access is denied" in low or "permission denied" in low:
            return "Недостаточно прав к файлу/папке. Запустите приложение с нужными правами и проверьте антивирус."
        if "mic" in low or "microphone" in low or "speech" in low:
            return "Проверьте выбранный микрофон, разрешения Windows на доступ к микрофону и профиль слышимости."
        return "Откройте лог, проверьте точный шаг падения и исправьте соответствующий путь/ключ/сетевую настройку."

    def run_internal_diagnostics(self):
        findings = []
        try:
            with sqlite3.connect(get_db_path()) as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception as e:
            findings.append(f"База данных недоступна: {short_exc(e)}")

        if CONFIG_MGR.get_auto_update():
            manifest_url = (CONFIG_MGR.get_update_manifest_url() or "").strip()
            direct_url = (CONFIG_MGR.get_update_download_url() or "").strip()
            for u in (manifest_url, direct_url):
                if u and not self._is_trusted_update_url(u):
                    findings.append("Обновления: обнаружен недоверенный источник URL. Проверьте раздел 'Обновления'.")
                    break

        error_lines = self._collect_session_error_lines(1200)
        if error_lines:
            findings.append(f"В журнале текущей сессии обнаружены ошибки: {len(error_lines)}.")
            shown = []
            seen = set()
            all_norm = []
            for raw_line in error_lines:
                msg_raw = raw_line.split(" - ERROR - ", 1)[-1].strip() if " - ERROR - " in raw_line else raw_line
                all_norm.append(normalize_text(msg_raw))
            has_telegram_409 = any("error code: 409" in n and ("telegram" in n or "getupdates" in n) for n in all_norm)

            for raw_line in reversed(error_lines):
                msg = raw_line
                if " - ERROR - " in raw_line:
                    msg = raw_line.split(" - ERROR - ", 1)[-1].strip()
                norm = normalize_text(msg)
                if has_telegram_409 and (
                    "break infinity polling" in norm
                    or "infinity polling: polling exited" in norm
                    or norm == "exception traceback:"
                ):
                    continue
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                shown.append(msg)
                if len(shown) >= 6:
                    break

            for idx, msg in enumerate(shown, 1):
                hint = self._diagnostic_hint_for_error(msg)
                findings.append(f"Ошибка лога #{idx}: {msg}\nКак исправить: {hint}")

            findings.append(f"Полный лог: {LOG_FILE}")
        elif self.telegram_bot and getattr(self.telegram_bot, "_conflict_count", 0) > 0:
            findings.append(
                "Telegram polling отключен из-за конфликта 409 (один token используется в двух местах). "
                "Оставьте только один bot-клиент с этим токеном."
            )

        if self.proxy_detected and not self.is_online:
            findings.append("Связь нестабильна при включенном VPN/Proxy. Попробуйте перезапустить или временно отключить VPN.")

        tts_provider = CONFIG_MGR.get_tts_provider()
        if tts_provider == "edge-tts":
            if edge_tts is None:
                findings.append("TTS: выбран Edge-TTS, но модуль edge_tts не установлен.")
            if sd is None and pygame is None and not shutil.which("ffplay") and AudioSegment is None:
                findings.append("TTS: для Edge-TTS нужен хотя бы один backend воспроизведения (sounddevice, pygame, ffplay или pydub/ffmpeg).")
        elif tts_provider == "elevenlabs":
            if ElevenLabs is None:
                findings.append("TTS: выбран ElevenLabs, но пакет elevenlabs не установлен.")
            if not CONFIG_MGR.get_elevenlabs_api_key() and not os.getenv("ELEVENLABS_API_KEY"):
                findings.append("TTS: для ElevenLabs не задан API-ключ.")
            if not CONFIG_MGR.get_elevenlabs_voice_id():
                findings.append("TTS: для ElevenLabs не задан ID голоса.")
            if sd is None and pygame is None and not shutil.which("ffplay") and AudioSegment is None:
                findings.append("TTS: для ElevenLabs нужен хотя бы один backend воспроизведения (sounddevice, pygame, ffplay или pydub/ffmpeg).")

        if getattr(sys, 'frozen', False) and not os.path.exists(sys.executable):
            findings.append("Запуск идёт в frozen-режиме, но sys.executable не найден.")

        return findings

    def _start_background_self_check_loop(self):
        if getattr(self, "_self_check_started", False):
            return
        self._self_check_started = True

        def worker():
            while self.running:
                try:
                    if CONFIG_MGR.get_background_self_check():
                        findings = self.run_internal_diagnostics()
                        fingerprint = "|".join(sorted(findings))
                        if findings and fingerprint != self._last_self_check_fingerprint:
                            self._last_self_check_fingerprint = fingerprint
                            self._background_diag_cache = list(findings)
                            self._background_diag_changed_at = time.time()
                        elif not findings:
                            self._last_self_check_fingerprint = ""
                            self._background_diag_cache = []
                    self._last_self_check_at = time.time()
                except Exception as e:
                    logger.warning(f"Background self-check error: {e}")

                interval_min = max(3, int(CONFIG_MGR.get_self_check_interval_min() or 10))
                for _ in range(interval_min * 60):
                    if not self.running:
                        break
                    time.sleep(1)

        threading.Thread(target=worker, daemon=True, name="SelfCheckThread").start()

    def check_internet(self):
        endpoints = (("1.1.1.1", 53), ("8.8.8.8", 53))
        for host, port in endpoints:
            try:
                with socket.create_connection((host, port), timeout=1.2):
                    return True
            except OSError:
                continue
        # HTTPS-check: учитывает системный proxy/VPN и даёт меньше ложных "оффлайн".
        try:
            from urllib.request import Request, urlopen
            for url in ("https://api.github.com", "https://www.google.com/generate_204"):
                try:
                    req = Request(url, headers={"User-Agent": APP_USER_AGENT})
                    with urlopen(req, timeout=2.2) as resp:
                        status = int(getattr(resp, "status", 200) or 200)
                        if 200 <= status < 500:
                            return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _consume_net_status(self):
        if self._net_check_in_progress:
            self.root.after(100, self._consume_net_status)
            return

        try:
            online = bool(self._pending_net_status)
        except Exception:
            online = False

        try:
            prev_online = bool(self.is_online)
            if online != prev_online:
                self.is_online = online
                self._net_flap_times.append(time.monotonic())

                if not online:
                    self.add_msg(
                        "🌐 Нет подключения к интернету.\n"
                        "Groq AI и поиск временно недоступны.\n"
                        "Рекомендации: 1) отключите VPN/proxy, 2) перезапустите VPN, 3) проверьте DNS/сеть.",
                        "bot",
                    )
                    self.set_status_temp("Нет сети: проверьте VPN", "warn")
                else:
                    self.proxy_detected = self._detect_proxy_enabled()
                    self.add_msg("🌐 Связь восстановлена.", "bot")
                    self.set_status_temp("Онлайн", "ok")

                self._apply_tts_auto_network_mode(online)

                if len(self._net_flap_times) >= 3:
                    recent = [t for t in self._net_flap_times if (time.monotonic() - t) <= 180]
                    if len(recent) >= 3 and (time.monotonic() - self._last_net_warning_ts) > 120:
                        self._last_net_warning_ts = time.monotonic()
                        self.add_msg(
                            "⚠️ Сеть нестабильна (частые обрывы).\n"
                            "Попробуйте: перезапустить/отключить VPN, сменить сервер VPN, перезагрузить роутер.",
                            "bot",
                        )

            if getattr(self, "net_label", None):
                if online:
                    self.net_label.config(text="🌐 Онлайн", fg=Theme.ONLINE)
                else:
                    self.net_label.config(text="❌ Оффлайн", fg=Theme.OFFLINE)

            # Если сеть уже восстановлена, но в статусе осталась старая тревога — сбрасываем.
            if online:
                current_status = str(self.status_var.get() or "").strip().lower()
                if "нет сети" in current_status or "vpn" in current_status:
                    self.set_status_temp("Онлайн", "ok")
        finally:
            self._pending_net_status = None

    def update_net_status(self):
        if self._net_check_in_progress:
            self.root.after(12000, self.update_net_status)
            return

        self._net_check_in_progress = True
        self._pending_net_status = None

        def worker():
            try:
                result = self.check_internet()
            except Exception:
                result = False
            self._pending_net_status = result
            self._net_check_in_progress = False

        threading.Thread(target=worker, daemon=True, name="NetCheckThread").start()
        self.root.after(100, self._consume_net_status)
        self.root.after(12000, self.update_net_status)


def _patched_create_diagnostic_tab(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    _, tools_body = create_section_card(
        body,
        "Диагностика и проверка",
        "Предрелизные проверки и отчеты собраны здесь. В frozen/installer-режиме dev-only инструменты "
        "мягко переключаются на встроенную диагностику, без ложных красных ошибок.",
    )
    actions = tk.Frame(tools_body, bg=Theme.CARD_BG)
    actions.pack(fill="x")
    create_action_button(actions, "Проанализировать код", self.run_diagnostic, bg=Theme.ACCENT, side="left")
    create_action_button(actions, "Проверить сессию", self.run_runtime_diagnostic, side="left", padx=(8, 0))
    create_action_button(actions, "Жесткий краш-тест", self.run_external_crash_test, side="left", padx=(8, 0))

    _, results_body = create_section_card(
        body,
        "Результаты",
        "Отчеты и найденные замечания появляются ниже.",
    )
    self.diagnostic_text = create_text_panel(results_body, height=12)
    self._register_scroll_target(self.diagnostic_text)

    _, maintenance_body = create_section_card(
        body,
        "Обслуживание",
        "Редкие и опасные действия вынесены отдельно, чтобы интерфейс оставался чище.",
    )
    create_action_button(
        maintenance_body,
        "Сбросить все пользовательские данные",
        self.reset_user_data,
        bg="#aa2222",
        fill="x",
    )

    _, history_body = create_section_card(
        body,
        "История исправлений",
        "Последние автофиксы и диагностические правки.",
    )
    self.history_text = create_text_panel(history_body, height=8)
    self._register_scroll_target(self.history_text)
    self.refresh_fix_history()


def _patched_diagnostic_hint_for_error(self, error_text: str) -> str:
    low = normalize_text(error_text or "")
    if "update check error" in low and "404" in low and "releases/latest" in low:
        return "GitHub-релиз еще не опубликован. До первого release канал обновлений может отвечать 404 — это не поломка приложения."
    return DiagnosticsToolsMixin._base_diagnostic_hint_for_error(self, error_text)


def _patched_run_internal_diagnostics(self):
    findings = DiagnosticsToolsMixin._base_run_internal_diagnostics(self)
    filtered = []
    for item in findings:
        norm = normalize_text(item)
        if "update check error" in norm and "404" in norm and "releases/latest" in norm:
            continue
        filtered.append(item)
    return filtered


def _patched_run_external_crash_test(self):
    script_path = runtime_root_path("scripts", "crash_test.py")
    report_path = runtime_root_path("release", "CRASH_TEST_REPORT.txt")
    if not os.path.exists(script_path):
        if os.path.exists(report_path):
            self.diagnostic_text.delete(1.0, tk.END)
            self.diagnostic_text.insert(
                tk.END,
                "Исходный crash_test.py не найден в текущем режиме запуска.\n"
                "Показываю последний сохраненный отчет из release-папки.\n\n",
            )
            try:
                with open(report_path, "r", encoding="utf-8", errors="replace") as f:
                    self.diagnostic_text.insert(tk.END, f.read())
            except Exception as e:
                self.diagnostic_text.insert(tk.END, f"Не удалось прочитать сохраненный отчет: {short_exc(e)}")
            self.set_status("Показан последний crash-report", "warn")
            self.root.after(2500, lambda: self.set_status("Готов", "ok"))
            return
        if getattr(sys, "frozen", False):
            self.diagnostic_text.delete(1.0, tk.END)
            self.diagnostic_text.insert(
                tk.END,
                "Во frozen/installer-режиме внешний crash_test.py недоступен.\n"
                "Запускаю встроенную диагностику вместо него.\n\n",
            )
            findings = self.run_internal_diagnostics()
            if findings:
                for idx, item in enumerate(findings, 1):
                    self.diagnostic_text.insert(tk.END, f"{idx}. {item}\n\n")
                self.set_status("Встроенная диагностика завершена", "warn")
            else:
                self.diagnostic_text.insert(tk.END, "Критичных проблем не найдено.\n")
                self.set_status("Встроенная диагностика: ошибок нет", "ok")
            self.root.after(2500, lambda: self.set_status("Готов", "ok"))
            return
        messagebox.showerror(app_brand_name(), f"Скрипт краш-теста не найден:\n{script_path}")
        return
    return DiagnosticsToolsMixin._base_run_external_crash_test(self)


def _patched_create_diagnostic_tab_v2(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

    _, tools_body = create_section_card(
        body,
        "Диагностика и проверка",
        "Здесь собраны предрелизные проверки и живые отчеты. В frozen или installer-режиме dev-only инструменты "
        "мягко переключаются на встроенную диагностику, без лишних ложных ошибок.",
    )
    create_action_grid(
        tools_body,
        [
            {"text": "Проанализировать код", "command": self.run_diagnostic, "bg": Theme.ACCENT},
            {"text": "Проверить сессию", "command": self.run_runtime_diagnostic},
            {"text": "Жесткий краш-тест", "command": self.run_external_crash_test},
        ],
        columns=2,
    )

    _, results_body = create_section_card(
        body,
        "Результаты",
        "Отчеты и найденные замечания появляются ниже.",
    )
    self.diagnostic_text = create_text_panel(results_body, height=12)
    self._register_scroll_target(self.diagnostic_text)

    _, maintenance_body = create_section_card(
        body,
        "Обслуживание",
        "Редкие и потенциально опасные действия вынесены отдельно, чтобы основной интерфейс оставался спокойнее.",
    )
    create_action_grid(
        maintenance_body,
        [
            {
                "text": "Сбросить все пользовательские данные",
                "command": self.reset_user_data,
                "bg": "#aa2222",
                "fg": "#f8fafc",
            }
        ],
        columns=1,
    )

    _, history_body = create_section_card(
        body,
        "История исправлений",
        "Последние автофиксы и диагностические правки.",
    )
    self.history_text = create_text_panel(history_body, height=8)
    self._register_scroll_target(self.history_text)
    self.refresh_fix_history()


DiagnosticsToolsMixin._base_diagnostic_hint_for_error = DiagnosticsToolsMixin._diagnostic_hint_for_error
DiagnosticsToolsMixin._base_run_internal_diagnostics = DiagnosticsToolsMixin.run_internal_diagnostics
DiagnosticsToolsMixin._base_run_external_crash_test = DiagnosticsToolsMixin.run_external_crash_test
DiagnosticsToolsMixin._create_diagnostic_tab = _patched_create_diagnostic_tab_v2
DiagnosticsToolsMixin._diagnostic_hint_for_error = _patched_diagnostic_hint_for_error
DiagnosticsToolsMixin.run_internal_diagnostics = _patched_run_internal_diagnostics
DiagnosticsToolsMixin.run_external_crash_test = _patched_run_external_crash_test


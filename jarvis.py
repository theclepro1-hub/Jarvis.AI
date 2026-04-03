#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JARVIS AI 2.0 Assistant v20.2.0
"""

import os
import sys
import time
import queue
import ctypes
try:
    import ctypes.wintypes as wintypes
except Exception:
    wintypes = None
import threading
import subprocess
import re
import logging
import atexit
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
import asyncio
import shutil
import wave

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import speech_recognition as sr
import pyttsx3
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw
import pystray
from pystray import MenuItem as trayMenuItem

from jarvis_ai.audio_devices import (
    audio_device_family_key as _audio_device_family_key,
    expand_audio_device_name as _expand_audio_device_name,
    find_audio_device_entry_by_name as _find_audio_device_entry_by_name,
    find_audio_device_entry_by_signature as _find_audio_device_entry_by_signature,
    get_audio_device_entry as _get_audio_device_entry,
    host_api_short_label as _host_api_short_label,
    is_audio_garbage_name as _is_audio_garbage_name,
    is_secondary_audio_choice as _is_secondary_audio_choice,
    list_input_device_entries_safe,
    list_microphone_names_safe,
    list_output_device_entries_safe,
    list_output_device_names_safe,
    pick_microphone_device,
    pick_output_device,
)
from jarvis_ai.audio_runtime import (
    audio_rms_int16,
    compressed_audio_decoder_available as _compressed_audio_decoder_available,
    suppress_pydub_ffmpeg_warnings,
)
from jarvis_ai.app_mixins import (
    ChatUiMixin,
    ClipboardMixin,
    DiagnosticsToolsMixin,
    ScrollingMixin,
    SettingsUiMixin,
    UpdateFlowMixin,
    VoicePipelineMixin,
    WorkspaceToolsMixin,
)
from jarvis_ai.action_catalog import SUPPORTED_ACTION_KEYS
from jarvis_ai.bootstrap import AppBootstrap, ensure_httpx_proxy_compat
from jarvis_ai.commands import (
    CommandParser,
    SIMPLE_BATCH_ACTIONS,
    SPLIT_PATTERN,
    find_dynamic_entry,
    find_app_key,
    get_dynamic_entry_by_key,
    normalize_text,
)
from jarvis_ai.action_permissions import (
    DEFAULT_PERMISSION_MODES,
    ask_permission,
    normalize_permission_modes,
    permission_action_label,
    permission_category_for_action,
)
from jarvis_ai.diagnostics import DiagnosticAssistant
from jarvis_ai.effects import DvdLogoBouncer
from jarvis_ai.reminders import ReminderScheduler
from jarvis_ai.state import (
    CONFIG,
    CONFIG_MGR,
    PROMPT_MGR,
    _is_learned_pattern_generic,
    db,
    get_config_path,
    get_db_path,
    get_prompts_dir,
)
from jarvis_ai.telegram_bot import TelegramBot
from jarvis_ai.branding import (
    APP_LOGGER_NAME,
    app_brand_name,
    app_title,
    app_version_badge,
)
from jarvis_ai.controllers import build_app_controllers
from jarvis_ai.guide_noobs import GuideNoobPanel
from jarvis_ai.runtime import parse_geometry, resource_path, set_windows_app_id
from jarvis_ai.app_composition import compose_jarvis_app
from jarvis_ai.response_parsing import extract_json_block
from jarvis_ai.service_hub import build_service_hub
from jarvis_ai.storage import app_config_dir, app_data_dir, app_log_dir
from jarvis_ai.runtime_shell import (
    _patched_build_workspace_chat as restored_build_workspace_chat,
    _patched_build_workspace_controls as restored_build_workspace_controls,
    _patched_build_workspace_overview as restored_build_workspace_overview,
    _patched_build_workspace_rail as restored_build_workspace_rail,
    _patched_build_workspace_shell_v2 as restored_build_workspace_shell_v2,
    _patched_build_workspace_sidebar as restored_build_workspace_sidebar,
    _patched_refresh_chat_empty_state as restored_refresh_chat_empty_state,
    _patched_refresh_workspace_layout_mode as restored_refresh_workspace_layout_mode,
    _set_workspace_section as restored_set_workspace_section,
)
from jarvis_ai.system_actions import (
    APP_OPEN_FUNCS,
    close_app,
    find_discord_path as _find_discord_path,
    find_steam_path as _find_steam_path,
    find_telegram_path as _find_telegram_path,
    get_date_text,
    get_time_text,
    launch_dynamic_entry,
    lock_pc,
    maybe_press,
    open_url_search,
    open_weather,
    refresh_known_app_launchers,
    restart_pc,
    shutdown_pc,
)
from jarvis_ai.theme import Theme
from jarvis_ai.ui_factory import bind_dynamic_wrap, create_action_grid, create_note_box
from jarvis_ai.structured_logging import log_event
from jarvis_ai.utils import short_exc
from jarvis_ai.voice_profiles import device_adaptation_tags

ensure_httpx_proxy_compat()

# Windows-specific constants
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Optional modules
try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    from groq import Groq
    from groq import APIError, APIConnectionError, RateLimitError
except ImportError:
    Groq = None
    APIError = APIConnectionError = RateLimitError = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from tenacity import RetryError, retry, stop_after_attempt, wait_exponential
except ImportError:
    class RetryError(Exception):
        pass

    def retry(*_args, **_kwargs):
        def _decorator(func):
            return func
        return _decorator

    def stop_after_attempt(*_args, **_kwargs):
        return None

    def wait_exponential(*_args, **_kwargs):
        return None

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import pygame
except Exception:
    pygame = None

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    from elevenlabs.client import ElevenLabs
except Exception:
    try:
        from elevenlabs import ElevenLabs
    except Exception:
        ElevenLabs = None

try:
    with suppress_pydub_ffmpeg_warnings():
        from pydub import AudioSegment
except Exception:
    AudioSegment = None

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import pyaudio
except Exception:
    pyaudio = None

# =========================================================
# LOGGING
# =========================================================
LOG_FILE = os.path.join(app_log_dir(), "jarvis.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(APP_LOGGER_NAME)
logging.getLogger("TeleBot").setLevel(logging.CRITICAL)
logging.getLogger("telebot").setLevel(logging.CRITICAL)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("comtypes").setLevel(logging.WARNING)
logging.getLogger("comtypes.client._code_cache").setLevel(logging.WARNING)

# =========================================================
# PATHS & CONFIG
# =========================================================
_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
_EMOTICON_RE = re.compile(
    r"^(?:[:;=xX8][\-^'`]?[)(DPp3oO/\\|*]+|<3+|:\)|:\(|:3|;\)|xD+|XD+|\^_\^|owo|uwu|❤+|❤️+|💖+|😂+|🤣+|👍+|🔥+|🙏+)$",
    re.IGNORECASE,
)


def _is_emoji_message(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if len(raw) > 36:
        return False
    low = raw.lower()
    if _EMOTICON_RE.match(low):
        return True
    if not _EMOJI_RE.search(raw):
        return False
    # Разрешаем только эмодзи/символы без обычных слов.
    stripped = _EMOJI_RE.sub("", raw)
    if re.search(r"[A-Za-zА-Яа-яЁё0-9]", stripped):
        return False
    return True


# =========================================================
# AUDIO DEVICE HELPERS (extracted)
# =========================================================
MIC_DEVICE_INDEX, MIC_NAME = pick_microphone_device()
if MIC_NAME:
    logger.debug(f"Selected microphone: {MIC_NAME}")
else:
    logger.warning("No microphone detected, using default.")

# =========================================================
# HELPER FUNCTIONS
# =========================================================
# Imported from jarvis_ai.response_parsing and jarvis_ai.system_actions.


def find_steam_path():
    return _find_steam_path()


def find_discord_path():
    return _find_discord_path()


def find_telegram_path():
    return _find_telegram_path()

# =========================================================
# COMMAND PARSER (улучшенный)
# =========================================================
# MAIN APPLICATION
# =========================================================
@compose_jarvis_app(settings_mixin_cls=SettingsUiMixin, emoji_detector=_is_emoji_message)
class JarvisApp(
    WorkspaceToolsMixin,
    SettingsUiMixin,
    VoicePipelineMixin,
    DiagnosticsToolsMixin,
    ChatUiMixin,
    ScrollingMixin,
    ClipboardMixin,
    UpdateFlowMixin,
):
    def __init__(self, root):
        self.app_bootstrap = AppBootstrap(config_mgr=CONFIG_MGR, prompt_mgr=PROMPT_MGR, db=db)
        self.app_bootstrap.prepare_runtime()
        self.app_context = self.app_bootstrap.build_context()
        self.config_mgr = self.app_context.config_mgr
        self.prompt_mgr = self.app_context.prompt_mgr
        self.db = self.app_context.db
        self.controllers = build_app_controllers(self)
        self.app_context.controllers = self.controllers
        self.ui_shell = self.controllers.ui_shell
        self.conversation_controller = self.controllers.conversation
        self.voice_controller = self.controllers.voice
        self.window_controller = self.controllers.window
        self.action_executor = self.controllers.actions
        Theme.apply_mode(self.config_mgr.get_theme_mode())
        self.root = root
        self.refresh_branding()
        self.root.configure(bg=Theme.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._startup_gate_setup = not bool(str(self.config_mgr.get_api_key() or "").strip())
        self.safe_mode = bool(
            self.config_mgr.get_safe_mode_enabled()
            or any(str(arg or "").strip().lower() == "--safe-mode" for arg in sys.argv[1:])
        )

        self.executor = ThreadPoolExecutor(max_workers=4)
        self.running = True
        self._ui_task_queue = queue.SimpleQueue()

        self.speaking_lock = threading.Lock()
        self.speaking = False
        self.listening_once = False
        self.manual_listen_until = 0.0
        self.processing_command = False
        self.context_lock = threading.Lock()
        self.context_messages = deque(self.db.load_context(limit=7), maxlen=7)

        self.tts_engine = None
        self.voices = []
        self._init_tts()

        self.services = build_service_hub(
            self,
            Groq,
            ReminderScheduler,
            TelegramBot,
            DiagnosticAssistant,
            telegram_enabled=not self.safe_mode,
            config_mgr=self.config_mgr,
            context=self.app_context,
        )
        self.groq_client = self.services.groq_client
        self.reminder_scheduler = self.services.reminder_scheduler
        self.telegram_bot = self.services.telegram_bot
        self.diagnostic_assistant = self.services.diagnostic_assistant
        if not self._startup_gate_setup and self.telegram_bot:
            self.telegram_bot.start()

        self.is_full = False
        self.assets = {}
        self.history_window = None
        self.status_var = tk.StringVar(value="Готов")
        self.workspace_mode_var = tk.StringVar(value="Рабочий стол")
        self.ui_rewrite = None
        self.mic_pulse_state = False
        self.last_ai_reply = ""
        self.chat_history = []
        self._chat_render_limit = 140
        self._typing_animating = False
        self._typing_tick = 0
        self._rate_apply_after = None
        self._is_quitting = False
        self._bg_anim_started = False
        self.dvd_logos = []
        self._volume_apply_after = None
        self._mic_manual_request = False
        self._mic_manual_active = False
        self._mic_click_cooldown_until = 0.0
        self._normal_geometry = self.config_mgr.get_window_geometry()
        self._mic_listen_lock = threading.Lock()
        self._mic_state_lock = threading.RLock()
        self._typing_stop_flag = False
        self._resize_timer = None
        self._bg_anim_after_id = None
        self._bg_rebuild_after_id = None
        self._settings_tab1_save_callback = None
        self._control_center_rebuild_pending = False
        self._control_center_rebuild_target = None
        self._bg_tick_ms = 54
        self._status_reset_after_id = None
        self._scroll_targets = []
        self._mousewheel_bound = False
        self._mousewheel_bound_hosts = set()
        self._active_scroll_target = None
        self._wheel_delta_accum = {}
        self._base_tk_scaling = None
        self._last_applied_dpi_scale = None
        self._chat_sync_after_id = None
        self._chat_scroll_to_end_pending = False
        self._bg_anim_paused = False
        self._bg_pause_reasons = set()
        self._current_mic_index = None
        self._process_state_lock = threading.Lock()
        self._last_self_check_fingerprint = ""
        self._last_self_check_at = 0.0
        self._session_started_at = datetime.now()
        self._background_diag_cache = []
        self._background_diag_changed_at = 0.0
        self._tts_forced_offline = False
        self._tts_provider_before_offline = ""
        self._elevenlabs_client_cached = None
        self._elevenlabs_client_key = ""
        self._pygame_audio_ready = False
        self._tts_stop_event = threading.Event()
        self._active_audio_stream = None
        self._last_bg_canvas_size = (0, 0)
        self._last_resize_signature = None
        self._last_shell_rebuild_signature = None
        self._pending_shell_rebuild = False
        self._resize_preview_after = None
        self._startup_resize_freeze_until = time.monotonic() + 0.9
        self._resize_guard_after_id = None
        self._resize_guard_visible = False
        self._tts_unavailable_notified = set()
        self._last_listen_transient_log_ts = 0.0
        self._last_listen_transient_key = ""
        self._global_clipboard_bound = False
        self._window_activity_after_id = None
        self._proxy_url_in_use = ""
        self._command_palette_window = None
        self._command_palette_actions = []
        self._command_palette_visible = []
        self._workspace_resize_in_progress = False
        self._resize_guard_hold_until = 0.0
        self._fullscreen_transition_warmed = False
        self._settings_overlay_warmed = False
        self._activation_gate_warmed = False
        try:
            setattr(self.root, "_jarvis_resize_in_progress", False)
        except Exception:
            pass

        # Индикатор интернета
        self.is_online = True
        self.net_label = None
        self._net_check_in_progress = False
        self._pending_net_status = None
        self._net_flap_times = deque(maxlen=8)
        self._last_net_warning_ts = 0.0

        # VPN/Proxy
        self._ensure_install_dirs()
        refresh_known_app_launchers()
        self._apply_proxy_env_from_config()
        self.proxy_detected = self._detect_proxy_enabled()
        if self.proxy_detected:
            self.root.after(1500, lambda: self.set_status("🌐 VPN/Proxy обнаружен — AI оптимизирован", "ok"))

        # Распознаватель
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.operation_timeout = 3.2
        self.apply_listening_profile()

        icon_path = resource_path("assets/ai_avatar.png")
        self.tray_icon = None
        self._tray_icon_path = icon_path
        self._tray_icon_started = False
        if str(self.config_mgr.get_close_behavior() or "exit").strip().lower() == "tray":
            self.create_tray_icon(icon_path)

        # Установка иконки окна
        ico_candidates = [
            resource_path("assets/иконка.ico"),
            resource_path("assets/icon.ico"),
        ]
        for ico_path in ico_candidates:
            if os.path.exists(ico_path):
                try:
                    self.root.iconbitmap(ico_path)
                    try:
                        ico_img = Image.open(ico_path)
                        self._taskbar_icon = ImageTk.PhotoImage(ico_img)
                        self.root.wm_iconphoto(True, self._taskbar_icon)
                    except Exception:
                        pass
                    break
                except tk.TclError:
                    continue

        geom = self.config_mgr.get_window_geometry()
        parsed = parse_geometry(geom) if geom else None
        self._apply_dpi_scaling()
        min_w, min_h, pref_geom = self._window_geometry_preset()
        pref_parsed = parse_geometry(pref_geom)
        if parsed and pref_parsed:
            max_w = max(pref_parsed[0], self.root.winfo_screenwidth() - 20)
            max_h = max(pref_parsed[1], self.root.winfo_screenheight() - 20)
            if min_w <= parsed[0] <= max_w and min_h <= parsed[1] <= max_h:
                self.root.geometry(geom)
                self._normal_geometry = geom
            else:
                self.root.geometry(pref_geom)
                self._normal_geometry = pref_geom
        else:
            self.root.geometry(pref_geom)
            self._normal_geometry = pref_geom
        try:
            self.root.minsize(min_w, min_h)
        except Exception:
            pass

        self.load_assets()
        self.setup_ui()
        self._ensure_activity_state()
        self.apply_theme_runtime()
        self._refresh_activity_widgets()
        self.refresh_mic_status_label()
        self.refresh_output_status_label()
        self.refresh_tts_status_label()
        self._prewarm_shell_layout()
        self.set_status("Готов", "ok")
        self.root.after(250, self.mic_pulse_tick)
        self._runtime_started = False

        self._setup_hotkey()
        atexit.register(self.shutdown)
        self.root.after(40, self._drain_ui_tasks)

        # Startup uses the dedicated registration screen when the API key is
        # missing. Background services only continue when activation is not
        # blocking startup.
        if not self._startup_gate_setup:
            self.root.after(260, self._start_runtime_services)
        self.root.after(120, self._show_window_main)

    def _start_runtime_services(self):
        if self._runtime_started:
            return
        self._runtime_started = True
        if self.telegram_bot:
            self.telegram_bot.start()
        if self.safe_mode:
            self.root.after(250, lambda: self.set_status("Безопасный режим", "warn", duration_ms=3600))
            return
        self.root.after(1800, self.check_for_updates)
        self.root.after(2600, self.update_net_status)
        self._start_background_self_check_loop()
        threading.Thread(target=self.listen_task, daemon=True, name="ListenThread").start()
        self.root.after(240, lambda: self.executor.submit(self.initial_greeting))
        self.root.after(5200, self.check_update_notification)

    def run_setup_wizard(self, activation_only: Optional[bool] = None):
        if activation_only is None:
            activation_only = bool(self._startup_gate_setup)
        activation_only = bool(activation_only)
        self._setup_wizard_window = None
        if activation_only:
            self._startup_gate_setup = True
        gate = getattr(self, "activation_gate", None)
        gate_ready = False
        if gate is not None:
            try:
                gate_ready = bool(gate.winfo_exists())
            except Exception:
                gate_ready = False
        if not gate_ready:
            self._build_embedded_activation_gate()
        self._show_embedded_activation_gate()
        self.set_status("Заполните регистрацию и ключ", "warn" if activation_only else "busy")

    def on_setup_wizard_closed(self):
        self._setup_wizard_window = None
        api_ready = bool(str(self.config_mgr.get_api_key() or "").strip())
        if self._startup_gate_setup and not api_ready:
            self.set_status("Нужна активация", "warn")
            self.root.after(100, lambda: self.run_setup_wizard(True))
            return

        if self._startup_gate_setup:
            self._startup_gate_setup = False
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass
            self._hide_embedded_activation_gate()
            if not self.safe_mode:
                self.root.after(620, self.start_bg_anim)
            self._start_runtime_services()
        
    def reload_services(self):
        # Перезагружаем Groq клиент и Telegram бот после сохранения настроек в мастере
        global MIC_DEVICE_INDEX, MIC_NAME
        cfg = self.config_mgr
        refresh_known_app_launchers()
        MIC_DEVICE_INDEX, MIC_NAME = pick_microphone_device()
        self._voice_device_refresh_requested = True
        if cfg.get_api_key() and Groq:
            try:
                ensure_httpx_proxy_compat()
                self.groq_client = Groq(api_key=cfg.get_api_key())
            except Exception as exc:
                log_event(logger, "bootstrap", "groq_client_reload_failed", level=logging.ERROR, error=str(exc))
                logger.error("Failed to reload Groq client: %s", exc, exc_info=True)
                self.groq_client = None
        else:
            self.groq_client = None
        if hasattr(self, "services"):
            self.services.groq_client = self.groq_client

        self._apply_proxy_env_from_config()
        self.proxy_detected = self._detect_proxy_enabled()
        self.apply_listening_profile(cfg.get_listening_profile())
        Theme.apply_mode(cfg.get_theme_mode())
             
        if self.telegram_bot:
            self.telegram_bot.stop()
        self.telegram_bot = None if self.safe_mode else TelegramBot(
            cfg.get_telegram_token(),
            cfg.get_telegram_user_id(),
            self.process_telegram_query,
            display_name=cfg.get_user_name(),
        )
        if self.telegram_bot:
            self.telegram_bot.start()
        if hasattr(self, "services"):
            self.services.telegram_bot = self.telegram_bot
        self.refresh_output_status_label()
        self.refresh_tts_status_label()
        
    def reset_user_data(self):
        """Полный сброс всех пользовательских данных"""
        result = messagebox.askyesno("Сброс данных", "Вы уверены, что хотите сбросить все настройки, историю и промпты? Это действие необратимо.")
        if result:
            # Удаляем конфиг
            if os.path.exists(get_config_path()):
                os.remove(get_config_path())
            # Удаляем БД
            if os.path.exists(get_db_path()):
                os.remove(get_db_path())
            # Удаляем промпты
            prompts_dir = get_prompts_dir()
            if os.path.exists(prompts_dir):
                import shutil
                shutil.rmtree(prompts_dir)
            # Сброс флага первого запуска
            CONFIG_MGR.set("first_run_done", False)
            messagebox.showinfo("Сброс выполнен", "Все данные сброшены. Приложение будет перезапущено.")
            self.quit_app()
            # Перезапуск (через 2 секунды)
            if getattr(sys, 'frozen', False):
                os.startfile(sys.executable)
            else:
                os.execl(sys.executable, sys.executable, *sys.argv)

    def _ensure_install_dirs(self):
        """Создаёт все нужные папки и даёт полные права текущему пользователю"""
        dirs = [
            app_config_dir(),
            app_data_dir(),
            app_log_dir(),
            get_prompts_dir(),
        ]
        user = os.getlogin() if sys.platform == "win32" else None
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            if sys.platform == "win32" and user:
                try:
                    subprocess.call(
                        ['icacls', d, '/grant', f'{user}:F', '/T'],
                        creationflags=CREATE_NO_WINDOW,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    logger.warning(f"icacls error for {d}: {e}")

    def _read_windows_proxy_url(self) -> str:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0] or 0)
            server = str(winreg.QueryValueEx(key, "ProxyServer")[0] or "").strip()
            winreg.CloseKey(key)
            if not enabled or not server:
                return ""
            if "=" in server:
                for chunk in server.split(";"):
                    if "=" not in chunk:
                        continue
                    proto, value = chunk.split("=", 1)
                    if proto.strip().lower() in {"https", "http", "socks", "socks5"} and value.strip():
                        server = value.strip()
                        break
            if server and not server.startswith(("http://", "https://", "socks5://")):
                server = f"http://{server}"
            return server
        except Exception:
            return ""

    def _detect_proxy_enabled(self) -> bool:
        return bool(
            os.environ.get("http_proxy")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("HTTPS_PROXY")
            or self._read_windows_proxy_url()
        )

    def _apply_proxy_env_from_config(self):
        proxy_url = str(CONFIG_MGR.get_proxy_url() or "").strip()
        if not proxy_url:
            proxy_url = self._read_windows_proxy_url()
        if proxy_url and not proxy_url.startswith(("http://", "https://", "socks5://")):
            proxy_url = f"http://{proxy_url}"
        self._proxy_url_in_use = proxy_url
        if proxy_url:
            os.environ["http_proxy"] = proxy_url
            os.environ["https_proxy"] = proxy_url
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
            os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
        else:
            for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "no_proxy", "NO_PROXY"):
                os.environ.pop(key, None)

    def _setup_hotkey(self):
        if keyboard:
            try:
                keyboard.add_hotkey('win+j', self.toggle_window)
                logger.debug("Global hotkey Win+J registered")
            except Exception as e:
                logger.error(f"Hotkey registration failed: {e}")

    def _enqueue_ui_task(self, fn, *args, **kwargs):
        try:
            self._ui_task_queue.put((fn, args, kwargs))
        except Exception:
            pass

    def _drain_ui_tasks(self):
        if not self.running:
            return
        try:
            processed = 0
            while processed < 50:
                try:
                    fn, args, kwargs = self._ui_task_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    logger.debug(f"UI task error: {e}")
                processed += 1
        finally:
            if self.running:
                self.root.after(40, self._drain_ui_tasks)

    def _tray_show(self, icon=None, item=None):
        self._enqueue_ui_task(self.show_window, icon, item)

    def _tray_quit(self, icon=None, item=None):
        self._enqueue_ui_task(self.quit_app, icon, item)

    def _tray_tips(self, icon=None, item=None):
        self._enqueue_ui_task(self.show_quick_tips)

    def create_tray_icon(self, icon_path):
        if self.tray_icon is not None:
            return self.tray_icon
        try:
            if os.path.exists(icon_path):
                image = Image.open(icon_path)
            else:
                image = Image.new('RGBA', (64,64), (0,0,0,0))
            self.tray_icon = pystray.Icon(
                "jarvis",
                image,
                app_title(with_version=True),
                menu=pystray.Menu(
                    trayMenuItem("Показать", self._tray_show, default=True),
                    trayMenuItem("Подсказки", self._tray_tips),
                    trayMenuItem("Выход", self._tray_quit)
                )
            )
            threading.Thread(target=self.tray_icon.run, daemon=True, name="TrayIconThread").start()
            self._tray_icon_started = True
        except Exception as e:
            logger.error(f"Tray error: {e}")
        return self.tray_icon

    def _configure_ttk_styles(self):
        try:
            style = ttk.Style()
            style.theme_use("clam")
            style.configure("TFrame", background=Theme.BG_LIGHT)
            style.configure("TLabel", background=Theme.BG_LIGHT, foreground=Theme.FG)
            style.configure(
                "TButton",
                background=Theme.BUTTON_BG,
                foreground=Theme.FG,
                borderwidth=0,
                focuscolor="none",
            )
            style.map("TButton", background=[("active", Theme.ACCENT)])

            style.configure("Jarvis.TNotebook", background=Theme.BG_LIGHT, borderwidth=0)
            style.configure(
                "Jarvis.TNotebook.Tab",
                background=Theme.BUTTON_BG,
                foreground=Theme.FG,
                padding=(18, 10),
                borderwidth=0,
                font=("Segoe UI Semibold", 12),
            )
            style.map(
                "Jarvis.TNotebook.Tab",
                background=[("selected", Theme.ACCENT), ("active", Theme.CARD_BG)],
                foreground=[("selected", Theme.FG), ("active", Theme.FG)],
            )

            style.configure(
                "Jarvis.TCombobox",
                fieldbackground=Theme.INPUT_BG,
                background=Theme.BUTTON_BG,
                foreground=Theme.FG,
                arrowcolor=Theme.FG,
                bordercolor=Theme.INPUT_BORDER,
                lightcolor=Theme.INPUT_BORDER,
                darkcolor=Theme.INPUT_BORDER,
                insertcolor=Theme.FG,
                font=("Segoe UI", 12),
            )
            style.map(
                "Jarvis.TCombobox",
                fieldbackground=[("readonly", Theme.INPUT_BG)],
                foreground=[("readonly", Theme.FG)],
                selectbackground=[("readonly", Theme.INPUT_BG)],
                selectforeground=[("readonly", Theme.FG)],
                background=[("readonly", Theme.BUTTON_BG)],
            )
            try:
                self.root.option_add("*TCombobox*Listbox.background", Theme.INPUT_BG)
                self.root.option_add("*TCombobox*Listbox.foreground", Theme.FG)
                self.root.option_add("*TCombobox*Listbox.selectBackground", Theme.ACCENT)
                self.root.option_add("*TCombobox*Listbox.selectForeground", Theme.FG)
                self.root.option_add("*TCombobox*Listbox.font", "Segoe UI 12")
            except Exception:
                pass

            style.configure(
                "Jarvis.Vertical.TScrollbar",
                background=Theme.BUTTON_BG,
                troughcolor=Theme.BG_LIGHT,
                bordercolor=Theme.BORDER,
                arrowcolor=Theme.FG,
                relief="flat",
            )
            style.map("Jarvis.Vertical.TScrollbar", background=[("active", Theme.ACCENT)])
        except Exception as e:
            logger.debug(f"TTK style apply error: {e}")

    def _bind_hover_bg(self, widget, role: str = "button"):
        def _base():
            if role == "input_icon":
                return Theme.BUTTON_BG
            return Theme.BUTTON_BG

        def _hover():
            if role in {"chip", "input_icon"}:
                return Theme.ACCENT
            return Theme.ACCENT

        def on_enter(_=None):
            try:
                widget.configure(bg=_hover())
            except Exception:
                pass

        def on_leave(_=None):
            try:
                widget.configure(bg=_base())
            except Exception:
                pass

        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        on_leave()

    def _bind_guide_hover(self, widget, section: str):
        def _enter(_=None):
            try:
                self._update_guide_context(section)
            except Exception:
                pass

        def _leave(_=None):
            try:
                self._update_guide_context()
            except Exception:
                pass

        try:
            widget.bind("<Enter>", _enter, add="+")
            widget.bind("<Leave>", _leave, add="+")
        except Exception:
            pass

    def _restyle_settings_window(self):
        surfaces = []
        for attr in ("settings_window", "embedded_settings_page", "quick_settings_panel"):
            win = getattr(self, attr, None)
            if not win:
                continue
            try:
                if win.winfo_exists():
                    surfaces.append(win)
            except Exception:
                continue
        if not surfaces:
            return

        danger_bgs = {"#7f1d1d", "#aa2222"}
        danger_fgs = {"#f8fafc"}

        def _parent_bg(widget, fallback=Theme.BG_LIGHT):
            parent = getattr(widget, "master", None)
            while parent is not None:
                try:
                    raw = parent.cget("bg")
                except Exception:
                    parent = getattr(parent, "master", None)
                    continue
                mapped = Theme.resolve_color(raw, role="bg")
                return mapped or str(raw or "").strip() or fallback
            return fallback

        def visit(widget):
            try:
                if isinstance(widget, tk.Frame):
                    current = str(widget.cget("bg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current, role="bg")
                    widget.configure(bg=mapped_bg or _parent_bg(widget))
                    try:
                        widget.configure(highlightbackground=Theme.BORDER)
                    except Exception:
                        pass
                elif isinstance(widget, tk.Label):
                    current_bg = str(widget.cget("bg")).strip().lower()
                    current_fg = str(widget.cget("fg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current_bg, role="bg")
                    mapped_fg = Theme.resolve_color(current_fg, role="fg")
                    widget.configure(
                        bg=mapped_bg or _parent_bg(widget),
                        fg=mapped_fg or Theme.FG,
                    )
                elif isinstance(widget, tk.Button):
                    current_bg = str(widget.cget("bg")).strip().lower()
                    current_fg = str(widget.cget("fg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current_bg, role="bg")
                    mapped_fg = Theme.resolve_color(current_fg, role="fg")
                    final_bg = current_bg if current_bg in danger_bgs else (mapped_bg or current_bg or Theme.BUTTON_BG)
                    final_fg = current_fg if current_fg in danger_fgs else (mapped_fg or Theme.FG)
                    widget.configure(
                        bg=final_bg,
                        fg=final_fg,
                        activebackground=Theme.ACCENT,
                        activeforeground=final_fg if final_bg in danger_bgs else Theme.FG,
                        highlightbackground=Theme.BORDER,
                    )
                elif isinstance(widget, tk.Entry):
                    widget.configure(
                        bg=Theme.INPUT_BG,
                        fg=Theme.FG,
                        insertbackground=Theme.FG,
                        readonlybackground=Theme.INPUT_BG,
                        disabledbackground=Theme.INPUT_BG,
                    )
                elif isinstance(widget, tk.Text):
                    widget.configure(
                        bg=Theme.INPUT_BG,
                        fg=Theme.FG,
                        insertbackground=Theme.FG,
                        highlightbackground=Theme.BORDER,
                        highlightcolor=Theme.ACCENT,
                    )
                elif isinstance(widget, tk.Listbox):
                    widget.configure(
                        bg=Theme.INPUT_BG,
                        fg=Theme.FG,
                        selectbackground=Theme.ACCENT,
                        selectforeground=Theme.FG,
                        highlightthickness=0,
                        bd=0,
                    )
                elif isinstance(widget, tk.Checkbutton):
                    current_fg = str(widget.cget("fg")).strip().lower()
                    mapped_fg = Theme.resolve_color(current_fg, role="fg")
                    bg = _parent_bg(widget, fallback=Theme.CARD_BG)
                    widget.configure(
                        bg=bg,
                        fg=mapped_fg or Theme.FG,
                        activebackground=bg,
                        activeforeground=mapped_fg or Theme.FG,
                        selectcolor=Theme.INPUT_BG,
                    )
                elif isinstance(widget, tk.Canvas):
                    current = str(widget.cget("bg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current, role="bg")
                    widget.configure(bg=mapped_bg or _parent_bg(widget), highlightbackground=Theme.BORDER)
                elif isinstance(widget, tk.Scale):
                    bg = _parent_bg(widget, fallback=Theme.CARD_BG)
                    widget.configure(
                        bg=bg,
                        fg=Theme.FG,
                        troughcolor=Theme.BUTTON_BG,
                        activebackground=Theme.ACCENT,
                    )
                elif isinstance(widget, tk.Scrollbar):
                    widget.configure(
                        bg=Theme.BUTTON_BG,
                        activebackground=Theme.ACCENT,
                        troughcolor=Theme.BG_LIGHT,
                        relief="flat",
                        bd=0,
                        highlightthickness=0,
                    )
            except Exception:
                pass
            for child in widget.winfo_children():
                visit(child)

        for win in surfaces:
            visit(win)

    def _sync_chat_scroll_region(self):
        if not hasattr(self, "chat_canvas"):
            return
        try:
            bbox = self.chat_canvas.bbox("all")
            if bbox:
                self.chat_canvas.configure(scrollregion=bbox)
        except Exception:
            pass

    def _flush_chat_layout_sync(self):
        self._chat_sync_after_id = None
        self._sync_chat_scroll_region()
        if getattr(self, "_chat_scroll_to_end_pending", False):
            try:
                self.chat_canvas.yview_moveto(1.0)
            except Exception:
                pass
        self._chat_scroll_to_end_pending = False

    def _schedule_chat_layout_sync(self, scroll_to_end: bool = False):
        if scroll_to_end:
            self._chat_scroll_to_end_pending = True
        if getattr(self, "_chat_sync_after_id", None) is not None:
            return
        try:
            self._chat_sync_after_id = self.root.after_idle(self._flush_chat_layout_sync)
        except Exception:
            self._flush_chat_layout_sync()

    def _trim_chat_render_cache(self):
        limit = max(40, int(getattr(self, "_chat_render_limit", 140) or 140))
        if len(self.chat_history) > limit:
            self.chat_history = self.chat_history[-limit:]
        if not hasattr(self, "chat_frame"):
            return
        children = list(self.chat_frame.winfo_children())
        extra = len(children) - limit
        if extra <= 0:
            return
        for child in children[:extra]:
            try:
                child.destroy()
            except Exception:
                pass

    def _window_geometry_preset(self) -> Tuple[int, int, str]:
        try:
            sw = max(int(self.root.winfo_screenwidth() or 0), 640)
            sh = max(int(self.root.winfo_screenheight() or 0), 480)
        except Exception:
            sw, sh = 1366, 768
        usable_w = max(480, sw - 12)
        usable_h = max(360, sh - 18)
        min_w = min(860, usable_w)
        min_h = min(640, usable_h)
        pref_w = min(1600, usable_w)
        pref_h = min(1040, usable_h)
        pref_w = max(min_w, pref_w)
        pref_h = max(min_h, pref_h)
        x = max((sw - pref_w) // 2, 0)
        y = max((sh - pref_h) // 2, 0)
        return min_w, min_h, f"{pref_w}x{pref_h}+{x}+{y}"

    def _main_container_target_size(self) -> Tuple[int, int]:
        try:
            root_w = max(int(self.root.winfo_width() or 0), 1)
            root_h = max(int(self.root.winfo_height() or 0), 1)
        except Exception:
            return 1280, 860
        return root_w, root_h

    def _apply_main_container_bounds(self):
        if not hasattr(self, "main_container"):
            return
        try:
            root_w = max(int(self.root.winfo_width() or 0), 1)
            root_h = max(int(self.root.winfo_height() or 0), 1)
            cont_w, cont_h = self._main_container_target_size()
            bounds_signature = (root_w, root_h, cont_w, cont_h)
            if bounds_signature == getattr(self, "_last_main_container_bounds", None):
                return
            if isinstance(getattr(self, "bg_canvas", None), tk.Canvas) and hasattr(self, "cont_win"):
                self.bg_canvas.coords(self.cont_win, 0, 0)
                self.bg_canvas.itemconfigure(self.cont_win, width=cont_w, height=cont_h)
            else:
                try:
                    self.main_container.configure(width=cont_w, height=cont_h)
                except Exception:
                    pass
            self._last_main_container_bounds = bounds_signature
        except Exception:
            return
        try:
            self._sync_chat_canvas_width()
        except Exception:
            pass

    def _show_resize_guard(self):
        # The resize guard was causing an invisible overlay during window changes.
        # Disable the overlay and rely on native Tkinter resizing behavior.
        return

    def _hide_resize_guard(self):
        guard = getattr(self, "_resize_guard", None)
        if guard is not None:
            try:
                guard.place_forget()
            except Exception:
                pass
        self._resize_guard_visible = False
        self._resize_guard_hold_until = 0.0

    def _hold_resize_guard(self, hold_ms: int = 120):
        self._hide_resize_guard()

    def _prewarm_shell_layout(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self._apply_main_container_bounds()
        except Exception:
            pass
        try:
            self._sync_chat_canvas_width()
        except Exception:
            pass
        try:
            self.refresh_workspace_layout_mode()
        except Exception:
            pass
        try:
            self._refresh_chat_empty_state()
        except Exception:
            pass

    def _prime_after_visual_transition(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self._apply_main_container_bounds()
        except Exception:
            pass
        try:
            self._sync_chat_canvas_width()
        except Exception:
            pass
        try:
            self.refresh_workspace_layout_mode()
        except Exception:
            pass
        try:
            if hasattr(self, "_schedule_settings_visual_refresh") and self._is_full_settings_open():
                self._schedule_settings_visual_refresh()
        except Exception:
            pass
        try:
            if hasattr(self, "_refresh_activation_gate_layout") and getattr(self, "_startup_gate_setup", False):
                self._refresh_activation_gate_layout()
        except Exception:
            pass

    def _handle_window_map(self, _event=None):
        if not bool(getattr(self, "_needs_visual_prime_after_map", False)):
            return
        try:
            state_name = str(self.root.state() or "").lower()
        except Exception:
            state_name = "normal"
        if state_name in {"iconic", "withdrawn"}:
            return
        self._needs_visual_prime_after_map = False
        try:
            self._last_resize_signature = None
        except Exception:
            pass
        try:
            self.root.after(18, self._prime_after_visual_transition)
            self.root.after(72, self._prime_after_visual_transition)
        except Exception:
            pass

    def _handle_window_unmap(self, _event=None):
        self._needs_visual_prime_after_map = True
        try:
            self._hide_resize_guard()
        except Exception:
            pass

    def _sync_chat_canvas_width(self, width: Optional[int] = None):
        if not hasattr(self, "chat_canvas") or not hasattr(self, "chat_window_id"):
            return
        try:
            current = int(width if width is not None else self.chat_canvas.winfo_width())
            target = max(320, current - 6)
            self.chat_canvas.itemconfigure(self.chat_window_id, width=target)
        except Exception:
            pass
        self._sync_chat_scroll_region()

    def _detect_runtime_theme_mode(self) -> str:
        try:
            bg = str(self.root.cget("bg") or "").strip().lower()
            if bg == Theme.PALETTES["light"]["BG"].lower():
                return "light"
            if bg == Theme.PALETTES["dark"]["BG"].lower():
                return "dark"
        except Exception:
            pass
        mode = str(self.config_mgr.get_theme_mode() or "dark").strip().lower()
        return mode if mode in {"dark", "light"} else "dark"

    def _refresh_chat_theme(self):
        if not hasattr(self, "chat_frame"):
            return
        history = list(getattr(self, "chat_history", []))
        if history:
            for child in self.chat_frame.winfo_children():
                child.destroy()
            for item in history:
                self._render_chat_message(
                    item.get("text", ""),
                    sender=item.get("sender", "bot"),
                    time_text=item.get("time", datetime.now().strftime("%H:%M")),
                    store=False,
                )
        try:
            self._sync_chat_canvas_width()
            self.chat_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _header_subtitle_text(self) -> str:
        user_name = str(self.config_mgr.get_user_name() or "").strip()
        base = "Чистый рабочий стол для чата, голоса и быстрых команд"
        if user_name:
            return f"{base} • профиль: {user_name}"
        return base

    def refresh_branding(self):
        try:
            self.root.title(app_title(with_version=True))
        except Exception:
            pass
        try:
            if hasattr(self, "title_label"):
                self.title_label.configure(text=app_brand_name())
            if hasattr(self, "version_label"):
                self.version_label.configure(text=app_version_badge())
            if hasattr(self, "subtitle_label"):
                self.subtitle_label.configure(text=self._header_subtitle_text())
        except Exception:
            pass

    def apply_theme_runtime(self):
        Theme.apply_mode(self.config_mgr.get_theme_mode())
        try:
            self.root.configure(bg=Theme.BG)
        except Exception:
            return

        self._configure_ttk_styles()

        for widget_name, bg_color in (
            ("bg_canvas", Theme.BG),
            ("main_container", Theme.BG_LIGHT),
            ("shell", Theme.BG_LIGHT),
            ("workspace", Theme.BG_LIGHT),
            ("sidebar", Theme.CARD_BG),
            ("side_panel", Theme.BG_LIGHT),
            ("content_stage", Theme.BG_LIGHT),
            ("chat_shell", Theme.CARD_BG),
            ("chat_header", Theme.CARD_BG),
            ("chat_canvas", Theme.BG_LIGHT),
            ("chat_frame", Theme.BG_LIGHT),
            ("top_bar", Theme.CARD_BG),
            ("top_left", Theme.CARD_BG),
            ("top_right", Theme.CARD_BG),
            ("brand_row", Theme.CARD_BG),
            ("status_grid", Theme.CARD_BG),
            ("net_chip", Theme.BUTTON_BG),
            ("mic_chip", Theme.BUTTON_BG),
            ("output_chip", Theme.BUTTON_BG),
            ("tts_chip", Theme.BUTTON_BG),
            ("quick_bar", Theme.CARD_BG),
            ("quick_head", Theme.CARD_BG),
            ("quick_inner", Theme.CARD_BG),
            ("controls_bar", Theme.BG_LIGHT),
            ("entry_wrap", Theme.CARD_BG),
            ("activation_gate", Theme.CARD_BG),
        ):
            w = getattr(self, widget_name, None)
            if w is None:
                continue
            try:
                w.configure(bg=bg_color)
            except Exception:
                pass

        try:
            self.main_container.configure(highlightbackground=Theme.BORDER)
        except Exception:
            pass
        try:
            if hasattr(self, "top_bar"):
                self.top_bar.configure(highlightbackground=Theme.BORDER)
        except Exception:
            pass
        for widget_name in ("sidebar", "net_chip", "mic_chip", "output_chip", "tts_chip", "adaptation_chip", "quick_bar", "entry_wrap"):
            w = getattr(self, widget_name, None)
            if w is None:
                continue
            try:
                w.configure(highlightbackground=Theme.BORDER)
            except Exception:
                pass
        try:
            if hasattr(self, "chat_shell"):
                self.chat_shell.configure(highlightbackground=Theme.BORDER)
        except Exception:
            pass
        try:
            if hasattr(self, "top_divider"):
                self.top_divider.configure(bg=Theme.BORDER)
        except Exception:
            pass

        try:
            if hasattr(self, "entry"):
                self.entry.configure(bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG)
        except Exception:
            pass

        for btn in getattr(self, "header_action_buttons", []):
            try:
                btn.configure(bg=Theme.BUTTON_BG, fg=Theme.FG)
            except Exception:
                pass
        for btn in getattr(self, "sidebar_action_buttons", []):
            try:
                mapped_bg = Theme.resolve_color(str(btn.cget("bg")), role="bg") or Theme.BUTTON_BG
                btn.configure(bg=mapped_bg, fg=Theme.FG, highlightbackground=Theme.BORDER)
            except Exception:
                pass
        for btn in getattr(self, "sidebar_mode_buttons", []):
            try:
                btn.configure(bg=Theme.CARD_BG, fg=Theme.FG, highlightbackground=Theme.BORDER)
            except Exception:
                pass
        for btn in getattr(self, "quick_action_buttons", []):
            try:
                mapped_bg = Theme.resolve_color(str(btn.cget("bg")), role="bg") or Theme.BUTTON_BG
                btn.configure(bg=mapped_bg, fg=Theme.FG, highlightbackground=Theme.BORDER)
            except Exception:
                pass
        for btn in getattr(self, "rail_action_buttons", []):
            try:
                mapped_bg = Theme.resolve_color(str(btn.cget("bg")), role="bg") or Theme.BUTTON_BG
                btn.configure(bg=mapped_bg, fg=Theme.FG, highlightbackground=Theme.BORDER)
            except Exception:
                pass

        for name in ("copy_btn", "paste_btn", "send_btn"):
            w = getattr(self, name, None)
            if w is None:
                continue
            try:
                w.configure(bg=Theme.BUTTON_BG, fg=Theme.FG)
            except Exception:
                pass

        try:
            active = self._is_manual_listen_active()
            if not active and getattr(self, "mic_btn", None):
                self.mic_btn.configure(bg=Theme.BUTTON_BG, fg=Theme.MIC_ICON_FG, highlightbackground=Theme.BORDER)
        except Exception:
            pass

        for widget_name, bg_color in (
            ("status_label", Theme.CARD_BG),
            ("net_label", Theme.BUTTON_BG),
            ("mic_status_label", Theme.BUTTON_BG),
            ("output_status_label", Theme.BUTTON_BG),
            ("tts_status_label", Theme.BUTTON_BG),
            ("quick_title_label", Theme.CARD_BG),
            ("quick_desc_label", Theme.CARD_BG),
            ("chat_hint_label", Theme.CARD_BG),
            ("workspace_mode_badge", Theme.BUTTON_BG),
            ("side_tip_label", Theme.BUTTON_BG),
        ):
            w = getattr(self, widget_name, None)
            if w is None:
                continue
            try:
                if widget_name == "net_label":
                    w.configure(bg=bg_color, fg=Theme.ONLINE if self.is_online else Theme.OFFLINE)
                elif widget_name == "quick_title_label":
                    w.configure(bg=bg_color, fg=Theme.FG)
                elif widget_name in {"quick_desc_label", "chat_hint_label", "side_tip_label"}:
                    w.configure(bg=bg_color, fg=Theme.FG_SECONDARY)
                elif widget_name == "workspace_mode_badge":
                    w.configure(bg=bg_color, fg=Theme.FG_SECONDARY)
                else:
                    w.configure(bg=bg_color, fg=Theme.FG_SECONDARY)
            except Exception:
                pass
        try:
            if hasattr(self, "title_label"):
                self.title_label.configure(bg=Theme.CARD_BG, fg=Theme.FG)
        except Exception:
            pass
        try:
            if hasattr(self, "subtitle_label"):
                self.subtitle_label.configure(bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY)
            if hasattr(self, "version_label"):
                self.version_label.configure(bg=Theme.ACCENT, fg=Theme.FG)
        except Exception:
            pass

        self.refresh_branding()
        try:
            if hasattr(self, "guide_panel") and self.guide_panel:
                self.guide_panel.apply_theme()
        except Exception:
            pass
        for label in getattr(self, "side_status_labels", []):
            try:
                label.configure(bg=Theme.BUTTON_BG, fg=Theme.FG_SECONDARY, highlightbackground=Theme.BORDER)
            except Exception:
                pass

        self._refresh_chat_theme()
        self._refresh_chat_empty_state()
        self._restyle_settings_window()
        self._restyle_workspace_surface()

        if hasattr(self, "dvd_logos") and self.dvd_logos:
            for logo in list(self.dvd_logos):
                try:
                    logo.apply_theme()
                except Exception:
                    pass

    def _restyle_workspace_surface(self):
        root = getattr(self, "main_container", None)
        if root is None:
            return

        def visit(widget):
            try:
                if isinstance(widget, tk.Frame):
                    current = str(widget.cget("bg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current, role="bg")
                    widget.configure(bg=mapped_bg or current or Theme.BG_LIGHT)
                    try:
                        widget.configure(highlightbackground=Theme.BORDER)
                    except Exception:
                        pass
                elif isinstance(widget, tk.Label):
                    current_bg = str(widget.cget("bg")).strip().lower()
                    current_fg = str(widget.cget("fg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current_bg, role="bg")
                    mapped_fg = Theme.resolve_color(current_fg, role="fg")
                    widget.configure(bg=mapped_bg or current_bg or Theme.CARD_BG, fg=mapped_fg or Theme.FG)
                elif isinstance(widget, tk.Button):
                    current_bg = str(widget.cget("bg")).strip().lower()
                    current_fg = str(widget.cget("fg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current_bg, role="bg")
                    mapped_fg = Theme.resolve_color(current_fg, role="fg")
                    widget.configure(
                        bg=mapped_bg or Theme.BUTTON_BG,
                        fg=mapped_fg or Theme.FG,
                        highlightbackground=Theme.BORDER,
                    )
                elif isinstance(widget, tk.Entry):
                    widget.configure(bg=Theme.INPUT_BG, fg=Theme.FG, insertbackground=Theme.FG)
                elif isinstance(widget, tk.Canvas):
                    current = str(widget.cget("bg")).strip().lower()
                    mapped_bg = Theme.resolve_color(current, role="bg")
                    widget.configure(bg=mapped_bg or Theme.BG_LIGHT)
            except Exception:
                pass
            for child in widget.winfo_children():
                visit(child)

        try:
            visit(root)
        except Exception:
            pass

    def _show_window_main(self):
        try:
            try:
                current_state = str(self.root.state() or "").lower()
            except Exception:
                current_state = "normal"
            was_hidden = current_state in {"withdrawn", "iconic"}

            if not self.is_full:
                try:
                    min_w, min_h, pref_geom = self._window_geometry_preset()
                    if was_hidden:
                        geom = self._normal_geometry
                        parsed = parse_geometry(geom) if geom else None
                        if not parsed or parsed[0] < min_w or parsed[1] < min_h:
                            geom = pref_geom
                        if geom and geom != self.root.geometry():
                            self.root.geometry(geom)
                    else:
                        current_w = int(self.root.winfo_width() or 0)
                        current_h = int(self.root.winfo_height() or 0)
                        if current_w < min_w or current_h < min_h:
                            self.root.geometry(pref_geom)
                except Exception:
                    pass
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            if was_hidden:
                if not getattr(self, "_window_shown_once", False):
                    self._hold_resize_guard(110)
                    self._prewarm_shell_layout()
                self.root.deiconify()
                if current_state == "iconic":
                    self.root.state("normal")
                try:
                    self.root.update_idletasks()
                except Exception:
                    pass
            self.root.lift()
            if was_hidden:
                self.root.focus_force()
            self._window_shown_once = True
            self._prime_after_visual_transition()
            if getattr(self, "_resize_guard_visible", False):
                try:
                    self.root.after(24, self._hide_resize_guard)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Show window error: {e}")

    def show_window(self, icon=None, item=None):
        if threading.current_thread() is not threading.main_thread():
            self._enqueue_ui_task(self.show_window, icon, item)
            return
        if self._startup_gate_setup and not bool(str(self.config_mgr.get_api_key() or "").strip()):
            self.root.after(0, self._show_window_main)
            self.root.after(0, lambda: self.run_setup_wizard(True))
            return
        try:
            self.root.after(0, self._show_window_main)
        except Exception:
            self._show_window_main()

    def _get_microphone_devices(self, refresh: bool = False):
        names = list_microphone_names_safe(refresh=refresh)
        return names

    def _get_input_device_entries(self, refresh: bool = False):
        return list_input_device_entries_safe(refresh=refresh)

    def _get_output_device_entries(self, refresh: bool = False):
        return list_output_device_entries_safe(refresh=refresh)

    def _device_name_score(self, name: str, kind: str = "input") -> int:
        low = str(name or "").strip().lower().replace("ё", "е")
        if not low:
            return -100
        score = 0
        if _is_audio_garbage_name(low):
            score -= 50
        input_tokens = (
            "микрофон",
            "microphone",
            "mic",
            "input",
            "вход",
            "headset",
            "гарнитура",
            "logitech",
            "hyperx",
            "steelseries",
            "g435",
            "g pro x",
            "realtek",
            "wireless",
            "usb",
        )
        output_tokens = (
            "динам",
            "speaker",
            "speakers",
            "headset",
            "earphone",
            "науш",
            "output",
            "realtek",
            "logitech",
            "headphones",
            "g435",
            "колон",
            "bluetooth",
            "wireless",
            "станци",
        )
        negative_input_tokens = (
            "output",
            "speaker",
            "speakers",
            "динам",
            "render",
            "line out",
            "выход",
            "hdmi",
            "spdif",
            "назначение звуков",
            "переназнач",
            "line in",
            "line input",
            "stereo mix",
            "digital output",
        )
        negative_output_tokens = (
            "microphone",
            "mic",
            "input",
            "вход",
            "запись",
            "capture",
            "line in",
            "stereo mix",
            "переназнач",
            "digital output",
            "spdif",
            "hdmi",
        )
        if kind == "input":
            score += sum(3 for token in input_tokens if token in low)
            score -= sum(4 for token in negative_input_tokens if token in low)
        else:
            score += sum(3 for token in output_tokens if token in low)
            score -= sum(4 for token in negative_output_tokens if token in low)
        if kind == "input":
            if "bluetooth" in low or "hands-free" in low:
                score += 1
        elif "hands-free" in low or "hf audio" in low:
            score -= 7
        family = _audio_device_family_key(name)
        if len(family) <= 2:
            score -= 10
        if len(low) > 72:
            score -= 1
        return score

    def _device_entry_score(self, item: Optional[Dict[str, Any]], kind: str = "input") -> int:
        if not item:
            return -1000
        base_name = item.get("clean_name") or item.get("name") or ""
        score = self._device_name_score(base_name, kind=kind)
        if _is_secondary_audio_choice(base_name, kind=kind):
            score -= 12
        score += int(item.get("host_api_priority", 0) or 0) // 30
        if kind == "input":
            if item.get("is_default_input"):
                score += 8
            score += min(int(item.get("max_input_channels", 0) or 0), 2)
        else:
            if item.get("is_default_output"):
                score += 8
            score += min(int(item.get("max_output_channels", 0) or 0), 2)
        return score

    def _format_audio_option_label(self, item: Dict[str, Any], kind: str = "input") -> str:
        base = _expand_audio_device_name(item.get("name") or item.get("clean_name"), kind)
        host = _host_api_short_label(item.get("host_api"))
        if base and host:
            return f"{base} [{host}]"
        return base or (host if host else "Не найдено")

    def _microphone_names_for_settings(self, _names: List[str]) -> List[Tuple[Optional[int], str]]:
        result: List[Tuple[Optional[int], str]] = [(None, "Авто — лучший доступный микрофон")]
        selected_idx = CONFIG_MGR.get_mic_device_index()
        entries = self._get_input_device_entries(refresh=False)
        if not entries:
            return result
        family_best: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            label = self._format_audio_option_label(item, kind="input")
            if not label or _is_audio_garbage_name(label):
                continue
            item_idx = int(item.get("index", -1) or -1)
            if _is_secondary_audio_choice(label, kind="input") and item_idx != int(selected_idx if selected_idx is not None else -999):
                continue
            family = item.get("family") or _audio_device_family_key(label) or f"input-{item.get('index')}"
            current = family_best.get(family)
            if current is None or self._device_entry_score(item, "input") > self._device_entry_score(current, "input"):
                family_best[family] = item
        ranked = sorted(
            family_best.values(),
            key=lambda item: (-self._device_entry_score(item, "input"), len(item.get("clean_name") or item.get("name") or ""), int(item.get("index", 0) or 0)),
        )
        kept_families = []
        for item in ranked:
            idx = int(item.get("index", 0) or 0)
            label = self._format_audio_option_label(item, kind="input")
            score = self._device_entry_score(item, "input")
            if score <= 0 and idx != selected_idx:
                continue
            family = item.get("family") or _audio_device_family_key(label)
            if family and any(family in prev or prev in family for prev in kept_families):
                continue
            result.append((idx, label))
            if family:
                kept_families.append(family)
        if selected_idx is not None and all(idx != selected_idx for idx, _ in result[1:]):
            selected_item = _get_audio_device_entry(selected_idx, refresh=False)
            if selected_item and int(selected_item.get("max_input_channels", 0) or 0) > 0:
                result.append((int(selected_item["index"]), self._format_audio_option_label(selected_item, kind="input")))
        return result

    def _output_options_for_settings(self) -> List[Tuple[Optional[int], str]]:
        result: List[Tuple[Optional[int], str]] = [(None, "По умолчанию Windows")]
        selected_idx = CONFIG_MGR.get_output_device_index()
        entries = self._get_output_device_entries(refresh=False)
        if not entries:
            return result
        family_best: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            label = self._format_audio_option_label(item, kind="output")
            if not label or _is_audio_garbage_name(label):
                continue
            item_idx = int(item.get("index", -1) or -1)
            if _is_secondary_audio_choice(label, kind="output") and item_idx != int(selected_idx if selected_idx is not None else -999):
                continue
            family = item.get("family") or _audio_device_family_key(label) or f"output-{item.get('index')}"
            current = family_best.get(family)
            if current is None or self._device_entry_score(item, "output") > self._device_entry_score(current, "output"):
                family_best[family] = item
        ranked = sorted(
            family_best.values(),
            key=lambda item: (-self._device_entry_score(item, "output"), len(item.get("clean_name") or item.get("name") or ""), int(item.get("index", 0) or 0)),
        )
        kept_families = []
        for item in ranked:
            idx = int(item.get("index", 0) or 0)
            label = self._format_audio_option_label(item, kind="output")
            score = self._device_entry_score(item, "output")
            if score <= 0 and idx != selected_idx:
                continue
            family = item.get("family") or _audio_device_family_key(label)
            if family and any(family in prev or prev in family for prev in kept_families):
                continue
            result.append((idx, label))
            if family:
                kept_families.append(family)
        if selected_idx is not None and all(idx != selected_idx for idx, _ in result[1:]):
            selected_item = _get_audio_device_entry(selected_idx, refresh=False)
            if selected_item and int(selected_item.get("max_output_channels", 0) or 0) > 0:
                result.append((int(selected_item["index"]), self._format_audio_option_label(selected_item, kind="output")))
        return result

    def _get_output_devices(self, refresh: bool = False):
        names = list_output_device_names_safe(refresh=refresh)
        return names

    def get_selected_output_device_index(self, use_default: bool = False):
        entries = self._get_output_device_entries(refresh=False)
        stored_signature = str(CONFIG_MGR.get_output_device_signature() or "").strip()
        if stored_signature:
            matched = _find_audio_device_entry_by_signature(stored_signature, kind="output", refresh=False)
            if matched is not None:
                return int(matched.get("index", 0) or 0)
        stored = (CONFIG_MGR.get_output_device_name() or "").strip()
        if stored:
            matched = _find_audio_device_entry_by_name(stored, kind="output", refresh=False)
            if matched is not None:
                return int(matched.get("index", 0) or 0)
        idx = CONFIG_MGR.get_output_device_index()
        if idx is not None and not stored_signature:
            try:
                idx = int(idx)
                matched_by_idx = next((item for item in entries if int(item.get("index", -1)) == idx), None)
                if matched_by_idx is not None:
                    clean_name = _expand_audio_device_name(matched_by_idx.get("name"), "output")
                    if clean_name and not _is_audio_garbage_name(clean_name):
                        return idx
            except Exception:
                pass
        if use_default:
            default_item = next((item for item in entries if item.get("is_default_output")), None)
            if default_item is None:
                auto_idx, _auto_name = pick_output_device()
                if auto_idx is not None:
                    return auto_idx
            if default_item is None and entries:
                ranked = sorted(entries, key=lambda item: (-self._device_entry_score(item, "output"), int(item.get("index", 0) or 0)))
                default_item = ranked[0] if ranked else None
            if default_item is not None:
                return int(default_item.get("index", 0) or 0)
        return None

    def get_selected_microphone_index(self):
        entries = self._get_input_device_entries(refresh=False)
        stored_signature = str(CONFIG_MGR.get_mic_device_signature() or "").strip()
        if stored_signature:
            matched = _find_audio_device_entry_by_signature(stored_signature, kind="input", refresh=False)
            if matched is not None:
                return int(matched.get("index", 0) or 0)
        stored = (CONFIG_MGR.get_mic_device_name() or "").strip()
        if stored:
            matched = _find_audio_device_entry_by_name(stored, kind="input", refresh=False)
            if matched is not None:
                return int(matched.get("index", 0) or 0)
        idx = CONFIG_MGR.get_mic_device_index()
        if idx is not None and not stored_signature:
            try:
                idx = int(idx)
                matched_by_idx = next((item for item in entries if int(item.get("index", -1)) == idx), None)
                if matched_by_idx is not None:
                    current_name = _expand_audio_device_name(matched_by_idx.get("name"), "input")
                    if current_name and not _is_audio_garbage_name(current_name):
                        return idx
            except Exception:
                pass
        if MIC_DEVICE_INDEX is not None:
            try:
                matched_auto = next((item for item in entries if int(item.get("index", -1)) == int(MIC_DEVICE_INDEX)), None)
                if matched_auto is not None:
                    current_name = _expand_audio_device_name(matched_auto.get("name"), "input")
                    if current_name and not _is_audio_garbage_name(current_name):
                        return int(MIC_DEVICE_INDEX)
            except Exception:
                pass
        auto_idx, auto_name = pick_microphone_device()
        if auto_idx is not None and auto_name and not _is_audio_garbage_name(auto_name):
            return auto_idx
        return None

    def get_selected_microphone_name(self):
        idx = self.get_selected_microphone_index()
        selected_item = _get_audio_device_entry(idx, refresh=False) if idx is not None else None
        if selected_item and int(selected_item.get("max_input_channels", 0) or 0) > 0:
            return _expand_audio_device_name(selected_item.get("name"), "input")
        stored = (CONFIG_MGR.get_mic_device_name() or "").strip()
        if stored:
            return _expand_audio_device_name(stored, "input")
        names = self._get_microphone_devices()
        return "Авто" if names else "Не найден"

    def get_selected_output_name(self):
        selected_idx = self.get_selected_output_device_index(use_default=True)
        selected_item = _get_audio_device_entry(selected_idx, refresh=False)
        if selected_item and int(selected_item.get("max_output_channels", 0) or 0) > 0:
            return _expand_audio_device_name(selected_item.get("name"), "output")
        stored = (CONFIG_MGR.get_output_device_name() or "").strip()
        if stored:
            return _expand_audio_device_name(stored, "output")
        return "Не найден"

    # ====================== ИСПРАВЛЕНИЕ ОБРЕЗКИ МИКРОФОНА ======================
    def _shorten_device_name(self, name: str, max_len: int = 120) -> str:
        if not name or len(name) <= max_len:
            return name or "Не найден"
        return name[:max_len - 3] + "..."

    def refresh_mic_status_label(self, extra: str = ""):
        if not hasattr(self, "mic_status_var"):
            return
        name = self.get_selected_microphone_name()
        name_short = self._shorten_device_name(name, max_len=140)
        base = f"🎤 Микрофон: {name_short}"
        if CONFIG_MGR.get_mic_device_index() is None:
            base = f"{base} (авто)"
        if extra:
            base = f"{base} • {extra}"
        try:
            if self.mic_status_var.get() != base:
                self.mic_status_var.set(base)
            self._full_mic_status_name = name
            self.refresh_adaptation_status_label()
            if not getattr(self, "_mic_status_tooltip_bound", False):
                self.mic_status_label.bind(
                    "<Enter>",
                    lambda _e: self._show_tooltip_for_widget(
                        self.mic_status_label,
                        getattr(self, "_full_mic_status_name", self.get_selected_microphone_name()),
                    ),
                )
                self.mic_status_label.bind("<Leave>", lambda _e: self._hide_tooltip())
                self._mic_status_tooltip_bound = True
        except Exception:
            pass

    def refresh_output_status_label(self):
        if not hasattr(self, "output_status_var"):
            return
        name = self.get_selected_output_name()
        name_short = self._shorten_device_name(name, max_len=140)
        try:
            msg = f"🎧 Вывод: {name_short}"
            if CONFIG_MGR.get_output_device_index() is None and not str(CONFIG_MGR.get_output_device_name() or "").strip():
                msg = f"{msg} (по умолчанию)"
            if self.output_status_var.get() != msg:
                self.output_status_var.set(msg)
            self._full_output_status_name = name
            self.refresh_adaptation_status_label()
            if not getattr(self, "_output_status_tooltip_bound", False):
                self.output_status_label.bind(
                    "<Enter>",
                    lambda _e: self._show_tooltip_for_widget(
                        self.output_status_label,
                        getattr(self, "_full_output_status_name", self.get_selected_output_name()),
                    ),
                )
                self.output_status_label.bind("<Leave>", lambda _e: self._hide_tooltip())
                self._output_status_tooltip_bound = True
        except Exception:
            pass

    def refresh_tts_status_label(self):
        if not hasattr(self, "tts_status_var"):
            return
        provider = str(CONFIG_MGR.get_tts_provider() or "pyttsx3").strip().lower()
        names = {
            "pyttsx3": "Системный голос Windows",
            "edge-tts": "Microsoft Edge (онлайн)",
            "elevenlabs": "ElevenLabs (онлайн)",
        }
        mode = names.get(provider, provider or "pyttsx3")
        if self._tts_forced_offline:
            mode = "Системный голос Windows (авто)"
        self.tts_status_var.set(f"🔊 Голос: {mode}")
        self.refresh_adaptation_status_label()

    def _adaptation_status_text(self) -> str:
        tags = device_adaptation_tags(
            self.get_selected_microphone_name(),
            passive_mode=bool(CONFIG_MGR.get_active_listening_enabled()),
            proxy_detected=bool(self.proxy_detected),
            safe_mode=bool(self.safe_mode),
            wake_word_boost=bool(CONFIG_MGR.get_wake_word_boost_enabled()),
        )
        return f"🛠 Адаптация: {' · '.join(tags)}"

    def refresh_adaptation_status_label(self):
        if not hasattr(self, "adaptation_status_var"):
            return
        text = self._adaptation_status_text()
        self.adaptation_status_var.set(text)
        self._adaptation_tooltip_text = text.replace("🛠 ", "")

    def _apply_tts_auto_network_mode(self, online: bool):
        provider = str(CONFIG_MGR.get_tts_provider() or "pyttsx3").strip().lower()
        if not online and provider in {"edge-tts", "elevenlabs"}:
            self._tts_provider_before_offline = provider
            self._tts_forced_offline = True
            CONFIG_MGR.set_tts_provider("pyttsx3")
            self.refresh_tts_status_label()
            self.add_msg("🔈 Интернет пропал. Голос автоматически переключен в оффлайн режим (pyttsx3).", "bot")
            self.set_status_temp("Голос: оффлайн режим", "warn")
            return

        if online and self._tts_forced_offline:
            restore_to = self._tts_provider_before_offline if self._tts_provider_before_offline in {"edge-tts", "elevenlabs"} else "edge-tts"
            CONFIG_MGR.set_tts_provider(restore_to)
            self._tts_forced_offline = False
            self._tts_provider_before_offline = ""
            self.refresh_tts_status_label()
            self.add_msg("🔈 Интернет восстановлен. Онлайн-голос снова активен.", "bot")
            self.set_status_temp("Голос: онлайн режим", "ok")

    def _show_tooltip_for_widget(self, widget, text):
        try:
            self._hide_tooltip()
            tip = str(text or "").strip()
            if not tip:
                return
            self._tooltip = None
            self.set_status_temp(tip[:220], "busy", duration_ms=2600)
        except Exception:
            pass

    def _hide_tooltip(self):
        if hasattr(self, "_tooltip"):
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    def test_microphone_device(self, callback=None):
        def worker():
            idx = self.get_selected_microphone_index()
            name = self.get_selected_microphone_name()
            try:
                self.root.after(0, lambda: self.set_status(f"Проверяю микрофон: {name}", "busy"))
                mic = sr.Microphone(device_index=idx) if idx is not None else sr.Microphone()
                with mic as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
                    self.root.after(0, lambda: self.set_status("Скажите что-нибудь в микрофон...", "busy"))
                    audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=3)

                raw = audio.get_raw_data() if audio else b""
                rms = audio_rms_int16(raw)
                if raw and len(raw) > 1200 and rms > 0:
                    msg = f"Микрофон работает: {name}"
                    self.root.after(0, lambda: self.set_status(msg, "ok"))
                    self.root.after(0, lambda: self.refresh_mic_status_label("работает"))
                    if callback:
                        self.root.after(0, lambda: callback(True, msg))
                else:
                    msg = f"Микрофон доступен, но сигнал не получен: {name}"
                    self.root.after(0, lambda: self.set_status(msg, "warn"))
                    self.root.after(0, lambda: self.refresh_mic_status_label("сигнал слабый"))
                    if callback:
                        self.root.after(0, lambda: callback(False, msg))
            except sr.WaitTimeoutError:
                msg = f"Микрофон открыт, но голос не обнаружен: {name}"
                self.root.after(0, lambda: self.set_status(msg, "warn"))
                self.root.after(0, lambda: self.refresh_mic_status_label("нет голоса"))
                if callback:
                    self.root.after(0, lambda: callback(False, msg))
            except Exception as e:
                msg = f"Микрофон не отвечает: {short_exc(e)}"
                self.root.after(0, lambda: self.set_status(msg, "error"))
                self.root.after(0, lambda: self.refresh_mic_status_label("не найден"))
                if callback:
                    self.root.after(0, lambda: callback(False, msg))
        threading.Thread(target=worker, daemon=True, name="MicTestThread").start()

    def _voice_names(self):
        names = []
        try:
            if self.voices:
                for i, v in enumerate(self.voices):
                    n = getattr(v, "name", f"Voice {i}")
                    names.append(f"{i}: {n}")
        except Exception as e:
            logger.warning(f"Voice list error: {e}")
        return names

    def _selected_voice_label(self):
        names = self._voice_names()
        idx = CONFIG_MGR.get_voice_index()
        if names and 0 <= idx < len(names):
            return names[idx]
        return names[0] if names else ""



    def hide_to_tray(self):
        try:
            geom = self._normal_geometry if self.is_full else self.root.geometry()
            if geom and parse_geometry(geom):
                CONFIG_MGR.set_window_geometry(geom)
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _quit_app_main(self):
        if self._is_quitting:
            return
        self._is_quitting = True
        try:
            self.shutdown()
        except Exception:
            pass
        sys.exit(0)

    def _stop_tts_engine_quick(self, timeout: float = 0.45):
        engine = getattr(self, "tts_engine", None)
        if engine is None:
            return
        finished = threading.Event()

        def _worker():
            try:
                engine.stop()
            except Exception:
                pass
            finally:
                finished.set()

        threading.Thread(target=_worker, daemon=True, name="TTSStopThread").start()
        finished.wait(timeout=max(0.05, float(timeout or 0.45)))

    def quit_app(self, icon=None, item=None):
        if threading.current_thread() is not threading.main_thread():
            self._enqueue_ui_task(self.quit_app, icon, item)
            return
        try:
            self.root.after(0, self._quit_app_main)
        except Exception:
            self._quit_app_main()

    def _init_tts(self):
        self.tts_provider = CONFIG_MGR.get_tts_provider()
        self.tts_engine = None
        self.voices = []
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty("rate", CONFIG_MGR.get_voice_rate())
            self.tts_engine.setProperty("volume", CONFIG_MGR.get_voice_volume())
            self.voices = self.tts_engine.getProperty("voices") or []
            idx = CONFIG_MGR.get_voice_index()
            if self.voices and 0 <= idx < len(self.voices):
                self.tts_engine.setProperty("voice", self.voices[idx].id)
        except Exception as e:
            logger.error(f"TTS init error: {e}")
            self.tts_engine = None
            self.voices = []

    def _tts_provider_available(self, provider: str) -> bool:
        provider = str(provider or "pyttsx3").strip().lower()
        if provider == "pyttsx3":
            return True
        if provider == "edge-tts":
            return edge_tts is not None and (sd is not None or pygame is not None or AudioSegment is not None or shutil.which("ffplay"))
        if provider == "elevenlabs":
            return ElevenLabs is not None and (sd is not None or pygame is not None or AudioSegment is not None or shutil.which("ffplay"))
        return False

    def _tts_provider_ready_details(self, provider: str) -> Tuple[bool, str]:
        provider = str(provider or "pyttsx3").strip().lower()
        if provider == "pyttsx3":
            return True, ""
        if provider == "edge-tts":
            if edge_tts is None:
                return False, "модуль edge_tts не установлен"
            if sd is None and pygame is None and AudioSegment is None and not shutil.which("ffplay"):
                return False, "нет backend-а воспроизведения (sounddevice/pygame/ffplay/pydub)"
            return True, ""
        if provider == "elevenlabs":
            if ElevenLabs is None:
                return False, "модуль elevenlabs не установлен"
            if not CONFIG_MGR.get_elevenlabs_api_key() and not os.getenv("ELEVENLABS_API_KEY"):
                return False, "не задан API-ключ ElevenLabs"
            if not CONFIG_MGR.get_elevenlabs_voice_id():
                return False, "не задан ID голоса ElevenLabs"
            if sd is None and pygame is None and AudioSegment is None and not shutil.which("ffplay"):
                return False, "нет backend-а воспроизведения (sounddevice/pygame/ffplay/pydub)"
            return True, ""
        return False, "неизвестный источник TTS"

    def _auto_fallback_tts_provider_if_needed(self, provider: str) -> str:
        provider = str(provider or "pyttsx3").strip().lower()
        if provider == "pyttsx3":
            return provider
        ready, reason = self._tts_provider_ready_details(provider)
        if ready:
            return provider

        # Провайдер недоступен в текущей сборке/окружении: мягко переключаемся на оффлайн.
        CONFIG_MGR.set_tts_provider("pyttsx3")
        if provider not in self._tts_unavailable_notified:
            self._tts_unavailable_notified.add(provider)
            try:
                self.root.after(0, self.refresh_tts_status_label)
                self.root.after(0, lambda: self.set_status_temp("Голос: авто-переход в оффлайн (pyttsx3)", "warn"))
                self.root.after(
                    0,
                    lambda p=provider: self.add_msg(
                        f"🔈 Источник голоса {p} недоступен ({reason or 'не настроен'}). Автоматически включён оффлайн-голос pyttsx3.",
                        "bot",
                    ),
                )
            except Exception:
                pass
        return "pyttsx3"

    def _is_transient_network_error(self, exc: Exception) -> bool:
        txt = normalize_text(short_exc(exc))
        markers = (
            "timed out",
            "timeout",
            "connection failed",
            "connection reset",
            "forcibly closed",
            "winerror 10054",
            "handshake operation timed out",
            "temporary failure",
            "network is unreachable",
            "name or service not known",
            "max retries exceeded",
            "read timed out",
            "ssl",
        )
        return any(marker in txt for marker in markers)

    def _is_tts_temp_error(self, exc: Exception) -> bool:
        txt = normalize_text(short_exc(exc))
        markers = (
            "winerror 32",
            "used by another process",
            "не может получить доступ к файлу",
            "temporary failure",
            "connection reset",
            "timed out",
            "timeout",
        )
        return any(marker in txt for marker in markers)

    def _log_listen_transient_issue(self, exc: Exception):
        now = time.monotonic()
        key = normalize_text(short_exc(exc))
        if key == self._last_listen_transient_key and (now - self._last_listen_transient_log_ts) < 25.0:
            return
        self._last_listen_transient_key = key
        self._last_listen_transient_log_ts = now
        if any(marker in key for marker in ("timed out", "timeout", "recognition connection failed", "connection failed")):
            logger.debug(f"Listen transient issue: {exc}")
            return
        logger.warning(f"Unexpected listen transient error: {exc}")

    def _ensure_pygame_audio(self) -> bool:
        if pygame is None:
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self._pygame_audio_ready = True
            return True
        except Exception as e:
            logger.warning(f"pygame mixer init failed: {e}")
            self._pygame_audio_ready = False
            return False

    def _explicit_output_routing_requested(self) -> bool:
        return CONFIG_MGR.get_output_device_index() is not None or bool(str(CONFIG_MGR.get_output_device_name() or "").strip())

    def _prefer_direct_pyttsx3_playback(self) -> bool:
        if sd is None or not self._explicit_output_routing_requested():
            return True
        try:
            selected_index = self.get_selected_output_device_index(use_default=False)
        except Exception:
            selected_index = None
        if selected_index is None:
            return True
        try:
            default_index, _ = pick_output_device()
        except Exception:
            default_index = None
        return default_index is not None and int(selected_index) == int(default_index)

    def _prefer_fast_local_tts_for_text(self, text: str) -> bool:
        cleaned = normalize_text(str(text or ""))
        if not cleaned:
            return True
        if len(cleaned) <= 72:
            return True
        short_ack_markers = (
            "готово",
            "выполнено",
            "открыл",
            "открываю",
            "закрыл",
            "закрываю",
            "включил",
            "выключил",
            "переключил",
            "сохранил",
            "проверка завершена",
        )
        return any(marker in cleaned for marker in short_ack_markers)

    def _stop_active_audio_stream_locked(self):
        stream = getattr(self, "_active_audio_stream", None)
        if stream is None:
            return
        try:
            stream.abort()
        except Exception:
            try:
                stream.stop()
            except Exception:
                pass
        try:
            stream.close()
        except Exception:
            pass
        self._active_audio_stream = None

    def _preferred_output_samplerate(self, device_index: Optional[int]) -> Optional[int]:
        item = _get_audio_device_entry(device_index, refresh=False)
        if item is None:
            return None
        try:
            rate = int(float(item.get("default_samplerate", 0) or 0))
        except Exception:
            return None
        return rate if rate > 0 else None

    def _preferred_output_channels(self, device_index: Optional[int]) -> Optional[int]:
        item = _get_audio_device_entry(device_index, refresh=False)
        if item is None:
            return None
        try:
            channels = int(item.get("max_output_channels", 0) or 0)
        except Exception:
            return None
        return channels if channels > 0 else None

    def _play_raw_chunks_with_sounddevice(
        self,
        samplerate: int,
        channels: int,
        sample_width: int,
        chunk_iter,
        device_index: Optional[int] = None,
    ):
        if sd is None:
            raise RuntimeError("sounddevice is unavailable")
        dtype_map = {1: "uint8", 2: "int16", 4: "int32"}
        width = int(sample_width or 0)
        if width not in dtype_map:
            raise RuntimeError(f"Unsupported audio sample width: {width}")
        kwargs = {
            "samplerate": max(8000, int(samplerate or 22050)),
            "channels": max(1, int(channels or 1)),
            "dtype": dtype_map[width],
            "blocksize": 2048,
        }
        if device_index is not None:
            kwargs["device"] = int(device_index)
        stream = sd.RawOutputStream(**kwargs)
        with self.speaking_lock:
            self._stop_active_audio_stream_locked()
            self._active_audio_stream = stream
        try:
            stream.start()
            for chunk in chunk_iter:
                if self._tts_stop_event.is_set():
                    raise InterruptedError("TTS playback interrupted")
                if chunk:
                    stream.write(chunk)
        finally:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
            with self.speaking_lock:
                if self._active_audio_stream is stream:
                    self._active_audio_stream = None

    def _play_wav_file_with_sounddevice(self, path: str, device_index: Optional[int] = None):
        block_frames = 2048
        with wave.open(path, "rb") as wav_file:
            sample_width = int(wav_file.getsampwidth() or 0)
            channels = int(wav_file.getnchannels() or 1)
            samplerate = int(wav_file.getframerate() or 22050)

            def _chunk_iter():
                while True:
                    data = wav_file.readframes(block_frames)
                    if not data:
                        break
                    yield data

            self._play_raw_chunks_with_sounddevice(
                samplerate=samplerate,
                channels=channels,
                sample_width=sample_width,
                chunk_iter=_chunk_iter(),
                device_index=device_index,
            )

    def _play_audio_segment_with_sounddevice(self, audio, device_index: Optional[int] = None):
        if AudioSegment is None:
            raise RuntimeError("pydub is not available")
        if audio is None:
            raise RuntimeError("Audio segment is empty")
        preferred_rate = self._preferred_output_samplerate(device_index)
        if preferred_rate and int(audio.frame_rate or 0) != preferred_rate:
            audio = audio.set_frame_rate(preferred_rate)
        preferred_channels = self._preferred_output_channels(device_index)
        if preferred_channels and int(audio.channels or 1) > preferred_channels:
            audio = audio.set_channels(max(1, preferred_channels))
        if int(audio.sample_width or 0) not in {1, 2, 4}:
            audio = audio.set_sample_width(2)
        if int(audio.channels or 0) <= 0:
            audio = audio.set_channels(1)
        frame_width = max(1, int(audio.channels or 1) * int(audio.sample_width or 2))
        raw = bytes(audio.raw_data or b"")
        block_bytes = 2048 * frame_width

        def _chunk_iter():
            for offset in range(0, len(raw), block_bytes):
                yield raw[offset:offset + block_bytes]

        self._play_raw_chunks_with_sounddevice(
            samplerate=int(audio.frame_rate or 22050),
            channels=int(audio.channels or 1),
            sample_width=int(audio.sample_width or 2),
            chunk_iter=_chunk_iter(),
            device_index=device_index,
        )

    def _play_audio_file_with_sounddevice(self, path: str, device_index: Optional[int] = None):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav":
            return self._play_wav_file_with_sounddevice(path, device_index=device_index)
        if AudioSegment is None:
            raise RuntimeError("pydub is required for non-WAV sounddevice playback")
        if not _compressed_audio_decoder_available():
            raise RuntimeError("compressed audio decoding backend is unavailable")
        with suppress_pydub_ffmpeg_warnings():
            audio = AudioSegment.from_file(path)
        return self._play_audio_segment_with_sounddevice(audio, device_index=device_index)

    def _play_audio_file(self, path: str):
        path = str(path or "").strip()
        if not path or not os.path.exists(path):
            raise FileNotFoundError(path)
        if self._tts_stop_event.is_set():
            raise InterruptedError("TTS playback interrupted")
        selected_output_index = self.get_selected_output_device_index(use_default=False)
        if sd is not None:
            try:
                self._play_audio_file_with_sounddevice(path, device_index=selected_output_index)
                return
            except InterruptedError:
                raise
            except Exception as e:
                err = normalize_text(short_exc(e))
                if any(marker in err for marker in ("compressed audio decoding backend is unavailable", "pydub is required", "pydub is not available", "ffprobe", "ffmpeg", "winerror 2")):
                    logger.debug(f"sounddevice playback skipped, using legacy backends: {e}")
                else:
                    logger.warning(f"sounddevice playback failed, trying legacy backends: {e}")
        ext = os.path.splitext(path)[1].lower()
        ffplay = shutil.which("ffplay")
        if sys.platform == "win32" and ext == ".wav":
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
                return
            except Exception as e:
                logger.warning(f"winsound playback failed, trying ffplay: {e}")
        if self._ensure_pygame_audio():
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.02)
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
                return
            except Exception as e:
                logger.warning(f"pygame playback failed, trying ffplay: {e}")
        if ffplay:
            subprocess.run([ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", path], check=False)
            return
        raise RuntimeError("No available audio playback backend for generated TTS.")

    def _convert_to_wav(self, source_path: str, wav_path: str):
        if AudioSegment is None:
            raise RuntimeError("pydub is not available")
        if not _compressed_audio_decoder_available():
            raise RuntimeError("compressed audio decoding backend is unavailable")
        last_error = None
        for _ in range(6):
            try:
                with suppress_pydub_ffmpeg_warnings():
                    audio = AudioSegment.from_file(source_path)
                audio.export(wav_path, format="wav")
                return
            except Exception as e:
                last_error = e
                msg = str(e).lower()
                is_lock = getattr(e, "winerror", None) == 32 or "used by another process" in msg or "не может получить доступ к файлу" in msg
                if is_lock:
                    time.sleep(0.15)
                    continue
                break
        if last_error:
            raise last_error

    def _safe_remove_tree(self, path: str):
        target = str(path or "").strip()
        if not target:
            return
        for _ in range(6):
            try:
                shutil.rmtree(target)
                return
            except FileNotFoundError:
                return
            except PermissionError:
                time.sleep(0.12)
            except Exception:
                break
        try:
            shutil.rmtree(target, ignore_errors=True)
        except Exception:
            pass

    async def _edge_tts_generate(self, text: str, out_path: str):
        voice = CONFIG_MGR.get_edge_tts_voice()
        rate = CONFIG_MGR.get_voice_rate()
        volume = CONFIG_MGR.get_voice_volume()
        rate_pct = int(((max(150, min(350, rate)) - 240) / 240.0) * 100)
        volume_pct = int(max(-90, min(0, (volume - 1.0) * 100)))
        rate_str = f"{rate_pct:+d}%" if rate_pct != 0 else "+1%"
        volume_str = f"{volume_pct:+d}%"
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate_str,
            volume=volume_str,
        )
        await communicate.save(out_path)

    def _elevenlabs_client(self):
        api_key = CONFIG_MGR.get_elevenlabs_api_key() or os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key or ElevenLabs is None:
            self._elevenlabs_client_cached = None
            self._elevenlabs_client_key = ""
            return None
        if self._elevenlabs_client_cached is not None and self._elevenlabs_client_key == api_key:
            return self._elevenlabs_client_cached
        try:
            self._elevenlabs_client_cached = ElevenLabs(api_key=api_key)
            self._elevenlabs_client_key = api_key
            return self._elevenlabs_client_cached
        except Exception as e:
            logger.error(f"ElevenLabs client init error: {e}")
            self._elevenlabs_client_cached = None
            self._elevenlabs_client_key = ""
            return None

    def _speak_with_pyttsx3(self, text: str):
        if self.tts_engine is None:
            self._init_tts()
        if not self.tts_engine:
            raise RuntimeError("pyttsx3 is unavailable")
        if self._prefer_direct_pyttsx3_playback():
            if self._tts_stop_event.is_set():
                return
            try:
                self.tts_engine.stop()
            except Exception:
                pass
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
            return
        import tempfile
        td = tempfile.mkdtemp(prefix="jarvis_tts_")
        try:
            wav_path = os.path.join(td, "tts.wav")
            self.tts_engine.stop()
            self.tts_engine.save_to_file(text, wav_path)
            self.tts_engine.runAndWait()
            for _ in range(20):
                if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                    break
                if self._tts_stop_event.is_set():
                    return
                time.sleep(0.05)
            if not os.path.exists(wav_path) or os.path.getsize(wav_path) <= 0:
                raise RuntimeError("pyttsx3 save_to_file produced empty audio")
            self._play_audio_file(wav_path)
        finally:
            self._safe_remove_tree(td)

    def _speak_with_edge_tts(self, text: str):
        import tempfile
        td = tempfile.mkdtemp(prefix="jarvis_tts_")
        try:
            mp3_path = os.path.join(td, "tts.mp3")
            asyncio.run(self._edge_tts_generate(text, mp3_path))
            last_play_error = None
            for _ in range(3):
                try:
                    self._play_audio_file(mp3_path)
                    last_play_error = None
                    break
                except Exception as e:
                    last_play_error = e
                    err = str(e).lower()
                    if "winerror 32" in err or "не может получить доступ к файлу" in err or "used by another process" in err:
                        time.sleep(0.08)
                        continue
                    break
            if last_play_error is not None:
                wav_path = os.path.join(td, "tts.wav")
                self._convert_to_wav(mp3_path, wav_path)
                self._play_audio_file(wav_path)
        finally:
            self._safe_remove_tree(td)

    def _speak_with_elevenlabs(self, text: str):
        import tempfile
        client = self._elevenlabs_client()
        if client is None:
            raise RuntimeError("ElevenLabs is unavailable")
        voice_id = CONFIG_MGR.get_elevenlabs_voice_id().strip()
        if not voice_id:
            raise RuntimeError("Для ElevenLabs не настроен ID голоса")
        model_id = CONFIG_MGR.get_elevenlabs_model_id().strip() or "eleven_flash_v2_5"
        td = tempfile.mkdtemp(prefix="jarvis_tts_")
        try:
            mp3_path = os.path.join(td, "tts.mp3")
            kwargs = {
                "text": text,
                "voice_id": voice_id,
                "model_id": model_id,
                "output_format": "mp3_22050_32",
            }
            try:
                audio = client.text_to_speech.convert(
                    optimize_streaming_latency=3,
                    **kwargs,
                )
            except TypeError:
                audio = client.text_to_speech.convert(**kwargs)
            except Exception:
                kwargs["output_format"] = "mp3_44100_128"
                try:
                    audio = client.text_to_speech.convert(
                        optimize_streaming_latency=3,
                        **kwargs,
                    )
                except TypeError:
                    audio = client.text_to_speech.convert(**kwargs)
            if hasattr(audio, "read"):
                data = audio.read()
            elif isinstance(audio, (bytes, bytearray)):
                data = bytes(audio)
            else:
                data = bytes(audio)
            with open(mp3_path, "wb") as f:
                f.write(data)
            last_play_error = None
            for _ in range(3):
                try:
                    self._play_audio_file(mp3_path)
                    last_play_error = None
                    break
                except Exception as e:
                    last_play_error = e
                    err = str(e).lower()
                    if "winerror 32" in err or "не может получить доступ к файлу" in err or "used by another process" in err:
                        time.sleep(0.08)
                        continue
                    break
            if last_play_error is not None:
                wav_path = os.path.join(td, "tts.wav")
                self._convert_to_wav(mp3_path, wav_path)
                self._play_audio_file(wav_path)
        except Exception as e:
            logger.warning(f"ElevenLabs TTS failed: {e}, falling back to pyttsx3")
            raise
        finally:
            self._safe_remove_tree(td)

    def _speak_by_provider(self, text: str):
        provider = str(CONFIG_MGR.get_tts_provider() or "pyttsx3").strip().lower()
        provider = self._auto_fallback_tts_provider_if_needed(provider)
        if provider in {"edge-tts", "elevenlabs"} and self._prefer_fast_local_tts_for_text(text):
            return self._speak_with_pyttsx3(text)
        if provider in {"edge-tts", "elevenlabs"} and not self.is_online:
            return self._speak_with_pyttsx3(text)
        if provider == "edge-tts":
            last_error = None
            for _ in range(2):
                try:
                    return self._speak_with_edge_tts(text)
                except Exception as e:
                    last_error = e
                    if self._is_tts_temp_error(e):
                        time.sleep(0.12)
                        continue
                    break
            logger.error(f"Edge-TTS error: {last_error}")
            if last_error and self.is_online and self._is_tts_temp_error(last_error):
                try:
                    self.root.after(0, lambda: self.set_status_temp("Edge-TTS временно недоступен, повторите", "warn"))
                except Exception:
                    pass
                return
        elif provider == "elevenlabs":
            last_error = None
            for _ in range(2):
                try:
                    return self._speak_with_elevenlabs(text)
                except Exception as e:
                    last_error = e
                    if self._is_tts_temp_error(e):
                        time.sleep(0.12)
                        continue
                    break
            logger.error(f"ElevenLabs TTS error: {last_error}")
            if last_error and self.is_online and self._is_tts_temp_error(last_error):
                try:
                    self.root.after(0, lambda: self.set_status_temp("ElevenLabs временно недоступен, повторите", "warn"))
                except Exception:
                    pass
                return
        return self._speak_with_pyttsx3(text)

    def apply_autostart(self):
        if sys.platform != "win32":
            return
        try:
            import winreg
            key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as reg:
                if CONFIG_MGR.get_autostart():
                    exe = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
                    winreg.SetValueEx(reg, app_brand_name(), 0, winreg.REG_SZ, exe)
                else:
                    try:
                        winreg.DeleteValue(reg, app_brand_name())
                    except FileNotFoundError:
                        pass
        except Exception as e:
            logger.error(f"Autostart error: {e}")

    def _schedule_rate_apply(self, rate):
        if self._rate_apply_after is not None:
            try:
                self.root.after_cancel(self._rate_apply_after)
            except Exception:
                pass
        self._rate_apply_after = self.root.after(180, lambda: self.apply_voice_rate(rate))

    def _schedule_volume_apply(self, volume):
        if self._volume_apply_after is not None:
            try:
                self.root.after_cancel(self._volume_apply_after)
            except Exception:
                pass
        self._volume_apply_after = self.root.after(180, lambda: self.apply_voice_volume(volume))

    def apply_voice_rate(self, rate):
        try:
            rate = max(150, min(350, int(rate)))
        except Exception:
            rate = CONFIG_MGR.get_voice_rate()
        CONFIG_MGR.set_voice_rate(rate)
        if self.tts_engine:
            try:
                self.tts_engine.setProperty("rate", rate)
            except Exception as e:
                logger.error(f"Apply voice rate error: {e}")

    def apply_voice_volume(self, volume):
        try:
            volume = max(0.2, min(1.0, float(volume)))
        except Exception:
            volume = CONFIG_MGR.get_voice_volume()
        CONFIG_MGR.set_voice_volume(volume)
        if self.tts_engine:
            try:
                self.tts_engine.setProperty("volume", volume)
            except Exception as e:
                logger.error(f"Apply voice volume error: {e}")

    def _matches_ctrl_shortcut(self, event, key: str) -> bool:
        wanted = str(key or "").strip().lower()
        if not wanted:
            return False
        keysym = str(getattr(event, "keysym", "") or "").strip().lower()
        char = str(getattr(event, "char", "") or "").strip().lower()
        try:
            keycode = int(getattr(event, "keycode", -1))
        except Exception:
            keycode = -1
        aliases = {
            "a": {"a", "ф", "cyrillic_ef"},
            "c": {"c", "с", "cyrillic_es"},
            "v": {"v", "м", "cyrillic_em"},
            "x": {"x", "ч", "cyrillic_che"},
        }
        keycodes = {"a": 65, "c": 67, "v": 86, "x": 88}
        return keycode == keycodes.get(wanted, -999) or keysym in aliases.get(wanted, set()) or char in aliases.get(wanted, set())

    def _handle_layout_aware_global_shortcuts(self, event):
        if self._matches_ctrl_shortcut(event, "v"):
            return self._paste_to_focused_widget(event)
        return None

    def _handle_layout_aware_entry_shortcuts(self, entry, event):
        if self._matches_ctrl_shortcut(event, "v"):
            if not self._insert_clipboard_into_widget(entry):
                try:
                    entry.event_generate("<<Paste>>")
                except Exception:
                    pass
            return "break"
        if self._matches_ctrl_shortcut(event, "c"):
            try:
                entry.event_generate("<<Copy>>")
            except Exception:
                pass
            return "break"
        if self._matches_ctrl_shortcut(event, "x"):
            try:
                entry.event_generate("<<Cut>>")
            except Exception:
                pass
            return "break"
        if self._matches_ctrl_shortcut(event, "a"):
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
        return None


    def load_assets(self):
        user_avatar_custom = str(CONFIG_MGR.get_user_avatar_path() or "").strip()
        user_avatar_path = user_avatar_custom if (user_avatar_custom and os.path.exists(user_avatar_custom)) else "assets/user_avatar.png"
        paths = {
            "noob2": ("assets/noob2.png", "NOOB"),
            "noob": ("assets/noob.png", "❄️"),
            "noob_settings": ("assets/noob2.png", "NOOB"),
            "noob_sidebar": ("assets/noob.png", "❄️"),
            "ai": ("assets/ai_avatar.png", "🤖"),
            "user": (user_avatar_path, "👤"),
            "mic": ("assets/mic_icon.png", "🎤"),
            "send": ("assets/send_icon.png", "➤"),
            "settings": ("assets/settings.png", "⚙"),
        }
        for key, (filename, fallback_text) in paths.items():
            p = filename if os.path.isabs(filename) else resource_path(filename)
            if os.path.exists(p):
                try:
                    img = Image.open(p).convert("RGBA")
                    if key in ["ai","user"]:
                        img = img.resize((40,40), Image.LANCZOS)
                        mask = Image.new("L", (40,40), 0)
                        ImageDraw.Draw(mask).ellipse((0,0,40,40), fill=255)
                        img.putalpha(mask)
                    elif key in {"noob", "noob2"}:
                        img = img.resize((180,180), Image.LANCZOS)
                    elif key == "noob_settings":
                        img = img.resize((92,92), Image.LANCZOS)
                    elif key == "noob_sidebar":
                        img = img.resize((92,92), Image.LANCZOS)
                    elif key in ["mic","send"]:
                        img = img.resize((32,32), Image.LANCZOS)
                    elif key == "settings":
                        img = img.resize((18,18), Image.LANCZOS)
                    self.assets[key] = ImageTk.PhotoImage(img, master=self.root)
                except Exception as e:
                    logger.error(f"Asset load error {key}: {e}")
                    self.assets[key] = fallback_text
            else:
                self.assets[key] = fallback_text

    def setup_ui(self):
        self.ui_rewrite = None
        self._setup_ui_v2()
        return
        self._configure_ttk_styles()
        self._install_global_clipboard_shortcuts()

        self.bg_canvas = tk.Canvas(self.root, bg=Theme.BG, highlightthickness=0)
        self.bg_canvas.pack(fill="both", expand=True)

        self.main_container = tk.Frame(self.bg_canvas, bg=Theme.BG_LIGHT, bd=1, highlightbackground=Theme.BORDER, highlightthickness=1)
        self.cont_win = self.bg_canvas.create_window(self.root.winfo_width()//2, self.root.winfo_height()//2,
                                                    window=self.main_container, width=620, height=824)

        self.top_bar = tk.Frame(
            self.main_container,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        self.top_bar.pack(side="top", fill="x", padx=10, pady=(10, 8))
        self.top_left = tk.Frame(self.top_bar, bg=Theme.CARD_BG)
        self.top_left.pack(side="left", fill="x", expand=True)
        self.brand_row = tk.Frame(self.top_left, bg=Theme.CARD_BG)
        self.brand_row.pack(fill="x")
        self.title_label = tk.Label(
            self.brand_row,
            text=app_brand_name(),
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=("Segoe UI", 18, "bold"),
        )
        self.title_label.pack(side="left", anchor="w")
        self.version_label = tk.Label(
            self.brand_row,
            text=app_version_badge(),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.version_label.pack(side="left", padx=(10, 0), pady=(2, 0))
        self.subtitle_label = tk.Label(
            self.top_left,
            text=self._header_subtitle_text(),
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9),
        )
        self.subtitle_label.pack(anchor="w", pady=(4, 0))
        self.status_label = tk.Label(
            self.top_left,
            textvariable=self.status_var,
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9, "bold"),
        )
        self.status_label.pack(anchor="w", pady=(6, 0))

        self.status_grid = tk.Frame(self.top_left, bg=Theme.CARD_BG)
        self.status_grid.pack(fill="x", pady=(12, 0))
        self.status_grid.grid_columnconfigure(0, weight=1)
        self.status_grid.grid_columnconfigure(1, weight=1)

        def make_status_chip(row: int, column: int, attr_name: str):
            chip = tk.Frame(
                self.status_grid,
                bg=Theme.BUTTON_BG,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            chip.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 6 if column == 0 else 0), pady=(0, 6))
            setattr(self, attr_name, chip)
            return chip

        self.net_chip = make_status_chip(0, 0, "net_chip")
        self.net_label = tk.Label(
            self.net_chip,
            text="🌐 Онлайн",
            bg=Theme.BUTTON_BG,
            fg=Theme.ONLINE,
            font=("Segoe UI", 9, "bold"),
            justify="left",
            wraplength=220,
        )
        self.net_label.pack(anchor="w")
        bind_dynamic_wrap(self.net_label, self.net_chip, padding=24, minimum=120)

        self.mic_status_var = tk.StringVar(value="🎤 Микрофон: не выбран")
        self.mic_chip = make_status_chip(0, 1, "mic_chip")
        self.mic_status_label = tk.Label(
            self.mic_chip,
            textvariable=self.mic_status_var,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=220,
        )
        self.mic_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.mic_status_label, self.mic_chip, padding=24, minimum=120)

        self.output_status_var = tk.StringVar(value="🎧 Вывод: не выбран")
        self.output_chip = make_status_chip(1, 0, "output_chip")
        self.output_status_label = tk.Label(
            self.output_chip,
            textvariable=self.output_status_var,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=220,
        )
        self.output_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.output_status_label, self.output_chip, padding=24, minimum=120)

        self.tts_status_var = tk.StringVar(value="🔊 Голос: pyttsx3 (оффлайн)")
        self.tts_chip = make_status_chip(1, 1, "tts_chip")
        self.tts_status_label = tk.Label(
            self.tts_chip,
            textvariable=self.tts_status_var,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=220,
        )
        self.tts_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.tts_status_label, self.tts_chip, padding=24, minimum=120)
        self.adaptation_status_var = tk.StringVar(value=self._adaptation_status_text())
        self.adaptation_chip = make_status_chip(2, 0, "adaptation_chip")
        self.adaptation_chip.grid(columnspan=2, padx=0, pady=(0, 0))
        self.adaptation_status_label = tk.Label(
            self.adaptation_chip,
            textvariable=self.adaptation_status_var,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=460,
        )
        self.adaptation_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.adaptation_status_label, self.adaptation_chip, padding=24, minimum=180)
        self.adaptation_status_label.bind(
            "<Enter>",
            lambda _e: self._show_tooltip_for_widget(
                self.adaptation_status_label,
                getattr(self, "_adaptation_tooltip_text", self._adaptation_status_text().replace("🛠 ", "")),
            ),
        )
        self.adaptation_status_label.bind("<Leave>", lambda _e: self._hide_tooltip())

        self.top_right = tk.Frame(self.top_bar, bg=Theme.CARD_BG)
        self.top_right.pack(side="right", anchor="ne", padx=(16, 0))
        self.header_action_buttons = []
        for txt, cmd, width, tip in [
            ("⚙", self.toggle_quick_settings_panel, 3, "Настройки"),
            ("?", self.show_quick_tips, 3, "Подсказки"),
            ("🕘", self.show_history, 3, "История"),
            ("✕", self.clear_chat, 3, "Очистить чат"),
        ]:
            btn = tk.Button(
                self.top_right,
                text=txt,
                command=cmd,
                bg=Theme.BUTTON_BG,
                fg=Theme.FG,
                font=("Segoe UI", 9, "bold"),
                relief="flat",
                width=width,
                padx=4,
                pady=8,
                cursor="hand2",
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
            )
            btn.pack(side="right", padx=(0, 6))
            self._bind_hover_bg(btn, role="button")
            btn.bind("<Enter>", lambda _e, b=btn, t=tip: self._show_tooltip_for_widget(b, t), add="+")
            btn.bind("<Leave>", lambda _e: self._hide_tooltip(), add="+")
            self.header_action_buttons.append(btn)

        self.quick_bar = tk.Frame(
            self.main_container,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.quick_bar.pack(side="top", fill="x", padx=10, pady=(0, 10))
        self.quick_head = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)
        self.quick_head.pack(fill="x", padx=14, pady=(12, 4))
        self.quick_title_label = tk.Label(
            self.quick_head,
            text="Быстрый старт",
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11, "bold"),
        )
        self.quick_title_label.pack(anchor="w")
        self.quick_desc_label = tk.Label(
            self.quick_head,
            text="Частые команды под рукой, чтобы окно не превращалось в свалку действий.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=560,
        )
        self.quick_desc_label.pack(anchor="w", pady=(4, 0))
        bind_dynamic_wrap(self.quick_desc_label, self.quick_bar, padding=32, minimum=220)
        self.quick_inner = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)
        self.quick_inner.pack(fill="x", padx=14, pady=(0, 12))
        self.quick_action_buttons = []
        for lbl, cmd in [("YouTube","открой ютуб"), ("Steam","открой стим"), ("DS","открой дискорд"),
                         ("Ozon","открой озон"), ("WB","открой вб")]:
            b = tk.Label(
                self.quick_inner,
                text=lbl,
                bg=Theme.BUTTON_BG,
                fg=Theme.FG,
                font=("Segoe UI", 9, "bold"),
                padx=14,
                pady=8,
                cursor="hand2",
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
            )
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda e, c=cmd: self.quick_action(c))
            self._bind_hover_bg(b, role="chip")
            self.quick_action_buttons.append(b)

        self.top_divider = tk.Frame(self.main_container, bg=Theme.BG_LIGHT, height=1)
        self.top_divider.pack(fill="x", padx=10, pady=(0, 6))

        self.content_stage = tk.Frame(self.main_container, bg=Theme.BG_LIGHT)
        self.content_stage.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 6))

        self.chat_shell = tk.Frame(
            self.content_stage,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.chat_shell.pack(fill="both", expand=True)
        self.chat_canvas = tk.Canvas(self.chat_shell, bg=Theme.BG_LIGHT, highlightthickness=0)
        self.chat_scroll = ttk.Scrollbar(
            self.chat_shell,
            orient="vertical",
            command=self.chat_canvas.yview,
            style="Jarvis.Vertical.TScrollbar",
        )
        self.chat_scroll.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.chat_canvas.configure(yscrollcommand=self.chat_scroll.set)
        self.chat_canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.chat_frame = tk.Frame(self.chat_canvas, bg=Theme.BG_LIGHT)
        self.chat_window_id = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw", width=570)
        self.chat_frame.bind("<Configure>", lambda _e: self._sync_chat_scroll_region())
        self.chat_canvas.bind("<Configure>", lambda e: self._sync_chat_canvas_width(e.width))
        self._register_scroll_target(self.chat_canvas)

        self.controls_bar = tk.Frame(self.main_container, bg=Theme.BG_LIGHT, height=76)
        self.controls_bar.pack(side="bottom", fill="x", padx=10, pady=10)
        self.controls_bar.pack_propagate(False)
        self.entry_wrap = tk.Frame(
            self.controls_bar,
            bg=Theme.CARD_BG,
            padx=12,
            pady=8,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.entry_wrap.pack(side="left", fill="both", expand=True)
        self.entry = tk.Entry(
            self.entry_wrap,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11),
            bd=0,
            insertbackground=Theme.FG,
            exportselection=0,
            relief="flat",
        )
        self.entry.pack(side="left", fill="both", expand=True, ipady=8)
        self._setup_entry_bindings(self.entry)
        self.entry.bind("<Return>", lambda e: self.send_text())

        self.copy_btn = tk.Label(
            self.entry_wrap,
            text="📋",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11),
            cursor="hand2",
            padx=9,
            pady=6,
        )
        self.copy_btn.pack(side="right", padx=(6, 0))
        self.copy_btn.bind("<Button-1>", lambda e: self.copy_chat())
        self._bind_hover_bg(self.copy_btn, role="input_icon")

        self.paste_btn = tk.Label(
            self.entry_wrap,
            text="📎",
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11),
            cursor="hand2",
            padx=9,
            pady=6,
        )
        self.paste_btn.pack(side="right", padx=(6, 0))
        self.paste_btn.bind("<Button-1>", lambda e: self.paste_text())
        self._bind_hover_bg(self.paste_btn, role="input_icon")

        self.send_btn = tk.Label(
            self.entry_wrap,
            bg=Theme.BUTTON_BG,
            cursor="hand2",
            padx=9,
            pady=6,
        )
        self.send_btn.pack(side="right", padx=(6, 0))
        if "send" in self.assets:
            if isinstance(self.assets["send"], ImageTk.PhotoImage):
                self.send_btn.config(image=self.assets["send"])
            else:
                self.send_btn.config(text=self.assets["send"], fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
        else:
            self.send_btn.config(text="➤", fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
        self.send_btn.bind("<Button-1>", lambda e: self.send_text())
        self._bind_hover_bg(self.send_btn, role="input_icon")

        self.mic_btn = tk.Label(
            self.controls_bar,
            bg=Theme.BUTTON_BG,
            cursor="hand2",
            padx=12,
            pady=10,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.mic_btn.pack(side="right", padx=(8, 0))
        if "mic" in self.assets:
            if isinstance(self.assets["mic"], ImageTk.PhotoImage):
                self.mic_btn.config(image=self.assets["mic"])
            else:
                self.mic_btn.config(text=self.assets["mic"], fg=Theme.MIC_ICON_FG, font=("Segoe UI", 16))
        else:
            self.mic_btn.config(text="🎤", fg=Theme.MIC_ICON_FG, font=("Segoe UI", 16))
        self.mic_btn.bind("<Button-1>", self.mic_click)

        self.root.bind("<F11>", self.toggle_fs)
        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("<FocusIn>", self._schedule_window_activity_sync, add="+")
        self.root.bind("<FocusOut>", self._schedule_window_activity_sync, add="+")
        self.root.bind("<Map>", self._schedule_window_activity_sync, add="+")
        self.root.bind("<Unmap>", self._schedule_window_activity_sync, add="+")

        self.activation_gate = None
        self.root.after(40, self._apply_main_container_bounds)
        self.root.after(90, self._schedule_window_activity_sync)
        if not self._startup_gate_setup:
            if not self.safe_mode:
                self.root.after(620, self.start_bg_anim)
        else:
            self.root.after_idle(lambda: self.run_setup_wizard(True))

    def _show_entry_placeholder(self):
        entry = getattr(self, "entry", None)
        if entry is None:
            return
        try:
            if str(entry.get() or "").strip():
                self._entry_placeholder_active = False
                return
        except Exception:
            return
        self._entry_placeholder_active = True
        self._entry_placeholder_text = "Напишите вопрос, команду или задачу..."
        try:
            entry.delete(0, tk.END)
            entry.insert(0, self._entry_placeholder_text)
            entry.configure(fg=Theme.FG_SECONDARY)
        except Exception:
            pass

    def _clear_entry_placeholder(self):
        if not bool(getattr(self, "_entry_placeholder_active", False)):
            return
        entry = getattr(self, "entry", None)
        if entry is None:
            return
        try:
            if str(entry.get() or "") == str(getattr(self, "_entry_placeholder_text", "")):
                entry.delete(0, tk.END)
            entry.configure(fg=Theme.FG)
        except Exception:
            pass
        self._entry_placeholder_active = False

    def _refresh_chat_empty_state(self):
        ui = getattr(self, "ui_rewrite", None)
        if ui is not None:
            return ui.refresh_chat_empty_state()
        return None

    def _set_workspace_section(self, section: str = "chat"):
        return restored_set_workspace_section(self, section)

    def refresh_workspace_layout_mode(self, *_args):
        return restored_refresh_workspace_layout_mode(self, *_args)

    def _rebuild_workspace_shell_v2(self):
        ui = getattr(self, "ui_rewrite", None)
        if ui is None:
            return None
        try:
            current_section = str(getattr(self, "_workspace_section", "chat") or "chat")
        except Exception:
            current_section = "chat"
        self.setup_ui()
        try:
            self.ui_rewrite.switch_section(current_section)
        except Exception:
            pass
        return None

    def _setup_ui_v2(self):
        self._configure_ttk_styles()
        self._install_global_clipboard_shortcuts()
        self._apply_dpi_scaling()
        metrics = self._workspace_metrics()
        self.ui_rewrite = None

        self.bg_canvas = tk.Frame(self.root, bg=Theme.BG_LIGHT, highlightthickness=0, bd=0)
        self.bg_canvas.pack(fill="both", expand=True)

        self.main_container = tk.Frame(
            self.bg_canvas,
            bg=Theme.BG_LIGHT,
            bd=0,
            highlightthickness=0,
        )
        self.main_container.pack(fill="both", expand=True)
        self.cont_win = None
        self._resize_guard = tk.Frame(self.root, bg=Theme.BG_LIGHT, bd=0, highlightthickness=0)
        self._resize_guard.place_forget()
        self._build_workspace_shell_v2(metrics)

        self.root.bind("<F11>", self.toggle_fs)
        self.root.bind("<Control-k>", self.open_command_palette)
        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("<FocusIn>", self._schedule_window_activity_sync, add="+")
        self.root.bind("<FocusOut>", self._schedule_window_activity_sync, add="+")
        self._needs_visual_prime_after_map = True
        self.root.bind("<Map>", self._schedule_window_activity_sync, add="+")
        self.root.bind("<Unmap>", self._schedule_window_activity_sync, add="+")
        self.root.bind("<Map>", self._handle_window_map, add="+")
        self.root.bind("<Unmap>", self._handle_window_unmap, add="+")

        old_gate = getattr(self, "activation_gate", None)
        if old_gate is not None:
            try:
                old_gate.destroy()
            except Exception:
                pass
        self.activation_gate = None
        self._build_embedded_activation_gate()
        self.root.after(40, self._apply_main_container_bounds)
        self.root.after(60, self.refresh_workspace_layout_mode)
        self.root.after(120, self._prime_after_visual_transition)
        self.root.after(260, self._prime_after_visual_transition)
        self.root.after(90, self._schedule_window_activity_sync)
        if not self._startup_gate_setup:
            if not self.safe_mode:
                self.root.after(620, self.start_bg_anim)
        else:
            self.root.after(180, lambda: self.run_setup_wizard(True))

    def _build_workspace_shell_v2(self, metrics=None):
        return restored_build_workspace_shell_v2(self, metrics)
        metrics = metrics or self._workspace_metrics()

        self.shell = tk.Frame(self.main_container, bg=Theme.BG_LIGHT)
        self.shell.pack(fill="both", expand=True, padx=metrics["shell_pad"], pady=metrics["shell_pad"])
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(
            self.shell,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            width=metrics["sidebar_width"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.sidebar.grid_propagate(False)
        self._build_workspace_sidebar(metrics)

        self.workspace = tk.Frame(self.shell, bg=Theme.BG_LIGHT)
        self.workspace.grid(row=0, column=1, sticky="nsew")

        self.side_panel = tk.Frame(self.shell, bg=Theme.BG_LIGHT, width=metrics["rail_width"])
        self.side_panel.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        self.side_panel.grid_propagate(False)

        self.top_bar = tk.Frame(
            self.workspace,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            padx=metrics["card_pad"],
            pady=metrics["card_pad"],
        )
        self.top_bar.pack(side="top", fill="x")
        self.top_left = tk.Frame(self.top_bar, bg=Theme.CARD_BG)
        self.top_left.pack(side="left", fill="x", expand=True)
        self.brand_row = tk.Frame(self.top_left, bg=Theme.CARD_BG)
        self.brand_row.pack(fill="x")
        self.title_label = tk.Label(
            self.brand_row,
            text=app_brand_name(),
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=metrics["title_font"],
        )
        self.title_label.pack(side="left", anchor="w")
        self.version_label = tk.Label(
            self.brand_row,
            text=app_version_badge(),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.version_label.pack(side="left", padx=(10, 0), pady=(2, 0))
        self.subtitle_label = tk.Label(
            self.top_left,
            text=self._header_subtitle_text(),
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=metrics["body_font"],
            justify="left",
        )
        self.subtitle_label.pack(anchor="w", pady=(6, 0))
        bind_dynamic_wrap(self.subtitle_label, self.top_left, padding=34, minimum=260)
        self.status_label = tk.Label(
            self.top_left,
            textvariable=self.status_var,
            bg=Theme.CARD_BG,
            fg=Theme.STATUS_OK,
            font=("Segoe UI", 9, "bold"),
        )
        self.status_label.pack(anchor="w", pady=(8, 0))

        self.top_right = tk.Frame(self.top_bar, bg=Theme.CARD_BG)
        self.top_right.pack(side="right", anchor="ne", padx=(16, 0))
        self.header_action_buttons = []

        def add_header_button(text, cmd, tip, icon_key=None):
            btn = tk.Button(
                self.top_right,
                text=text,
                command=cmd,
                bg=Theme.BUTTON_BG,
                fg=Theme.FG,
                font=("Segoe UI", 9, "bold"),
                relief="flat",
                padx=10,
                pady=8,
                cursor="hand2",
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
                compound="left",
            )
            if icon_key:
                icon = self.assets.get(icon_key)
                if isinstance(icon, ImageTk.PhotoImage):
                    btn.configure(image=icon, text="", width=34, padx=8)
            btn.pack(side="right", padx=(0, 6))
            self._bind_hover_bg(btn, role="button")
            self._bind_guide_hover(btn, "chat")
            btn.bind("<Enter>", lambda _e, b=btn, t=tip: self._show_tooltip_for_widget(b, t), add="+")
            btn.bind("<Leave>", lambda _e: self._hide_tooltip(), add="+")
            self.header_action_buttons.append(btn)

        add_header_button("?", self.show_quick_tips, "Короткие подсказки")
        add_header_button("Журнал", self.show_history, "История команд")
        add_header_button("", lambda: self.open_full_settings_view("main"), "Настройки", icon_key="settings")

        self.quick_bar = tk.Frame(
            self.workspace,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.quick_bar.pack(side="top", fill="x", pady=(8, 10))
        self.quick_head = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)
        self.quick_head.pack(fill="x", padx=metrics["card_pad"], pady=(metrics["card_pad"], 8))
        self._build_workspace_overview(metrics)
        self.content_stage = tk.Frame(self.workspace, bg=Theme.BG_LIGHT)
        self.content_stage.pack(side="top", fill="both", expand=True)
        self._build_workspace_chat(metrics)
        self._build_workspace_controls(metrics)
        self._build_workspace_rail(metrics)
        self._refresh_chat_empty_state()

    def _rebuild_workspace_shell_v2(self):
        if not hasattr(self, "main_container"):
            return
        metrics = self._workspace_metrics()
        settings_canvas = getattr(self, "_control_center_content_canvas", None)
        settings_open = bool(getattr(self, "_is_full_settings_open", lambda: False)())
        previous_entry = ""
        try:
            if getattr(self, "entry", None) is not None and self.entry.winfo_exists():
                previous_entry = str(self.entry.get() or "")
        except Exception:
            previous_entry = ""
        try:
            if previous_entry == "Например: открой Steam, сделай потише, что ты запомнил обо мне?":
                previous_entry = ""
        except Exception:
            previous_entry = ""
        current_section = str(getattr(self, "_workspace_section", "chat") or "chat")

        old_shell = getattr(self, "shell", None)
        if old_shell is not None:
            try:
                old_shell.destroy()
            except Exception:
                pass
        self._workspace_layout_signature = None
        self._workspace_shell_layout_mode = None
        self._scroll_targets = []
        self._active_scroll_target = None
        self._wheel_delta_accum = {}
        self._mousewheel_bound_hosts = set()

        self._build_workspace_shell_v2(metrics)
        try:
            self._set_workspace_section(current_section)
        except Exception:
            pass
        try:
            self._refresh_chat_theme()
        except Exception:
            pass
        try:
            if previous_entry:
                self.entry.delete(0, tk.END)
                self.entry.insert(0, previous_entry)
                self.entry.configure(fg=Theme.FG)
            else:
                self._show_entry_placeholder()
        except Exception:
            pass
        try:
            self.refresh_workspace_layout_mode()
        except Exception:
            pass
        if settings_open and settings_canvas is not None:
            try:
                if settings_canvas.winfo_exists():
                    self._register_scroll_target(settings_canvas)
                    self._active_scroll_target = settings_canvas
                    self._preferred_scroll_target = settings_canvas
            except Exception:
                pass

    def _build_workspace_sidebar(self, metrics):
        restored_build_workspace_sidebar(self, metrics)
        guide = getattr(self, "guide_panel", None)
        self.chat_noob_button = getattr(guide, "frame", None)
        self.chat_noob_message = getattr(guide, "message_label", None)
        return None
        self.sidebar_action_buttons = []

        # Top branding with more air and rounded corners
        top = tk.Frame(self.sidebar, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1, bd=0)
        top.pack(fill="x", padx=18, pady=(22, 18))
        tk.Label(top, text=app_brand_name(), bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Black", 18)).pack(anchor="w", pady=(0, 2))
        tk.Label(top, text=f"{app_version_badge()} • домашний экран", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 0))

        # Navigation with accent and rounded buttons
        nav = tk.Frame(self.sidebar, bg=Theme.CARD_BG)
        nav.pack(fill="x", padx=10, pady=(8, 18))

        nav_items = [
            ("💬 Новая беседа", "chat", self.clear_chat, False),
            ("🎤 Проверка голоса", "voice", lambda: self.open_full_settings_view("diagnostics"), True),
            ("🎮 Приложения и игры", "chat", lambda: self.open_full_settings_view("apps"), False),
            ("⚙️ Настройки", "chat", lambda: self.open_full_settings_view("main"), False),
            ("🖥️ Система", "release", lambda: self.open_full_settings_view("system"), False),
        ]
        for text, section, command, accent in nav_items:
            btn = tk.Button(
                nav,
                text=text,
                command=lambda s=section, c=command: (self._update_guide_context(s), c()),
                anchor="w",
                bg=Theme.ACCENT if accent else Theme.BUTTON_BG,
                fg=Theme.FG,
                relief="flat",
                padx=18,
                pady=12,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
                cursor="hand2",
                font=("Segoe UI Semibold", 12),
                bd=0,
            )
            btn.pack(fill="x", pady=(0, 12), ipady=2)
            btn.configure(overrelief="ridge")
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=Theme.ACCENT))
            btn.bind("<Leave>", lambda e, b=btn, a=accent: b.configure(bg=Theme.ACCENT if a else Theme.BUTTON_BG))
            self._bind_guide_hover(btn, section)
            self.sidebar_action_buttons.append(btn)

        # Note box with more padding and rounded look
        self.sidebar_note_box, self.sidebar_note_label = create_note_box(
            self.sidebar,
            "По центру — только рабочее пространство. Диагностика, релиз и обслуживание теперь собраны во вкладке «Система».",
            tone="soft",
        )
        self.sidebar_note_box.pack_configure(padx=16, pady=(0, 18))

    def _build_workspace_overview(self, metrics):
        return restored_build_workspace_overview(self, metrics)
        head_row = tk.Frame(self.quick_head, bg=Theme.CARD_BG)
        head_row.pack(fill="x", pady=(0, 6))
        self.quick_title_label = tk.Label(
            head_row,
            text="✨ Добро пожаловать в JARVIS!",
            bg=Theme.CARD_BG,
            fg=Theme.ACCENT,
            font=("Segoe UI Black", 16),
        )
        self.quick_title_label.pack(side="left", padx=(0, 8))
        self.workspace_mode_badge = tk.Label(
            head_row,
            textvariable=self.workspace_mode_var,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
        )
        self.workspace_mode_badge.pack(side="right")
        self.quick_desc_label = tk.Label(
            self.quick_head,
            text="Чат, голос и команды — в центре. Всё служебное и сложное теперь по разделам, чтобы не мешать работе.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 11),
            justify="left",
        )
        self.quick_desc_label.pack(anchor="w", pady=(2, 0))
        bind_dynamic_wrap(self.quick_desc_label, self.quick_head, padding=40, minimum=280)

        self.status_grid = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)
        self.status_grid.pack(fill="x", padx=metrics["card_pad"], pady=(0, 10))
        self.status_grid.grid_columnconfigure(0, weight=1)
        self.status_grid.grid_columnconfigure(1, weight=1)

        def make_status_chip(row: int, column: int, attr_name: str):
            chip = tk.Frame(
                self.status_grid,
                bg=Theme.BUTTON_BG,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            chip.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 6 if column == 0 else 0), pady=(0, 6))
            setattr(self, attr_name, chip)
            return chip

        self.net_chip = make_status_chip(0, 0, "net_chip")
        self.net_label = tk.Label(self.net_chip, text="🌐 Онлайн", bg=Theme.BUTTON_BG, fg=Theme.ONLINE, font=("Segoe UI", 9, "bold"), justify="left")
        self.net_label.pack(anchor="w")
        bind_dynamic_wrap(self.net_label, self.net_chip, padding=24, minimum=120)

        self.mic_status_var = tk.StringVar(value="🎤 Микрофон: не выбран")
        self.mic_chip = make_status_chip(0, 1, "mic_chip")
        self.mic_status_label = tk.Label(self.mic_chip, textvariable=self.mic_status_var, bg=Theme.BUTTON_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        self.mic_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.mic_status_label, self.mic_chip, padding=24, minimum=120)

        self.output_status_var = tk.StringVar(value="🎧 Вывод: не выбран")
        self.output_chip = make_status_chip(1, 0, "output_chip")
        self.output_status_label = tk.Label(self.output_chip, textvariable=self.output_status_var, bg=Theme.BUTTON_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        self.output_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.output_status_label, self.output_chip, padding=24, minimum=120)

        self.tts_status_var = tk.StringVar(value="🔊 Голос: pyttsx3 (оффлайн)")
        self.tts_chip = make_status_chip(1, 1, "tts_chip")
        self.tts_status_label = tk.Label(self.tts_chip, textvariable=self.tts_status_var, bg=Theme.BUTTON_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 8), justify="left")
        self.tts_status_label.pack(anchor="w")
        bind_dynamic_wrap(self.tts_status_label, self.tts_chip, padding=24, minimum=120)

        self.quick_inner = tk.Frame(self.quick_bar, bg=Theme.CARD_BG)
        self.quick_inner.pack(fill="x", padx=metrics["card_pad"], pady=(0, metrics["card_pad"]))
        _, self.quick_action_buttons = create_action_grid(
            self.quick_inner,
            [
                {"text": "Новая беседа", "command": lambda: (self._update_guide_context("chat"), self.clear_chat())},
                {"text": "Проверка голоса", "command": lambda: self.open_full_settings_view("diagnostics"), "bg": Theme.ACCENT},
                {"text": "Приложения и игры", "command": lambda: self.open_full_settings_view("apps")},
                {"text": "Система", "command": lambda: self.open_full_settings_view("system")},
            ],
            columns=2,
            bg=Theme.CARD_BG,
        )
        quick_hover_map = {
            "Новая беседа": "chat",
            "Проверка голоса": "voice",
            "Приложения и игры": "apps",
            "Система": "system",
        }
        for btn in self.quick_action_buttons:
            btn.configure(highlightbackground=Theme.BORDER, highlightthickness=1)
            self._bind_hover_bg(btn, role="button")
            self._bind_guide_hover(btn, quick_hover_map.get(btn.cget("text"), "chat"))
        self.top_divider = tk.Frame(self.workspace, bg=Theme.BORDER, height=1)
        self.top_divider.pack(fill="x", pady=(0, 8))

    def _build_workspace_chat(self, metrics):
        return restored_build_workspace_chat(self, metrics)
        self.chat_shell = tk.Frame(
            self.content_stage,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.chat_shell.pack(fill="both", expand=True)
        self.chat_header = tk.Frame(self.chat_shell, bg=Theme.CARD_BG)
        self.chat_header.pack(fill="x", padx=metrics["card_pad"], pady=(metrics["card_pad"], 0))
        tk.Label(self.chat_header, text="Чат и команды", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 12)).pack(side="left")
        self.chat_hint_label = tk.Label(
            self.chat_header,
            text="Введите команду или нажмите микрофон",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 8, "bold"),
        )
        self.chat_hint_label.pack(side="right")

        self.chat_canvas = tk.Canvas(self.chat_shell, bg=Theme.BG_LIGHT, highlightthickness=0)
        self.chat_scroll = ttk.Scrollbar(self.chat_shell, orient="vertical", command=self.chat_canvas.yview, style="Jarvis.Vertical.TScrollbar")
        self.chat_scroll.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.chat_canvas.configure(yscrollcommand=self.chat_scroll.set)
        self.chat_canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.chat_frame = tk.Frame(self.chat_canvas, bg=Theme.BG_LIGHT)
        self.chat_window_id = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw", width=650)
        self.chat_frame.bind("<Configure>", lambda _e: self._sync_chat_scroll_region())
        self.chat_canvas.bind("<Configure>", lambda e: self._sync_chat_canvas_width(e.width))
        self._register_scroll_target(self.chat_canvas)

    def _build_workspace_controls(self, metrics):
        return restored_build_workspace_controls(self, metrics)
        self.controls_bar = tk.Frame(self.workspace, bg=Theme.BG_LIGHT, height=metrics["entry_height"])
        self.controls_bar.pack(side="bottom", fill="x", pady=(12, 0))
        self.controls_bar.pack_propagate(False)
        self.entry_wrap = tk.Frame(
            self.controls_bar,
            bg=Theme.CARD_BG,
            padx=12,
            pady=8,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self.entry_wrap.pack(side="left", fill="both", expand=True)
        self.entry = tk.Entry(
            self.entry_wrap,
            bg=Theme.INPUT_BG,
            fg=Theme.FG,
            font=metrics["input_font"],
            bd=0,
            insertbackground=Theme.FG,
            exportselection=0,
            relief="flat",
        )
        self.entry.pack(side="left", fill="both", expand=True, ipady=8)
        self._setup_entry_bindings(self.entry)
        self.entry.bind("<Return>", lambda e: self.send_text())

        self.copy_btn = tk.Button(
            self.entry_wrap,
            text="📋",
            command=self.copy_chat,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11),
            cursor="hand2",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activebackground=Theme.ACCENT,
            activeforeground=Theme.FG,
            padx=9,
            pady=6,
        )
        self.copy_btn.pack(side="right", padx=(6, 0))
        self._bind_hover_bg(self.copy_btn, role="input_icon")

        self.paste_btn = tk.Button(
            self.entry_wrap,
            text="📎",
            command=self.paste_text,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            font=("Segoe UI", 11),
            cursor="hand2",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activebackground=Theme.ACCENT,
            activeforeground=Theme.FG,
            padx=9,
            pady=6,
        )
        self.paste_btn.pack(side="right", padx=(6, 0))
        self._bind_hover_bg(self.paste_btn, role="input_icon")

        self.send_btn = tk.Button(
            self.entry_wrap,
            bg=Theme.BUTTON_BG,
            command=self.send_text,
            cursor="hand2",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activebackground=Theme.ACCENT,
            activeforeground=Theme.FG,
            padx=9,
            pady=6,
            compound="center",
        )
        self.send_btn.pack(side="right", padx=(6, 0))
        if "send" in self.assets:
            if isinstance(self.assets["send"], ImageTk.PhotoImage):
                self.send_btn.config(image=self.assets["send"], text="")
            else:
                self.send_btn.config(text=self.assets["send"], fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
        else:
            self.send_btn.config(text="➤", fg=Theme.MIC_ICON_FG, font=("Segoe UI", 11, "bold"))
        self._bind_hover_bg(self.send_btn, role="input_icon")

        self.mic_btn = tk.Button(
            self.controls_bar,
            command=self.mic_click,
            bg=Theme.ACCENT,
            fg=Theme.FG,
            cursor="hand2",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activebackground="#16a34a",
            activeforeground=Theme.FG,
            padx=14,
            pady=10,
            compound="center",
        )
        self.mic_btn.pack(side="right", padx=(8, 0))
        if "mic" in self.assets:
            if isinstance(self.assets["mic"], ImageTk.PhotoImage):
                self.mic_btn.config(image=self.assets["mic"], text="")
            else:
                self.mic_btn.config(text=self.assets["mic"], font=("Segoe UI", 16))
        else:
            self.mic_btn.config(text="🎤", font=("Segoe UI", 16))
        self._bind_hover_bg(self.mic_btn, role="button")

    def _build_workspace_rail(self, metrics):
        return restored_build_workspace_rail(self, metrics)
        self.rail_action_buttons = []
        self.side_status_labels = []

        guide_host = tk.Frame(self.side_panel, bg=Theme.BG_LIGHT)
        guide_host.pack(fill="x")
        noob_asset = self.assets.get("noob2") or self.assets.get("noob")
        noob_image = noob_asset if isinstance(noob_asset, ImageTk.PhotoImage) else None
        self.guide_panel = GuideNoobPanel(guide_host, image=noob_image, title="Навигатор JARVIS")
        self._update_guide_context("chat")

        tools = tk.Frame(self.side_panel, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        tools.pack(fill="x", pady=(12, 0))
        tk.Label(tools, text="Спокойный режим", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=14, pady=(14, 4))
        tk.Label(
            tools,
            text="Домашний экран теперь показывает только основное. Вся служебная глубина переехала во вкладку «Система».",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=metrics["small_font"],
        ).pack(fill="x", padx=14, pady=(0, 10))
        _, buttons = create_action_grid(
            tools,
            [
                {"text": "Система", "command": lambda: self.open_full_settings_view("system"), "bg": Theme.ACCENT},
                {"text": "Проверка готовности", "command": lambda: (self._update_guide_context('readiness'), self.run_readiness_master())},
            ],
            columns=2,
            bg=Theme.CARD_BG,
        )
        for btn in buttons:
            btn.configure(highlightbackground=Theme.BORDER, highlightthickness=1)
            self._bind_hover_bg(btn, role="button")
            self._bind_guide_hover(btn, "system" if btn.cget("text") == "Система" else "readiness")
        self.rail_action_buttons.extend(buttons)

        _, tip_label = create_note_box(
            self.side_panel,
            "Если нужен совсем чистый вид, включите фокус-режим через быстрый поиск. Для релизных задач сразу открывайте вкладку «Система».",
            tone="soft",
        )
        self.side_tip_label = tip_label

    def _refresh_chat_empty_state(self):
        return restored_refresh_chat_empty_state(self)
        if not getattr(self, "chat_frame", None):
            return
        has_history = bool(getattr(self, "chat_history", []))
        placeholder = getattr(self, "_chat_empty_state", None)
        if has_history:
            if placeholder and placeholder.winfo_exists():
                placeholder.destroy()
            self._chat_empty_state = None
            return
        if placeholder and placeholder.winfo_exists():
            return

        empty = tk.Frame(self.chat_frame, bg=Theme.BG_LIGHT, pady=24)
        empty.pack(fill="x", padx=14, pady=(14, 8))
        self._chat_empty_state = empty
        card = tk.Frame(empty, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        card.pack(fill="x")
        tk.Label(card, text="С чего начать", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(16, 6))
        hint = tk.Label(
            card,
            text="Можно написать команду, нажать на микрофон или открыть раздел «Система», если нужен глубокий контроль и диагностика.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 9),
        )
        hint.pack(fill="x", padx=16, pady=(0, 12))
        bind_dynamic_wrap(hint, card, padding=34, minimum=260)
        _, buttons = create_action_grid(
            card,
            [
                {"text": "Проверка голоса", "command": lambda: self.open_full_settings_view("diagnostics"), "bg": Theme.ACCENT},
                {"text": "Настройки", "command": self.open_full_settings_view},
                {"text": "Система", "command": lambda: self.open_full_settings_view("system")},
            ],
            columns=3,
            bg=Theme.CARD_BG,
        )
        for btn in buttons:
            btn.configure(highlightbackground=Theme.BORDER, highlightthickness=1)
            self._bind_hover_bg(btn, role="button")

    def _build_embedded_activation_gate(self):
        self.activation_gate = tk.Frame(
            self.root,
            bg=Theme.BG_LIGHT,
        )
        self.activation_gate.place_forget()
        self.activation_gate.bind("<Configure>", lambda _event: self._schedule_activation_gate_layout_refresh(), add="+")

        shell = tk.Frame(self.activation_gate, bg=Theme.BG_LIGHT)
        self._activation_gate_shell = shell
        shell.pack(fill="both", expand=True, padx=24, pady=24)
        shell.grid_columnconfigure(0, weight=0)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        intro = tk.Frame(
            shell,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
            width=320,
        )
        self._activation_gate_intro = intro
        intro.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        intro.grid_propagate(False)
        tk.Label(
            intro,
            text="JARVIS AI 2.0",
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=("Bahnschrift SemiBold", 22),
        ).pack(anchor="w", padx=22, pady=(24, 6))
        tk.Label(
            intro,
            text=app_version_badge(),
            bg=Theme.ACCENT,
            fg=Theme.FG,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
        ).pack(anchor="w", padx=22)
        intro_note = tk.Label(
            intro,
            text="Сначала активируем доступ, потом сразу попадаем в спокойный рабочий экран с чатом, голосом и понятной навигацией.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="left",
            font=("Segoe UI", 10),
        )
        intro_note.pack(fill="x", padx=22, pady=(16, 18))
        bind_dynamic_wrap(intro_note, intro, padding=44, minimum=220)

        steps_box = tk.Frame(intro, bg=Theme.BUTTON_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        steps_box.pack(fill="x", padx=22, pady=(0, 14))
        for step in (
            "1. Вставьте Groq API-ключ",
            "2. При желании добавьте Telegram",
            "3. Укажите имя и тему",
            "4. Нажмите «Активировать и открыть чат»",
        ):
            tk.Label(
                steps_box,
                text=step,
                bg=Theme.BUTTON_BG,
                fg=Theme.FG if step.startswith("1.") else Theme.FG_SECONDARY,
                justify="left",
                anchor="w",
                font=("Segoe UI", 9, "bold" if step.startswith("1.") else "normal"),
            ).pack(fill="x", padx=14, pady=(10 if step.startswith("1.") else 0, 8))

        noob_card = tk.Frame(intro, bg=Theme.CARD_BG, width=320, height=260)
        noob_card.pack(fill="x", padx=22, pady=(0, 22))
        noob_card.pack_propagate(False)
        self._activation_gate_noob_card = noob_card
        noob_asset = self.assets.get("noob2") or self.assets.get("noob")
        if isinstance(noob_asset, ImageTk.PhotoImage):
            self._activation_gate_noob_image_label = tk.Label(noob_card, image=noob_asset, bg=Theme.CARD_BG)
            self._activation_gate_noob_image_label.image = noob_asset
            self._activation_gate_noob_image_label.pack(anchor="center", pady=(8, 10))
        else:
            self._activation_gate_noob_image_label = None
        tk.Label(
            noob_card,
            text="Нубик рядом",
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="center")
        noob_note = tk.Label(
            noob_card,
            text="Обязателен только API-ключ. Остальное можно дописать позже уже внутри настроек.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            justify="center",
            font=("Segoe UI", 9),
        )
        noob_note.pack(fill="x", pady=(8, 0))
        bind_dynamic_wrap(noob_note, noob_card, padding=26, minimum=180)

        form_card = tk.Frame(
            shell,
            bg=Theme.CARD_BG,
            highlightbackground=Theme.BORDER,
            highlightthickness=1,
        )
        self._activation_gate_form_card = form_card
        form_card.grid(row=0, column=1, sticky="nsew")

        head = tk.Frame(form_card, bg=Theme.CARD_BG)
        head.pack(fill="x", padx=22, pady=(22, 8))
        tk.Label(
            head,
            text=f"Активация {app_brand_name()}",
            bg=Theme.CARD_BG,
            fg=Theme.FG,
            font=("Bahnschrift SemiBold", 24),
        ).pack(anchor="w")
        gate_note = tk.Label(
            head,
            text="Введите ключи и базовые параметры профиля. После активации чат откроется в этом же окне, без лишних всплывающих мастеров.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 10),
            justify="left",
        )
        gate_note.pack(anchor="w", pady=(8, 0))
        bind_dynamic_wrap(gate_note, head, padding=26, minimum=260)

        body = tk.Frame(form_card, bg=Theme.CARD_BG)
        body.pack(fill="both", expand=True, padx=22, pady=(8, 18))

        def gate_entry(label: str, value: str = "", show: str = ""):
            row = tk.Frame(body, bg=Theme.CARD_BG)
            row.pack(fill="x", pady=(0, 10))
            tk.Label(row, text=label, bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI", 10)).pack(anchor="w")
            var = tk.StringVar(value=value or "")
            ent = tk.Entry(
                row,
                textvariable=var,
                bg=Theme.INPUT_BG,
                fg=Theme.FG,
                insertbackground=Theme.FG,
                relief="flat",
                show=show,
            )
            ent.pack(fill="x", ipady=7)
            self._setup_entry_bindings(ent)
            return var, ent

        self._gate_groq_var, self._gate_groq_entry = gate_entry("Groq API-ключ", self.config_mgr.get_api_key(), show="•")
        self._gate_tg_token_var, _ = gate_entry("Токен Telegram-бота (необязательно)", self.config_mgr.get_telegram_token(), show="•")
        self._gate_tg_id_var, _ = gate_entry("ID пользователя Telegram (необязательно)", str(self.config_mgr.get_telegram_user_id() or ""))
        self._gate_user_name_var, _ = gate_entry("Имя пользователя", self.config_mgr.get_user_name())
        self._gate_user_login_var, _ = gate_entry("Логин пользователя", self.config_mgr.get_user_login())

        mode_row = tk.Frame(body, bg=Theme.CARD_BG)
        mode_row.pack(fill="x", pady=(0, 8))
        tk.Label(mode_row, text="Тема интерфейса", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w")
        self._gate_theme_items = [("Тёмная", "dark"), ("Светлая", "light")]
        current_theme = str(self.config_mgr.get_theme_mode() or "dark").strip().lower()
        if current_theme not in {"dark", "light"}:
            current_theme = "dark"
        current_theme_label = next((lbl for lbl, key in self._gate_theme_items if key == current_theme), self._gate_theme_items[0][0])
        self._gate_theme_var = tk.StringVar(value=current_theme_label)
        theme_shell, theme_button = self._create_settings_choice_control(
            mode_row,
            self._gate_theme_var,
            [x[0] for x in self._gate_theme_items],
            font=("Segoe UI", 10),
        )
        theme_shell.pack(fill="x", pady=(3, 0))
        self._gate_theme_box = theme_button

        current_dangerous_modes = normalize_permission_modes(self.config_mgr.get_dangerous_action_modes())
        dangerous_mode_key = "ask"
        dangerous_values = [
            str(current_dangerous_modes.get(category, DEFAULT_PERMISSION_MODES[category]) or "").strip().lower()
            for category in DEFAULT_PERMISSION_MODES
        ]
        if dangerous_values and all(value == "trust" for value in dangerous_values):
            dangerous_mode_key = "trust"
        elif dangerous_values and all(value == "ask_once" for value in dangerous_values):
            dangerous_mode_key = "ask_once"
        self._gate_dangerous_mode_items = [
            ("Всегда спрашивать", "ask"),
            ("Разрешать один раз", "ask_once"),
            ("Всегда выполнять", "trust"),
        ]

        danger_row = tk.Frame(body, bg=Theme.CARD_BG)
        danger_row.pack(fill="x", pady=(8, 0))
        tk.Label(danger_row, text="Опасные действия", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w")
        self._gate_dangerous_mode_var = tk.StringVar(
            value=next((lbl for lbl, key in self._gate_dangerous_mode_items if key == dangerous_mode_key), self._gate_dangerous_mode_items[0][0])
        )
        danger_shell, danger_button = self._create_settings_choice_control(
            danger_row,
            self._gate_dangerous_mode_var,
            [label for label, _key in self._gate_dangerous_mode_items],
            font=("Segoe UI", 10),
        )
        danger_shell.pack(fill="x", pady=(3, 0))
        self._gate_dangerous_mode_box = danger_button

        controls = tk.Frame(body, bg=Theme.CARD_BG)
        self._activation_gate_controls = controls
        controls.pack(fill="x", pady=(10, 0))
        self._activation_gate_submit_btn = tk.Button(
            controls,
            text="Активировать и открыть чат",
            command=self._submit_embedded_activation_gate,
            bg=Theme.ACCENT,
            fg=Theme.FG,
            relief="flat",
            padx=14,
            pady=10,
            cursor="hand2",
            takefocus=True,
        )
        self._activation_gate_submit_btn.pack(side="right")
        self._activation_gate_clear_btn = tk.Button(
            controls,
            text="Очистить поля",
            command=self._reset_embedded_activation_gate,
            bg=Theme.BUTTON_BG,
            fg=Theme.FG,
            relief="flat",
            padx=12,
            pady=10,
        )
        self._activation_gate_clear_btn.pack(side="right", padx=(0, 8))

        footer_note = tk.Label(
            body,
            text="Поддерживаются Ctrl+V, Shift+Insert и вставка мышью. Обязательное поле только одно: Groq API-ключ. Здесь же можно выбрать, как JARVIS должен вести себя с опасными командами.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9),
        )
        footer_note.pack(anchor="w", fill="x", pady=(10, 0))
        bind_dynamic_wrap(footer_note, body, padding=26, minimum=220)
        self._schedule_activation_gate_layout_refresh()

    def _schedule_activation_gate_layout_refresh(self):
        after_id = getattr(self, "_activation_gate_layout_after_id", None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass

        def _refresh():
            self._activation_gate_layout_after_id = None
            self._refresh_activation_gate_layout()

        self._activation_gate_layout_after_id = self.root.after(32, _refresh)

    def _refresh_activation_gate_layout(self):
        gate = getattr(self, "activation_gate", None)
        shell = getattr(self, "_activation_gate_shell", None)
        intro = getattr(self, "_activation_gate_intro", None)
        form_card = getattr(self, "_activation_gate_form_card", None)
        submit_btn = getattr(self, "_activation_gate_submit_btn", None)
        clear_btn = getattr(self, "_activation_gate_clear_btn", None)
        image_label = getattr(self, "_activation_gate_noob_image_label", None)
        if gate is None or shell is None or intro is None or form_card is None:
            return
        try:
            width = max(int(gate.winfo_width() or self.main_container.winfo_width() or 0), 1)
            height = max(int(gate.winfo_height() or self.main_container.winfo_height() or 0), 1)
        except Exception:
            return

        compact = width < 980 or height < 700
        narrow_buttons = width < 760
        image_visible = bool(image_label is not None and (not compact) and width >= 1040 and height >= 760)
        layout_signature = (compact, narrow_buttons, image_visible)
        if layout_signature == getattr(self, "_activation_gate_layout_signature", None):
            return
        self._activation_gate_layout_signature = layout_signature

        try:
            if compact:
                shell.grid_columnconfigure(0, weight=1)
                shell.grid_columnconfigure(1, weight=0)
                shell.grid_rowconfigure(0, weight=0)
                shell.grid_rowconfigure(1, weight=1)
                intro.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 14))
                form_card.grid(row=1, column=0, columnspan=2, sticky="nsew")
                intro.grid_propagate(True)
                intro.configure(width=1)
            else:
                shell.grid_columnconfigure(0, weight=0)
                shell.grid_columnconfigure(1, weight=1)
                shell.grid_rowconfigure(0, weight=1)
                shell.grid_rowconfigure(1, weight=0)
                intro.grid(row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 14), pady=0)
                form_card.grid(row=0, column=1, columnspan=1, sticky="nsew")
                intro.grid_propagate(False)
                intro.configure(width=max(280, min(360, width // 3)))
        except Exception:
            pass

        if image_label is not None:
            try:
                image_packed = bool(str(image_label.winfo_manager() or "").strip())
            except Exception:
                image_visible = False
                image_packed = False
            if image_visible and not image_packed:
                image_label.pack(anchor="center", pady=(4, 8), before=image_label.master.winfo_children()[0] if image_label.master.winfo_children() else None)
            elif not image_visible and image_packed:
                try:
                    image_label.pack_forget()
                except Exception:
                    pass

        if submit_btn is not None and clear_btn is not None:
            try:
                submit_btn.pack_forget()
                clear_btn.pack_forget()
            except Exception:
                pass
            if narrow_buttons:
                clear_btn.pack(fill="x", pady=(0, 8))
                submit_btn.pack(fill="x")
            else:
                submit_btn.pack(side="right")
                clear_btn.pack(side="right", padx=(0, 8))

    def _show_embedded_activation_gate(self):
        if not hasattr(self, "activation_gate") or not self.activation_gate.winfo_exists():
            return
        try:
            for widget_name in ("entry", "send_btn", "mic_btn", "paste_btn", "copy_btn"):
                widget = getattr(self, widget_name, None)
                if widget is None:
                    continue
                try:
                    widget.configure(state="disabled")
                except Exception:
                    pass
            first_show = not bool(getattr(self, "_activation_gate_warmed", False))
            if first_show:
                self._activation_gate_warmed = True
                self._hold_resize_guard(120)
            try:
                self.root.update_idletasks()
                self._refresh_activation_gate_layout()
            except Exception:
                pass
            self.activation_gate.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.activation_gate.lift()
            try:
                self.activation_gate.focus_set()
            except Exception:
                pass
            try:
                self._activation_gate_submit_btn.focus_set()
            except Exception:
                pass
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            self._schedule_activation_gate_layout_refresh()
            if first_show:
                self.root.after(56, self._refresh_activation_gate_layout)
                self.root.after(96, self._hide_resize_guard)
            self.set_status("Требуется активация", "warn")
            if hasattr(self, "_gate_groq_entry"):
                self._gate_groq_entry.focus_set()
        except Exception:
            pass

    def _hide_embedded_activation_gate(self):
        if not hasattr(self, "activation_gate") or not self.activation_gate.winfo_exists():
            return
        try:
            self.activation_gate.place_forget()
        except Exception:
            pass
        for widget_name in ("entry", "send_btn", "mic_btn", "paste_btn", "copy_btn"):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            try:
                widget.configure(state="normal")
            except Exception:
                pass

    def _reset_embedded_activation_gate(self):
        for var_name in (
            "_gate_groq_var",
            "_gate_tg_token_var",
            "_gate_tg_id_var",
            "_gate_user_name_var",
            "_gate_user_login_var",
        ):
            var = getattr(self, var_name, None)
            if isinstance(var, tk.StringVar):
                var.set("")

    def _submit_embedded_activation_gate(self):
        try:
            cfg = self.config_mgr
            gate_groq_var = getattr(self, "_gate_groq_var", None)
            api_key = str(gate_groq_var.get() if isinstance(gate_groq_var, tk.StringVar) else "").strip()
            if not api_key:
                messagebox.showwarning(app_brand_name(), "Введите Groq API ключ, чтобы открыть чат.")
                self.set_status("Нужен API ключ", "warn")
                return

            try:
                gate_tg_id_var = getattr(self, "_gate_tg_id_var", None)
                tg_id_raw = str(gate_tg_id_var.get() if isinstance(gate_tg_id_var, tk.StringVar) else "").strip()
                tg_id = int(tg_id_raw) if tg_id_raw else 0
            except Exception:
                tg_id = 0

            gate_theme_var = getattr(self, "_gate_theme_var", None)
            selected_theme_label = str(gate_theme_var.get() if isinstance(gate_theme_var, tk.StringVar) else "").strip()
            selected_theme_key = next((key for lbl, key in getattr(self, "_gate_theme_items", []) if lbl == selected_theme_label), "dark")
            gate_dangerous_mode_var = getattr(self, "_gate_dangerous_mode_var", None)
            selected_dangerous_label = str(gate_dangerous_mode_var.get() if isinstance(gate_dangerous_mode_var, tk.StringVar) else "").strip()
            selected_dangerous_key = next((key for lbl, key in getattr(self, "_gate_dangerous_mode_items", []) if lbl == selected_dangerous_label), "ask")
            dangerous_modes = {category: selected_dangerous_key for category in DEFAULT_PERMISSION_MODES}

            gate_tg_token_var = getattr(self, "_gate_tg_token_var", None)
            gate_user_name_var = getattr(self, "_gate_user_name_var", None)
            gate_user_login_var = getattr(self, "_gate_user_login_var", None)

            cfg.set_many({
                "api_key": api_key,
                "telegram_token": str(gate_tg_token_var.get() if isinstance(gate_tg_token_var, tk.StringVar) else "").strip(),
                "telegram_user_id": tg_id,
                "allowed_user_ids": [tg_id] if tg_id else [],
                "user_name": str(gate_user_name_var.get() if isinstance(gate_user_name_var, tk.StringVar) else "").strip(),
                "user_login": str(gate_user_login_var.get() if isinstance(gate_user_login_var, tk.StringVar) else "").strip(),
                "theme_mode": selected_theme_key,
                "dangerous_action_modes": dangerous_modes,
            })
            cfg.set_first_run_done()

            self._startup_gate_setup = False
            self.reload_services()
            self.apply_theme_runtime()
            self.refresh_mic_status_label()
            self.refresh_output_status_label()
            self.refresh_tts_status_label()
            self._hide_embedded_activation_gate()
            if not self.safe_mode:
                self.start_bg_anim()
            self._start_runtime_services()
            self.set_status("Готов", "ok")
        except Exception as exc:
            log_event(logger, "ui", "activation_submit_failed", level=logging.ERROR, error=str(exc))
            logger.exception("Activation gate submit failed")
            try:
                messagebox.showerror(app_brand_name(), f"Ошибка активации: {exc}")
            except Exception:
                pass
            self.set_status("Ошибка активации", "error")

    def on_resize(self, e=None):
        force = e is None
        widget = getattr(e, "widget", None)
        if not force and widget not in (None, self.root):
            return
        try:
            state_name = str(self.root.state() or "").lower()
        except Exception:
            state_name = "normal"
        if not force and state_name in {"iconic", "withdrawn"}:
            try:
                self._hide_resize_guard()
            except Exception:
                pass
            self._workspace_resize_in_progress = False
            try:
                setattr(self.root, "_jarvis_resize_in_progress", False)
            except Exception:
                pass
            return
        try:
            width = int(getattr(e, "width", 0) or self.root.winfo_width() or 0)
            height = int(getattr(e, "height", 0) or self.root.winfo_height() or 0)
        except Exception:
            width = height = 0
        if not force and (width <= 1 or height <= 1):
            return
        if bool(getattr(self, "_is_full_settings_open", lambda: False)()):
            if not self.is_full:
                try:
                    geom = self.root.geometry()
                    if geom and parse_geometry(geom):
                        self._normal_geometry = geom
                except Exception:
                    pass
            try:
                self._sync_control_center_window_to_root()
            except Exception:
                pass
            try:
                self._schedule_control_center_layout_refresh()
            except Exception:
                pass
            try:
                if hasattr(self, "_schedule_control_center_content_scroll_refresh"):
                    self._schedule_control_center_content_scroll_refresh()
            except Exception:
                pass
            try:
                if hasattr(self, "_refresh_activation_gate_layout") and getattr(self, "_startup_gate_setup", False):
                    self._refresh_activation_gate_layout()
            except Exception:
                pass
            return
        if not force:
            resize_signature = (width, height, bool(self.is_full), state_name)
            previous_signature = getattr(self, "_last_resize_signature", None)
            if resize_signature == previous_signature:
                return
            if previous_signature and abs(width - previous_signature[0]) < 4 and abs(height - previous_signature[1]) < 4 and bool(self.is_full) == previous_signature[2] and state_name == previous_signature[3]:
                return
            self._last_resize_signature = resize_signature
            self._workspace_resize_in_progress = True
            try:
                setattr(self.root, "_jarvis_resize_in_progress", True)
            except Exception:
                pass
            try:
                large_resize = (
                    (previous_signature is not None and abs(width - previous_signature[0]) >= 36)
                    or (previous_signature is not None and abs(height - previous_signature[1]) >= 36)
                    or (previous_signature is not None and bool(self.is_full) != bool(previous_signature[2]))
                    or (previous_signature is not None and state_name != previous_signature[3])
                    or state_name in {"zoomed"}
                    or bool(self.is_full)
                )
                if large_resize:
                    self._show_resize_guard()
            except Exception:
                pass

        if not self.is_full:
            try:
                geom = self.root.geometry()
                if geom and parse_geometry(geom):
                    self._normal_geometry = geom
            except Exception:
                pass

        live_after = getattr(self, "_resize_preview_after", None)
        if live_after:
            try:
                self.root.after_cancel(live_after)
            except Exception:
                pass
        self._resize_preview_after = None
        try:
            if hasattr(self, "_close_workspace_section_menu"):
                self._close_workspace_section_menu()
        except Exception:
            pass

        if self._resize_timer:
            self.root.after_cancel(self._resize_timer)
        settle_delay = 110 if time.monotonic() < getattr(self, "_startup_resize_freeze_until", 0.0) else 45
        self._resize_timer = self.root.after(settle_delay, self._on_resize_settle)

    def _apply_resize_preview(self):
        self._resize_preview_after = None
        try:
            self._apply_main_container_bounds()
        except Exception:
            pass

    def _get_chat_obstacle_rect(self):
        try:
            if not isinstance(getattr(self, "bg_canvas", None), tk.Canvas):
                return None
            if not hasattr(self, "chat_shell") or not self.chat_shell.winfo_exists():
                return None
            cont_bbox = self.bg_canvas.bbox(self.cont_win)
            if not cont_bbox:
                return None
            left, top, _, _ = cont_bbox
            chat_x = left + self.chat_shell.winfo_x()
            chat_y = top + self.chat_shell.winfo_y()
            chat_w = self.chat_shell.winfo_width()
            chat_h = self.chat_shell.winfo_height()
            if chat_w <= 2 or chat_h <= 2:
                return None
            return (chat_x, chat_y, chat_x + chat_w, chat_y + chat_h)
        except Exception:
            return None

    def _on_resize_settle(self):
        self._resize_timer = None
        preview_after = getattr(self, "_resize_preview_after", None)
        if preview_after:
            try:
                self.root.after_cancel(preview_after)
            except Exception:
                pass
            self._resize_preview_after = None
        try:
            self.root.update_idletasks()
            self._apply_main_container_bounds()
            self._sync_chat_canvas_width()
        except Exception:
            pass
        self._workspace_resize_in_progress = False
        try:
            setattr(self.root, "_jarvis_resize_in_progress", False)
        except Exception:
            pass
        try:
            self.refresh_workspace_layout_mode()
        except Exception:
            pass
        guard_after = getattr(self, "_resize_guard_after_id", None)
        if guard_after:
            try:
                self.root.after_cancel(guard_after)
            except Exception:
                pass
        guard_delay = 8
        try:
            remaining_ms = int(max(0.0, float(getattr(self, "_resize_guard_hold_until", 0.0) or 0.0) - time.monotonic()) * 1000)
            if remaining_ms > guard_delay:
                guard_delay = remaining_ms
        except Exception:
            pass
        self._resize_guard_after_id = self.root.after(guard_delay, self._hide_resize_guard)
        try:
            if hasattr(self, "_schedule_settings_visual_refresh") and self._is_full_settings_open():
                self._schedule_settings_visual_refresh()
        except Exception:
            pass
        if not getattr(self, "dvd_logos", None):
            return
        current_w = max(self.bg_canvas.winfo_width(), 1)
        current_h = max(self.bg_canvas.winfo_height(), 1)
        old_w, old_h = self._last_bg_canvas_size
        self._last_bg_canvas_size = (current_w, current_h)
        major_resize = abs(current_w - old_w) >= 180 or abs(current_h - old_h) >= 180
        if not self.dvd_logos:
            try:
                self._set_bg_animation_paused(False, reason="resize")
            except Exception:
                pass
            return
        for logo in list(self.dvd_logos):
            try:
                logo.ensure_visible(current_w, current_h)
            except Exception:
                pass
        if major_resize:
            try:
                self.root.after(80, lambda: self._set_bg_animation_paused(False, reason="resize"))
            except Exception:
                pass
            return
        try:
            self._set_bg_animation_paused(False, reason="resize")
        except Exception:
            pass

    def _finalize_bg_anim_restart(self):
        self._bg_rebuild_after_id = None
        if self.dvd_logos:
            for logo in list(self.dvd_logos):
                try:
                    logo.destroy()
                except Exception:
                    pass
        self.dvd_logos = []
        self.start_bg_anim(append=False)

    def restart_bg_anim(self, animated: bool = True, retire_mode: str = "edge"):
        if self._bg_rebuild_after_id is not None:
            try:
                self.root.after_cancel(self._bg_rebuild_after_id)
            except Exception:
                pass
            self._bg_rebuild_after_id = None

        if self.dvd_logos and animated:
            for logo in list(self.dvd_logos):
                try:
                    logo.begin_retire(mode=retire_mode)
                except Exception as e:
                    logger.debug(f"Background effect retire error: {e}")
            self._bg_rebuild_after_id = self.root.after(320, self._finalize_bg_anim_restart)
            return

        self._finalize_bg_anim_restart()

    def start_bg_anim(self, append: bool = False):
        if getattr(self, '_bg_anim_started', False) and not append and self.dvd_logos:
            return
        self._bg_anim_started = True

        w = max(self.bg_canvas.winfo_width(), 1)
        h = max(self.bg_canvas.winfo_height(), 1)
        if w <= 2 or h <= 2:
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            w = max(self.bg_canvas.winfo_width(), 1)
            h = max(self.bg_canvas.winfo_height(), 1)
        self._last_bg_canvas_size = (w, h)

        if self.dvd_logos:
            for logo in list(self.dvd_logos):
                try:
                    logo.destroy()
                except Exception:
                    pass
            self.dvd_logos = []
        spawn_count = max(1, min(2, int((w * h) / 1800000) + 1))
        logo_img = self.assets.get("noob")
        if not isinstance(logo_img, ImageTk.PhotoImage):
            logo_img = None
        for idx in range(spawn_count):
            logo = DvdLogoBouncer(self.bg_canvas, logo_img, w, h, spawn_hint=idx)
            logo.apply_theme()
            self.dvd_logos.append(logo)
            try:
                self.bg_canvas.tag_lower(logo.item, self.cont_win)
            except Exception:
                pass
        self._schedule_bg_anim()

    def _set_bg_animation_paused(self, paused: bool, reason: str = "ui"):
        reason_key = str(reason or "ui").strip() or "ui"
        if paused:
            self._bg_pause_reasons.add(reason_key)
        else:
            self._bg_pause_reasons.discard(reason_key)
        self._bg_anim_paused = bool(self._bg_pause_reasons)
        if self._bg_anim_paused:
            if self._bg_anim_after_id:
                try:
                    self.root.after_cancel(self._bg_anim_after_id)
                except Exception:
                    pass
                self._bg_anim_after_id = None
            return
        self._schedule_bg_anim()

    def _schedule_bg_anim(self):
        if self._bg_anim_after_id or not self.running or self._bg_anim_paused:
            return
        self._bg_anim_after_id = self.root.after(self._bg_tick_ms, self._run_bg_anim_tick)

    def _schedule_window_activity_sync(self, _event=None):
        if self._window_activity_after_id is not None:
            try:
                self.root.after_cancel(self._window_activity_after_id)
            except Exception:
                pass
        self._window_activity_after_id = self.root.after(40, self._sync_window_activity_state)

    def _sync_window_activity_state(self):
        self._window_activity_after_id = None
        try:
            state = str(self.root.state() or "").lower()
        except Exception:
            state = "normal"
        if state in {"withdrawn", "iconic"}:
            self._set_bg_animation_paused(True, reason="window_hidden")
        else:
            self._set_bg_animation_paused(False, reason="window_hidden")

        try:
            focused = self.root.focus_get() is not None or self.root.focus_displayof() is not None
        except Exception:
            focused = True
        if focused:
            self._set_bg_animation_paused(False, reason="window_focus")
        else:
            self._set_bg_animation_paused(True, reason="window_focus")

    def _run_bg_anim_tick(self):
        self._bg_anim_after_id = None
        if not self.running or self._bg_anim_paused:
            return
        try:
            current_w = self.bg_canvas.winfo_width()
            current_h = self.bg_canvas.winfo_height()
            if self.dvd_logos and current_w > 2 and current_h > 2:
                if len(self.dvd_logos) > 6:
                    for extra in self.dvd_logos[6:]:
                        try:
                            extra.destroy()
                        except Exception:
                            pass
                    self.dvd_logos = self.dvd_logos[:6]
                for logo in list(self.dvd_logos):
                    logo.move(current_w, current_h)
                    if getattr(logo, "dead", False):
                        self.dvd_logos.remove(logo)
        except Exception as e:
            logger.debug(f"Background animation tick error: {e}")
        self._schedule_bg_anim()

    def _cancel_status_reset(self):
        if self._status_reset_after_id is not None:
            try:
                self.root.after_cancel(self._status_reset_after_id)
            except Exception:
                pass
            self._status_reset_after_id = None

    def _schedule_status_reset(self, duration_ms: int = 2000):
        wait_ms = max(300, int(duration_ms or 2000))
        self._cancel_status_reset()
        self._status_reset_after_id = self.root.after(wait_ms, self._reset_status_ready)

    def set_status(self, text, tone="neutral", auto_reset: bool = True, duration_ms: int = 2000):
        colors = {"neutral": Theme.FG_SECONDARY, "busy": Theme.STATUS_BUSY, "ok": Theme.STATUS_OK,
                  "warn": Theme.STATUS_WARN, "error": Theme.STATUS_ERROR}
        def _set():
            self.status_var.set(text)
            self.status_label.config(fg=colors.get(tone, Theme.FG_SECONDARY))
            msg = str(text or "").strip().lower()
            if auto_reset and msg and msg != "готов" and tone != "busy":
                self._schedule_status_reset(duration_ms)
            elif msg == "готов" or tone == "busy":
                self._cancel_status_reset()
        self.root.after(0, _set)

    def set_status_temp(self, text, tone="neutral", duration_ms: int = 2000):
        self.set_status(text, tone, auto_reset=True, duration_ms=duration_ms)

    def _reset_status_ready(self):
        self._status_reset_after_id = None
        self.set_status("Готов", "ok")


    def stop_speaking(self):
        self._tts_stop_event.set()
        with self.speaking_lock:
            if self.tts_engine:
                try:
                    self.tts_engine.stop()
                except Exception as e:
                    logger.error(f"TTS stop error: {e}")
            self._stop_active_audio_stream_locked()
            if pygame is not None:
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
            self.speaking = False

    def say(self, text):
        def _speak():
            if not str(text or "").strip():
                return
            if self.speaking:
                self.stop_speaking()
                time.sleep(0.05)
            self._tts_stop_event.clear()
            with self.speaking_lock:
                self.speaking = True
            try:
                self._speak_by_provider(text)
            except InterruptedError:
                pass
            except Exception as e:
                logger.error(f"TTS error: {e}")
                try:
                    self._speak_with_pyttsx3(text)
                except InterruptedError:
                    pass
                except Exception as fallback_exc:
                    logger.error(f"Fallback TTS error: {fallback_exc}")
            finally:
                with self.speaking_lock:
                    self._stop_active_audio_stream_locked()
                    self.speaking = False
        t = threading.Thread(target=_speak, daemon=True, name="TTS-Thread")
        t.start()


    def execute_action(self, action: str, arg: Any = None, raw_cmd: str = "", speak: bool = True, reply_callback=None) -> str:
        try:
            action_executor = getattr(self, "action_executor", None)
            log_event(
                logger,
                "actions",
                "execute_action",
                action=str(action or ""),
                has_arg=bool(str(arg or "").strip()),
                origin=raw_cmd or "voice/chat",
            )

            def out(msg):
                if msg and hasattr(self, "_set_live_pipeline_step"):
                    try:
                        self._set_live_pipeline_step(executed=msg)
                    except Exception:
                        pass
                if speak and msg:
                    if reply_callback:
                        reply_callback(msg)
                    else:
                        self.speak_msg(msg)
                return msg

            action_success_messages = {
                "music": "Открываю музыку. Приятного прослушивания.",
                "youtube": "Открываю YouTube. Приятного просмотра.",
                "fortnite": "Запускаю Fortnite. Приятной игры.",
                "cs2": "Запускаю CS2. Приятной игры.",
                "dbd": "Запускаю DBD. Приятной игры.",
                "deadlock": "Запускаю Deadlock. Приятной игры.",
                "roblox": "Запускаю Roblox. Приятной игры.",
            }

            if hasattr(self, "_set_live_pipeline_step"):
                try:
                    label = action_executor.describe(action, arg) if action_executor else permission_action_label(action, arg)
                    self._set_live_pipeline_step(understood=label)
                except Exception:
                    pass

            if action_executor:
                is_allowed = action_executor.allow(action, arg, origin=raw_cmd or "voice/chat")
            else:
                permission_category = permission_category_for_action(action)
                is_allowed = not permission_category or ask_permission(
                    self,
                    action,
                    arg,
                    category=permission_category,
                    origin=raw_cmd or "voice/chat",
                )
            if not is_allowed:
                return out("Действие отменено. Разрешение не выдано.")

            if action == "close_app":
                return out("Выполнено!" if close_app(arg) else "Закрытие не поддерживается.")
            if action == "open_dynamic_app":
                entry = get_dynamic_entry_by_key(str(arg or "")) or find_dynamic_entry(str(arg or ""))
                if entry and launch_dynamic_entry(entry):
                    return out("Выполнено!")
                return out("Не нашёл приложение для запуска.")
            if action == "timur_son":
                return out("ТИМУРКИНСЫН! 😎")
            if action in APP_OPEN_FUNCS:
                try:
                    APP_OPEN_FUNCS[action]()
                    return out(action_success_messages.get(str(action or "").strip().lower(), "Выполнено!"))
                except Exception as e:
                    log_event(logger, "actions", "execute_action_failed", level=logging.ERROR, action=action, error=str(e))
                    return self.report_error(f"Ошибка запуска {action}", e, speak=speak)

            if action == "shutdown": shutdown_pc(); return out("До встречи.")
            if action == "restart_pc": restart_pc(); return out("Перезагрузка.")
            if action == "lock": lock_pc(); return out("Экран заблокирован.")
            if action == "media_pause": return out("Пауза.") if maybe_press("playpause") else out("Не получилось.")
            if action == "media_play": return out("Продолжить.") if maybe_press("playpause") else out("Не получилось.")
            if action == "volume_up": return out("Громче.") if maybe_press("volumeup",10) else out("Не получилось.")
            if action == "volume_down": return out("Тише.") if maybe_press("volumedown",10) else out("Не получилось.")
            if action == "media_next": return out("Дальше.") if maybe_press("nexttrack") else out("Не получилось.")
            if action == "media_prev": return out("Назад.") if maybe_press("prevtrack") else out("Не получилось.")
            if action == "time": return out(get_time_text())
            if action == "date": return out(get_date_text())
            if action == "weather": open_weather(); return out("Погода.")
            if action == "search": open_url_search(arg or ""); return out("Ищу.")
            if action == "reminder":
                sec, txt = arg
                self.reminder_scheduler.add(sec, txt)
                return out(f"Напомню через {sec//60} минут: {txt}")
            if action == "history":
                self.add_msg(db.history_text(6), "bot")
                return out("Показываю историю.")
            if action == "repeat":
                return out(self.last_ai_reply if self.last_ai_reply else "Нечего повторять.")
            return out("Не понял команду.")
        except Exception as e:
            log_event(logger, "actions", "execute_action_failed", level=logging.ERROR, action=action, error=str(e))
            return self.report_error(f"Ошибка команды {action}", e, speak=speak)

    def _summarize_multi_action_reply(self, results) -> str:
        normalized = [str(item or "").strip() for item in (results or []) if str(item or "").strip()]
        if not normalized:
            return "Не удалось выполнить команды."
        lowered = [normalize_text(item) for item in normalized]
        success = [
            item
            for item, low in zip(normalized, lowered)
            if "не удалось" not in low
            and "не понял" not in low
            and "ошибка" not in low
        ]
        blocked = [item for item, low in zip(normalized, lowered) if "разрешение не выдано" in low or "отменено" in low]
        if success and len(success) > 1:
            return "Готово: выполнил несколько действий."
        if success:
            return success[-1]
        if blocked:
            return blocked[-1]
        return normalized[-1]

    def on_reminder(self, text):
        msg = f"⏰ Напоминание: {text}"
        self.speak_msg(msg)
        if self.telegram_bot and self.config_mgr.get_telegram_user_id():
            self.telegram_bot.send_message(self.config_mgr.get_telegram_user_id(), msg)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _ai_call(self, messages):
        return self.groq_client.chat.completions.create(
            model=CONFIG["model"],
            messages=messages,
            temperature=CONFIG["temperature"],
            max_tokens=CONFIG["max_tokens"],
        )

    def _friendly_ai_error_text(self, error: Exception) -> str:
        raw = error
        if RetryError is not None and isinstance(error, RetryError):
            try:
                raw = error.last_attempt.exception() or error
            except Exception:
                raw = error
        text = str(raw or error or "").strip()
        low = text.lower()
        type_name = raw.__class__.__name__.lower()
        if "invalid api key" in low or "invalid_api_key" in low or "authentication" in type_name:
            return "⚠️ Неверный Groq API ключ. Откройте Настройки -> Основные и вставьте актуальный ключ."
        if "rate" in low and "limit" in low:
            return "⏳ Лимит запросов Groq временно исчерпан. Подождите немного и повторите."
        if "timed out" in low or "timeout" in low or "connection" in low:
            return "🌐 Groq сейчас недоступен по сети. Проверьте интернет, VPN/Proxy и повторите."
        return ""

    def ai_handler(self, cmd: str, reply_callback=None) -> None:
        if not self.is_online:
            msg = "🌐 Нет интернета.\nGroq AI и поиск недоступны. Подключитесь к сети."
            self.root.after(0, lambda: self.add_msg(msg, "bot"))
            self.say(msg)
            return

        if not self.groq_client:
            msg = "⚠️ ИИ сейчас недоступен.\n\nПерейдите в Настройки → введите Groq API-ключ."
            self.root.after(0, lambda: self.add_msg(msg, "bot"))
            self.say(msg)
            return

        with self.context_lock:
            self.context_messages.append({"role": "user", "content": cmd})
        db.save_context("user", cmd)

        system_prompt = PROMPT_MGR.get_system_prompt()
        if CONFIG_MGR.get_free_chat_mode():
            system_prompt += (
                " Дополнение режима: свободный стиль общения включён. "
                "В chat-ответах можно писать естественно, без официоза и без жёсткого лимита по длине, "
                "если это полезно пользователю."
            )
        with self.context_lock:
            messages = [{"role": "system", "content": system_prompt}] + list(self.context_messages)

        self.set_status("Думаю...", "busy")
        self.start_typing_indicator()
        try:
            if retry is not None:
                resp = self._ai_call(messages)
            else:
                resp = self.groq_client.chat.completions.create(
                    model=CONFIG["model"], messages=messages,
                    temperature=CONFIG["temperature"], max_tokens=CONFIG["max_tokens"]
                )
            text = resp.choices[0].message.content.strip()
            with self.context_lock:
                self.context_messages.append({"role": "assistant", "content": text})
            db.save_context("assistant", text)

            parsed = extract_json_block(text)
            if parsed is None:
                msg = text[:300] if text else "Не понял команду."
                normalized_msg = normalize_text(msg)
                if normalized_msg.startswith("продолжение следует") or normalized_msg.startswith("to be continued"):
                    msg = "Модель вернула обрывок ответа. Повторите запрос или переключите мозг JARVIS."
                if hasattr(self, "_set_live_pipeline_step"):
                    try:
                        self._set_live_pipeline_step(understood="Свободный ответ", executed=msg[:120])
                    except Exception:
                        pass
                db.save_command(cmd, msg)
                if reply_callback:
                    reply_callback(msg)
                else:
                    self.speak_msg(msg)
                return

            if isinstance(parsed, dict) and "items" in parsed:
                items = parsed.get("items")
                if isinstance(items, list):
                    self.dispatch_ai_intents(items, cmd, reply_callback=reply_callback)
                elif isinstance(items, dict):
                    self.dispatch_ai_intents([items], cmd, reply_callback=reply_callback)
                else:
                    # Иногда модель возвращает items строкой. Пробуем достать reply, иначе fallback.
                    reply_text = str(parsed.get("reply", "") or "").strip()
                    if reply_text:
                        if reply_callback:
                            reply_callback(reply_text)
                        else:
                            self.speak_msg(reply_text)
                    else:
                        msg = text[:300] if text else "Не понял команду."
                        if reply_callback:
                            reply_callback(msg)
                        else:
                            self.speak_msg(msg)
            elif isinstance(parsed, dict):
                self.dispatch_ai_intents([parsed], cmd, reply_callback=reply_callback)
            elif isinstance(parsed, list):
                self.dispatch_ai_intents(parsed, cmd, reply_callback=reply_callback)
            else:
                reply_text = None
                if isinstance(parsed, dict) and "reply" in parsed:
                    reply_text = parsed["reply"]
                elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict) and "reply" in parsed[0]:
                    reply_text = parsed[0]["reply"]
                
                msg = reply_text if reply_text else "Не понял команду."
                db.save_command(cmd, msg)
                if reply_callback:
                    reply_callback(msg)
                else:
                    self.speak_msg(msg)
        except (APIError, APIConnectionError, RateLimitError) as e:
            friendly = self._friendly_ai_error_text(e)
            if friendly:
                if reply_callback:
                    reply_callback(friendly)
                else:
                    self.speak_msg(friendly)
            else:
                self.report_error("Ошибка ИИ", e, speak=True)
        except RetryError as e:
            friendly = self._friendly_ai_error_text(e)
            if friendly:
                if reply_callback:
                    reply_callback(friendly)
                else:
                    self.speak_msg(friendly)
            else:
                self.report_error("Ошибка ИИ", e, speak=True)
        except Exception as e:
            self.report_error("Неизвестная ошибка ИИ", e, speak=True)
        finally:
            self.stop_typing_indicator()
            self.set_status("Готов", "ok")

    def dispatch_ai_intents(self, intents, raw_cmd, reply_callback=None):
        if not intents:
            msg = "Не понял команду."
            if hasattr(self, "_set_live_pipeline_step"):
                try:
                    self._set_live_pipeline_step(executed=msg)
                except Exception:
                    pass
            if reply_callback:
                reply_callback(msg)
            else:
                self.speak_msg(msg)
            return
        if isinstance(intents, dict):
            intents = [intents]
        items = [self._normalize_ai_item(item) for item in (intents or [])[:6]]
        command_actions = 0
        for item in items:
            try:
                kind = normalize_text(str(item.get("type", "chat") or "chat"))
                action = str(item.get("action", "chat") or "").strip().lower()
                is_command = ("command" in kind) or (action in APP_OPEN_FUNCS) or (action in {"close_app", "open_dynamic_app", "search", "reminder", "history", "repeat", "time", "date", "weather", "media_pause", "media_play", "media_next", "media_prev", "volume_up", "volume_down", "shutdown", "restart_pc", "lock"})
                if is_command and action and action != "chat":
                    command_actions += 1
            except Exception:
                continue
        multi_command_reply = command_actions > 1
        multi_results = []
        for item in items:
            try:
                kind = normalize_text(str(item.get("type", "chat") or "chat"))
                action = item.get("action", "chat").strip().lower()
                arg = item.get("arg", "")
                reply = item.get("reply", "").strip()
                is_command = ("command" in kind) or (action in APP_OPEN_FUNCS) or (action in {"close_app", "open_dynamic_app", "search", "reminder", "history", "repeat", "time", "date", "weather", "media_pause", "media_play", "media_next", "media_prev", "volume_up", "volume_down", "shutdown", "restart_pc", "lock"})
                if is_command and action and action != "chat":
                    if hasattr(self, "_set_live_pipeline_step"):
                        try:
                            self._set_live_pipeline_step(understood=permission_action_label(action, arg))
                        except Exception:
                            pass
                    result = self.execute_action(
                        action,
                        arg,
                        raw_cmd,
                        speak=False,
                        reply_callback=None if multi_command_reply else reply_callback,
                    )
                    if result:
                        multi_results.append(result)
                        self.last_ai_reply = result
                        db.save_command(raw_cmd, result)
                        self._learn_from_intent(raw_cmd, action, arg, result)
                    if reply and multi_command_reply:
                        multi_results.append(reply)
                    elif reply:
                        if reply_callback:
                            reply_callback(reply)
                        else:
                            self.speak_msg(reply)
                    elif not multi_command_reply:
                        msg = result if result else "Не удалось выполнить команду."
                        if reply_callback:
                            reply_callback(msg)
                        else:
                            self.speak_msg(msg)
                else:
                    if reply:
                        self.last_ai_reply = reply
                        if hasattr(self, "_set_live_pipeline_step"):
                            try:
                                self._set_live_pipeline_step(understood="Свободный ответ", executed=reply[:120])
                            except Exception:
                                pass
                        if reply_callback:
                            reply_callback(reply)
                        else:
                            self.speak_msg(reply)
                    else:
                        msg = "Не понял команду."
                        if hasattr(self, "_set_live_pipeline_step"):
                            try:
                                self._set_live_pipeline_step(executed=msg)
                            except Exception:
                                pass
                        if reply_callback:
                            reply_callback(msg)
                        else:
                            self.speak_msg(msg)
            except Exception as e:
                self.report_error("Ошибка обработки ИИ", e, speak=True)

        if multi_command_reply:
            summary = self._summarize_multi_action_reply(multi_results)
            if reply_callback:
                reply_callback(summary)
            else:
                self.speak_msg(summary)

    def _normalize_ai_item(self, item):
        if not isinstance(item, dict):
            return {"type": "chat", "action": "chat", "arg": "", "reply": ""}

        supported = _supported_ai_actions()
        action = str(item.get("action", "chat") or "chat").strip().lower()
        arg = item.get("arg", "")
        reply = str(item.get("reply", "") or "").strip()

        if action in {"greeting", "answer", "response", "conversation", "message"}:
            action = "chat"

        if action == "browser":
            arg_text = str(arg or "").strip()
            arg_low = arg_text.lower()
            if "youtube.com" in arg_low or "youtu.be" in arg_low:
                action, arg = "youtube", ""
            elif arg_text:
                action = "search"

        if action == "open_dynamic_app":
            entry = get_dynamic_entry_by_key(str(arg or "")) or find_dynamic_entry(str(arg or ""))
            if entry:
                arg = entry["key"]
            else:
                app_key = find_app_key(str(arg or ""))
                if app_key:
                    action, arg = app_key, ""

        if action == "close_app":
            resolved_key = find_app_key(str(arg or ""))
            if not resolved_key:
                entry = find_dynamic_entry(str(arg or ""))
                resolved_key = entry["key"] if entry else ""
            if resolved_key:
                arg = resolved_key

        if action not in supported:
            resolved_action = find_app_key(action)
            if resolved_action:
                action = resolved_action

        if action not in supported:
            action = "chat"

        return {
            "type": "command" if action in supported and action != "chat" else "chat",
            "action": action,
            "arg": arg if arg is not None else "",
            "reply": reply,
        }

    def _learn_from_intent(self, raw_cmd: str, action: str, arg: Any, result: str):
        if not CONFIG_MGR.get_self_learning_enabled():
            return
        pattern = normalize_text(raw_cmd)
        if not pattern or len(pattern) < 3 or _is_learned_pattern_generic(pattern):
            return
        action = str(action or "").strip().lower()
        if not action or action == "chat":
            return

        result_text = normalize_text(str(result or ""))
        if "не " in result_text and "выполн" not in result_text:
            return

        allowed_actions = set(SUPPORTED_ACTION_KEYS) - {
            "shutdown",
            "restart_pc",
            "lock",
            "reminder",
            "history",
            "repeat",
            "timur_son",
        }
        if action not in allowed_actions:
            return

        learned = list(CONFIG_MGR.get_learned_commands() or [])
        normalized_arg = arg
        for item in learned:
            if not isinstance(item, dict):
                continue
            if normalize_text(item.get("pattern", "")) == pattern and str(item.get("action", "")).strip().lower() == action:
                item["arg"] = normalized_arg
                CONFIG_MGR.set_learned_commands(learned[-120:])
                return

        learned.append({"pattern": pattern, "action": action, "arg": normalized_arg})
        CONFIG_MGR.set_learned_commands(learned[-120:])

    def process_query(self, query: str, reply_callback=None) -> None:
        raw_query = str(query or "").strip()
        self._last_user_query = raw_query
        if self._startup_gate_setup and not bool(str(self.config_mgr.get_api_key() or "").strip()):
            msg = "Сначала завершите активацию в стартовом окне."
            if reply_callback:
                reply_callback(msg)
            else:
                self.root.after(0, lambda: self.add_msg(msg, "bot"))
                self.root.after(0, lambda: self.run_setup_wizard(True))
            return

        if _is_emoji_message(raw_query):
            if reply_callback:
                reply_callback(raw_query)
            else:
                self.root.after(0, lambda t=raw_query: self.add_msg(t, "bot"))
            self.set_status("Готов", "ok")
            return

        text = normalize_text(raw_query)
        if not text:
            return
        if hasattr(self, "_set_live_pipeline_step"):
            try:
                self._set_live_pipeline_step(reset=True, heard=raw_query, recognized=text)
            except Exception:
                pass

        with self._process_state_lock:
            if self.processing_command:
                busy_msg = "Уже обрабатываю предыдущую команду. Повторите через секунду."
                if reply_callback:
                    reply_callback(busy_msg)
                else:
                    self.root.after(0, lambda: self.add_msg(busy_msg, "bot"))
                return
            self.processing_command = True
        self.set_status("Обрабатываю...", "busy")
        try:
            parts = [p.strip() for p in SPLIT_PATTERN.split(text) if p.strip()] or [text]

            local_actions = []
            ai_parts = []
            simple_only = True

            for cmd in parts:
                act, arg = CommandParser.classify_local(cmd)
                if act:
                    local_actions.append((act, arg, cmd))
                    if act not in SIMPLE_BATCH_ACTIONS:
                        simple_only = False
                else:
                    ai_parts.append(cmd)
                    simple_only = False

            if len(parts) > 3 and local_actions and not ai_parts and simple_only:
                futures = [
                    self.executor.submit(self.execute_action, act, arg, cmd, False, None)
                    for act, arg, cmd in local_actions
                ]
                any_ok = False
                for fut in futures:
                    try:
                        res = fut.result(timeout=7)
                        if res:
                            any_ok = True
                            self.last_ai_reply = res
                    except FutureTimeoutError:
                        logger.warning("Command execution timeout")
                    except Exception as e:
                        self.report_error("Ошибка пакетной команды", e, speak=True)
                msg = "Выполнено!" if any_ok else "Не удалось выполнить команды."
                if reply_callback:
                    reply_callback(msg)
                else:
                    self.speak_msg(msg)
                self.set_status("Готов", "ok")
                return

            for act, arg, cmd in local_actions:
                if hasattr(self, "_set_live_pipeline_step"):
                    try:
                        self._set_live_pipeline_step(understood=permission_action_label(act, arg))
                    except Exception:
                        pass
                res = self.execute_action(act, arg, cmd, speak=True, reply_callback=reply_callback)
                if res:
                    self.last_ai_reply = res
                    db.save_command(cmd, res)
            for cmd in ai_parts:
                self.ai_handler(cmd, reply_callback=reply_callback)

            self.set_status("Готов", "ok")
        finally:
            with self._process_state_lock:
                self.processing_command = False


    def initial_push_history(self, text: str):
        if text:
            if not hasattr(self, 'command_history'):
                self.command_history = deque(maxlen=100)
            self.command_history.append(text)

    def process_telegram_query(self, query):
        responses = []
        def capture(msg):
            responses.append(msg)
        self.process_query(query, reply_callback=capture)
        return "\n".join(responses).strip() or "Не понял команду."

    def toggle_window(self):
        if self.root.state() in ('withdrawn', 'iconic'):
            self.show_window()
        else:
            self.hide_to_tray()

    def toggle_fs(self, e=None):
        self.is_full = not self.is_full
        first_fullscreen_transition = not bool(getattr(self, "_fullscreen_transition_warmed", False))
        self._fullscreen_transition_warmed = True
        self._startup_resize_freeze_until = time.monotonic() + (0.2 if first_fullscreen_transition else 0.12)
        self._last_resize_signature = None
        self._workspace_resize_in_progress = True
        try:
            setattr(self.root, "_jarvis_resize_in_progress", True)
        except Exception:
            pass
        try:
            self._hold_resize_guard(180 if first_fullscreen_transition else 80)
        except Exception:
            pass
        try:
            if hasattr(self, "_close_workspace_section_menu"):
                self._close_workspace_section_menu()
        except Exception:
            pass
        if self.is_full:
            try:
                self._normal_geometry = self.root.geometry()
            except Exception:
                pass
            self.root.attributes("-fullscreen", True)
        else:
            self.root.attributes("-fullscreen", False)
            target = self._normal_geometry or self._window_geometry_preset()[2]
            try:
                self.root.geometry(target)
            except Exception:
                pass
        self.root.after(12, self.on_resize)
        self.root.after(52 if first_fullscreen_transition else 36, self._on_resize_settle)
        self.root.after(86 if first_fullscreen_transition else 52, self._prime_after_visual_transition)

    def shutdown(self):
        logger.info("Shutting down...")
        self._tts_stop_event.set()
        try:
            if self.root.state() != 'withdrawn':
                geom = self._normal_geometry if self.is_full else self.root.geometry()
                if geom and parse_geometry(geom):
                    CONFIG_MGR.set_window_geometry(geom)
        except Exception:
            pass
        self.running = False
        if self._bg_anim_after_id:
            try:
                self.root.after_cancel(self._bg_anim_after_id)
            except Exception:
                pass
            self._bg_anim_after_id = None
        if self._bg_rebuild_after_id:
            try:
                self.root.after_cancel(self._bg_rebuild_after_id)
            except Exception:
                pass
            self._bg_rebuild_after_id = None
        if self._resize_timer:
            try:
                self.root.after_cancel(self._resize_timer)
            except Exception:
                pass
            self._resize_timer = None
        if self._status_reset_after_id is not None:
            try:
                self.root.after_cancel(self._status_reset_after_id)
            except Exception:
                pass
            self._status_reset_after_id = None
        if self.reminder_scheduler:
            self.reminder_scheduler.stop()
            self.reminder_scheduler = None
        if self.telegram_bot:
            self.telegram_bot.stop()
            self.telegram_bot = None
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        if self.tts_engine:
            self._stop_tts_engine_quick()
            self.tts_engine = None
        voice_meter_thread = getattr(self, "_voice_meter_thread", None)
        if voice_meter_thread and voice_meter_thread.is_alive():
            try:
                voice_meter_thread.join(timeout=0.8)
            except Exception:
                pass
        with self.speaking_lock:
            self._stop_active_audio_stream_locked()
        if pygame is not None:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
                    pygame.mixer.quit()
            except Exception:
                pass
        if keyboard:
            try:
                keyboard.remove_hotkey('win+j')
            except Exception:
                pass
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        db.shutdown()
        logger.info("Shutdown complete.")

# =========================================================
# BACKGROUND EFFECT (noob drift)
# =========================================================
# MAIN
# =========================================================
def _supported_ai_actions():
    return set(SUPPORTED_ACTION_KEYS) | {"chat"}


if __name__ == "__main__":
    def is_already_running():
        mutex_name = "JarvisAppSingleInstanceMutex"
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        return ctypes.windll.kernel32.GetLastError() == 183

    if is_already_running():
        messagebox.showwarning(app_brand_name(), "Программа уже запущена.")
        sys.exit(0)

    set_windows_app_id()
    root = tk.Tk()
    try:
        root.withdraw()
    except Exception:
        pass
    app = JarvisApp(root)
    try:
        root.mainloop()
    finally:
        try:
            app.shutdown()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

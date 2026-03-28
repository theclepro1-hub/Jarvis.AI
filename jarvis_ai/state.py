import json
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List

from .branding import APP_LOGGER_NAME
from .release_meta import DEFAULT_GITHUB_REPO, DEFAULT_RELEASE_API_URL
from .storage import config_path, db_path, prompts_dir

logger = logging.getLogger(APP_LOGGER_NAME)
CONFIG_SCHEMA_VERSION = 4

LOCAL_APPDATA = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
ROAMING_APPDATA = os.getenv("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
USER_PROFILE = os.path.expanduser("~")
DEFAULT_CHAT_MODEL = "groq/compound-mini"
DEFAULT_CHAT_TEMPERATURE = 0.0
DEFAULT_CHAT_MAX_TOKENS = 280
DEFAULT_SYSTEM_PROMPT = (
    "You are the brain of the Windows assistant Jarvis AI 2.0. "
    "Understand natural Russian user requests and always reply in Russian. "
    "Return ONLY valid JSON without markdown, comments, code fences, or extra text. "
    "Schema: {\"type\":\"commands|chat\",\"items\":[{\"type\":\"command|chat\",\"action\":\"...\",\"arg\":\"...\",\"reply\":\"...\"}]}. "
    "Always keep items as an array. "
    "Use type=\"commands\" when the user asks for local, system, media, app, reminder, or launcher actions. "
    "Use type=\"chat\" only for normal conversation or pure text answers. "
    "For chat answers use exactly one item with type=\"chat\", action=\"chat\", arg=\"\", and a short natural reply. "
    "Allowed command actions only: music,youtube,ozon,wildberries,browser,cs2,fortnite,dbd,deadlock,steam,settings,twitch,roblox,discord,notepad,calc,taskmgr,explorer,downloads,documents,desktop,restart_explorer,restart_pc,search,time,date,weather,media_pause,media_play,media_next,media_prev,volume_up,volume_down,shutdown,lock,close_app,open_dynamic_app,reminder,history,repeat,telegram,timur_son. "
    "Do not invent new action names. "
    "When the user asks to open, launch, start, close, search, control media, tell time/date/weather, or run a local action, prefer commands over chat. "
    "If the target matches a known built-in app or site, use that exact action instead of browser. "
    "If the target looks like a user-installed Windows app or game and is not built-in, use open_dynamic_app. "
    "Examples: "
    "user='открой ютуб' -> {\"type\":\"commands\",\"items\":[{\"type\":\"command\",\"action\":\"youtube\",\"arg\":\"\",\"reply\":\"Открываю YouTube.\"}]}; "
    "user='открой дискорд и стим' -> {\"type\":\"commands\",\"items\":[{\"type\":\"command\",\"action\":\"discord\",\"arg\":\"\",\"reply\":\"Открываю Discord.\"},{\"type\":\"command\",\"action\":\"steam\",\"arg\":\"\",\"reply\":\"Открываю Steam.\"}]}; "
    "user='который час' -> {\"type\":\"commands\",\"items\":[{\"type\":\"command\",\"action\":\"time\",\"arg\":\"\",\"reply\":\"Сейчас покажу время.\"}]}; "
    "user='открой фотошоп' -> {\"type\":\"commands\",\"items\":[{\"type\":\"command\",\"action\":\"open_dynamic_app\",\"arg\":\"фотошоп\",\"reply\":\"Пробую открыть фотошоп.\"}]}; "
    "user='привет' -> {\"type\":\"chat\",\"items\":[{\"type\":\"chat\",\"action\":\"chat\",\"arg\":\"\",\"reply\":\"Привет! Чем помочь?\"}]}. "
    "For search put the plain query into arg. "
    "For close_app put the internal app key into arg. "
    "For open_dynamic_app put the dynamic app key or the app display name into arg. "
    "For reminder encode arg as \"seconds|text\". "
    "For multiple commands return multiple command items in execution order. "
    "Keep reply concise, helpful, and friendly."
)

_GENERIC_LEARNED_PATTERNS = {
    "открой", "открыть", "запусти", "запустить", "включи", "включить",
    "закрой", "закрыть", "выключи", "выключить", "start", "open", "close",
}


def _normalize_pattern_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower().replace("ё", "е"))


def _is_learned_pattern_generic(pattern: str) -> bool:
    norm = _normalize_pattern_text(pattern)
    if not norm:
        return True
    words = norm.split()
    if len(words) < 2:
        return True
    return norm in _GENERIC_LEARNED_PATTERNS


def get_config_path():
    return config_path()


def get_db_path():
    return db_path()


def get_prompts_dir():
    return prompts_dir()


def _prompt_needs_repair(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    if "Return ONLY valid JSON" in raw and "Jarvis AI 2.0" in raw:
        return False
    suspicious_markers = ("Р", "СЃ", "вЂ", "рџ", "Џ")
    return any(marker in raw for marker in suspicious_markers)

# =========================================================
# CONFIGURATION MANAGER (единый)
# =========================================================

class ConfigManager:
    def __init__(self):
        self.config_path = get_config_path()
        self.default_config = self._load_defaults()
        self._lock = threading.RLock()
        self._config = self._load_config()
        self._validate()
        self.save()

    def _load_defaults(self):
        return {
            "config_version": CONFIG_SCHEMA_VERSION,
            "api_key": "",
            "model": DEFAULT_CHAT_MODEL,
            "temperature": DEFAULT_CHAT_TEMPERATURE,
            "max_tokens": DEFAULT_CHAT_MAX_TOKENS,
            "telegram_token": "",
            "telegram_user_id": 0,
            "user_login": "",
            "allowed_user_ids": [],
            "single_user_mode": True,
            "github_repo": DEFAULT_GITHUB_REPO,
            "update_manifest_url": DEFAULT_RELEASE_API_URL,
            "update_download_url": "",
            "update_asset_name": "setup",
            "auto_update": True,
            "update_check_on_start": True,
            "mic_device_index": None,
            "mic_device_name": "",
            "output_device_index": None,
            "output_device_name": "",
            "fortnite_roots": [r"D:\Epic Games", r"D:\Fortnite"],
            "yandex_music_path": os.path.join(LOCAL_APPDATA, r"Programs\YandexMusic\Яндекс Музыка.exe"),
            "discord_candidates": [
                os.path.join(LOCAL_APPDATA, r"Discord\Discord.exe"),
            ],
            "steam_path": r"C:\Program Files (x86)\Steam\Steam.exe",
            "epic_launcher_path": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
            "telegram_desktop_path": os.path.join(ROAMING_APPDATA, r"Telegram Desktop\Telegram.exe"),
            "user_name": "",
            "autostart": False,
            "voice_index": 0,
            "voice_rate": 240,
            "voice_volume": 1.0,
            "tts_provider": "pyttsx3",
            "edge_tts_voice": "ru-RU-DmitryNeural",
            "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY", ""),
            "elevenlabs_voice_id": "",
            "elevenlabs_model_id": "eleven_flash_v2_5",
            "personality": "default",
            "window_geometry": "1180x820+180+80",
            "available_version": "",
            "first_run_done": False,
            "theme_mode": "dark",
            "ui_density": "comfortable",
            "focus_mode_enabled": False,
            "advanced_tabs_enabled": True,
            "empty_state_hints_enabled": True,
            "helper_guides_enabled": True,
            "close_behavior": "exit",
            "dpi_adaptation_enabled": True,
            "ui_scale_percent": 100,
            "listening_profile": "normal",
            "device_profile_mode": "auto",
            "device_profile_overrides": {
                "headset": "boost",
                "usb_mic": "boost",
                "built_in": "normal",
                "webcam": "normal",
                "default": "normal",
            },
            "wake_word_boost": True,
            "wake_debug_enabled": True,
            "microphone_meter_enabled": True,
            "active_listening_enabled": True,
            "safe_mode_enabled": False,
            "noise_suppression_enabled": True,
            "vad_enabled": True,
            "hybrid_brain_enabled": True,
            "explain_actions_enabled": True,
            "auto_recovery_enabled": True,
            "release_channel": "stable",
            "snapshot_before_update": True,
            "portable_bundle_enabled": True,
            "release_lock_enabled": True,
            "readiness_last_report": [],
            "readiness_last_summary": "",
            "background_self_check": True,
            "self_check_interval_min": 10,
            "proxy_url": "",
            "user_avatar_path": "",
            "free_chat_mode": False,
            "last_update_notice_version": "",
            "ai_simple_labels": True,
            "user_memory_items": [],
            "scenarios": [],
            "current_scenario": "",
            "last_control_center_section": "main",
            "human_log_entries": [],
            "action_history_entries": [],
            "plugin_pack_last_path": "",
            "fullscreen_layout": "mission_control",
            "update_trusted_hosts": [
                "api.github.com",
                "github.com",
                "objects.githubusercontent.com",
                "release-assets.githubusercontent.com",
                "github-releases.githubusercontent.com",
                "raw.githubusercontent.com",
                "githubusercontent.com",
            ],
            "custom_apps": [],
            "launcher_games": [],
            "learned_commands": [],
            "self_learning_enabled": True,
        }

    def _load_config(self):
        cfg = self.default_config.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                if not str(raw or "").strip():
                    return cfg
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    cfg.update(loaded)
            except Exception as e:
                logger.error(f"Error loading config: {e}")
        return cfg

    def _validate(self):
        cfg = self._config

        try:
            cfg["config_version"] = int(cfg.get("config_version", 0) or 0)
        except Exception:
            cfg["config_version"] = 0

        if cfg.get("telegram_user_id") in (None, "", 0):
            old_ids = cfg.get("allowed_user_ids", [])
            if isinstance(old_ids, list) and old_ids:
                try:
                    cfg["telegram_user_id"] = int(old_ids[0])
                except Exception:
                    cfg["telegram_user_id"] = 0

        if not isinstance(cfg.get("allowed_user_ids"), list):
            cfg["allowed_user_ids"] = []
        if cfg.get("telegram_user_id"):
            try:
                cfg["telegram_user_id"] = int(cfg["telegram_user_id"])
            except Exception:
                cfg["telegram_user_id"] = 0

        if cfg.get("telegram_user_id"):
            cfg["allowed_user_ids"] = [cfg["telegram_user_id"]]
        else:
            cfg["allowed_user_ids"] = []
        previous_version = int(cfg.get("config_version", 0) or 0)
        if previous_version < CONFIG_SCHEMA_VERSION and str(cfg.get("model") or "").strip() in {"", "llama-3.1-8b-instant"}:
            cfg["model"] = DEFAULT_CHAT_MODEL
        if previous_version < CONFIG_SCHEMA_VERSION and float(cfg.get("temperature", DEFAULT_CHAT_TEMPERATURE) or 0) == 0.15:
            cfg["temperature"] = DEFAULT_CHAT_TEMPERATURE
        if previous_version < CONFIG_SCHEMA_VERSION and int(cfg.get("max_tokens", DEFAULT_CHAT_MAX_TOKENS) or 0) == 220:
            cfg["max_tokens"] = DEFAULT_CHAT_MAX_TOKENS

        # Публичный канал обновлений всегда фиксирован на официальный репозиторий.
        cfg["github_repo"] = DEFAULT_GITHUB_REPO
        cfg["update_manifest_url"] = DEFAULT_RELEASE_API_URL

        try:
            cfg["voice_index"] = int(cfg.get("voice_index", 0) or 0)
        except Exception:
            cfg["voice_index"] = 0

        try:
            cfg["voice_rate"] = int(cfg.get("voice_rate", 240) or 240)
        except Exception:
            cfg["voice_rate"] = 240

        try:
            cfg["voice_volume"] = float(cfg.get("voice_volume", 1.0) or 1.0)
        except Exception:
            cfg["voice_volume"] = 1.0

        tts_provider = str(cfg.get("tts_provider", "pyttsx3") or "pyttsx3").strip().lower()
        if tts_provider not in {"pyttsx3", "edge-tts", "elevenlabs"}:
            tts_provider = "pyttsx3"
        cfg["tts_provider"] = tts_provider

        ui_density = str(cfg.get("ui_density", "comfortable") or "comfortable").strip().lower()
        if ui_density not in {"compact", "comfortable"}:
            ui_density = "comfortable"
        cfg["ui_density"] = ui_density

        if not isinstance(cfg.get("focus_mode_enabled"), bool):
            cfg["focus_mode_enabled"] = bool(cfg.get("focus_mode_enabled", False))
        if not isinstance(cfg.get("advanced_tabs_enabled"), bool):
            cfg["advanced_tabs_enabled"] = bool(cfg.get("advanced_tabs_enabled", True))
        if not isinstance(cfg.get("empty_state_hints_enabled"), bool):
            cfg["empty_state_hints_enabled"] = bool(cfg.get("empty_state_hints_enabled", True))
        if not isinstance(cfg.get("helper_guides_enabled"), bool):
            cfg["helper_guides_enabled"] = bool(cfg.get("helper_guides_enabled", True))
        if not isinstance(cfg.get("dpi_adaptation_enabled"), bool):
            cfg["dpi_adaptation_enabled"] = bool(cfg.get("dpi_adaptation_enabled", True))
        try:
            cfg["ui_scale_percent"] = max(85, min(180, int(cfg.get("ui_scale_percent", 100) or 100)))
        except Exception:
            cfg["ui_scale_percent"] = 100

        device_profile_mode = str(cfg.get("device_profile_mode", "auto") or "auto").strip().lower()
        if device_profile_mode not in {"auto", "headset", "usb_mic", "built_in", "webcam", "default"}:
            device_profile_mode = "auto"
        cfg["device_profile_mode"] = device_profile_mode
        if not isinstance(cfg.get("device_profile_overrides"), dict):
            cfg["device_profile_overrides"] = dict(self.default_config["device_profile_overrides"])
        else:
            merged_overrides = dict(self.default_config["device_profile_overrides"])
            for key, value in cfg.get("device_profile_overrides", {}).items():
                kind = str(key or "").strip().lower()
                profile = str(value or "").strip().lower()
                if kind in merged_overrides and profile in {"normal", "boost", "aggressive"}:
                    merged_overrides[kind] = profile
            cfg["device_profile_overrides"] = merged_overrides

        if not isinstance(cfg.get("noise_suppression_enabled"), bool):
            cfg["noise_suppression_enabled"] = bool(cfg.get("noise_suppression_enabled", True))
        if not isinstance(cfg.get("vad_enabled"), bool):
            cfg["vad_enabled"] = bool(cfg.get("vad_enabled", True))
        if not isinstance(cfg.get("hybrid_brain_enabled"), bool):
            cfg["hybrid_brain_enabled"] = bool(cfg.get("hybrid_brain_enabled", True))
        if not isinstance(cfg.get("explain_actions_enabled"), bool):
            cfg["explain_actions_enabled"] = bool(cfg.get("explain_actions_enabled", True))
        if not isinstance(cfg.get("auto_recovery_enabled"), bool):
            cfg["auto_recovery_enabled"] = bool(cfg.get("auto_recovery_enabled", True))
        if not isinstance(cfg.get("snapshot_before_update"), bool):
            cfg["snapshot_before_update"] = bool(cfg.get("snapshot_before_update", True))
        if not isinstance(cfg.get("portable_bundle_enabled"), bool):
            cfg["portable_bundle_enabled"] = bool(cfg.get("portable_bundle_enabled", True))
        if not isinstance(cfg.get("release_lock_enabled"), bool):
            cfg["release_lock_enabled"] = bool(cfg.get("release_lock_enabled", True))
        if not isinstance(cfg.get("ai_simple_labels"), bool):
            cfg["ai_simple_labels"] = bool(cfg.get("ai_simple_labels", True))

        release_channel = str(cfg.get("release_channel", "stable") or "stable").strip().lower()
        if release_channel not in {"stable", "beta"}:
            release_channel = "stable"
        cfg["release_channel"] = release_channel

        fullscreen_layout = str(cfg.get("fullscreen_layout", "mission_control") or "mission_control").strip().lower()
        if fullscreen_layout not in {"mission_control"}:
            fullscreen_layout = "mission_control"
        cfg["fullscreen_layout"] = fullscreen_layout

        if not isinstance(cfg.get("readiness_last_report"), list):
            cfg["readiness_last_report"] = []
        if not isinstance(cfg.get("readiness_last_summary"), str):
            cfg["readiness_last_summary"] = ""
        if not isinstance(cfg.get("plugin_pack_last_path"), str):
            cfg["plugin_pack_last_path"] = ""
        if not isinstance(cfg.get("current_scenario"), str):
            cfg["current_scenario"] = ""

        memory_items = []
        for item in (cfg.get("user_memory_items") or []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "") or "").strip()[:40]
            title = str(item.get("title", "") or "").strip()
            value = str(item.get("value", "") or "").strip()
            if not title and not value:
                continue
            kind = str(item.get("kind", "note") or "note").strip().lower() or "note"
            scope = str(item.get("scope", "personal") or "personal").strip().lower() or "personal"
            if scope not in {"personal", "temporary", "pinned"}:
                scope = "personal"
            tags = []
            for raw_tag in (item.get("tags") or []):
                tag = str(raw_tag or "").strip()
                if tag and tag.lower() not in {x.lower() for x in tags}:
                    tags.append(tag[:24])
            memory_items.append({
                "id": item_id,
                "title": title[:80],
                "value": value[:400],
                "kind": kind,
                "scope": scope,
                "pinned": bool(item.get("pinned", False) or scope == "pinned"),
                "tags": tags[:8],
                "created_at": str(item.get("created_at", "") or "").strip()[:32],
                "last_used_at": str(item.get("last_used_at", "") or "").strip()[:32],
            })
        cfg["user_memory_items"] = memory_items[-120:]

        scenarios = []
        for item in (cfg.get("scenarios") or []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "") or "").strip()[:40]
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            trigger_phrases = []
            for raw_phrase in (item.get("trigger_phrases") or []):
                phrase = str(raw_phrase or "").strip()
                if phrase and phrase.lower() not in {x.lower() for x in trigger_phrases}:
                    trigger_phrases.append(phrase[:80])
            scenarios.append({
                "id": item_id,
                "name": name[:80],
                "summary": str(item.get("summary", "") or "").strip()[:200],
                "changes": item.get("changes", {}) if isinstance(item.get("changes", {}), dict) else {},
                "trigger_phrases": trigger_phrases[:8],
                "enabled": bool(item.get("enabled", True)),
            })
        cfg["scenarios"] = scenarios[-32:]

        if not isinstance(cfg.get("edge_tts_voice"), str):
            cfg["edge_tts_voice"] = "ru-RU-DmitryNeural"
        else:
            cfg["edge_tts_voice"] = str(cfg.get("edge_tts_voice") or "ru-RU-DmitryNeural").strip() or "ru-RU-DmitryNeural"

        if not isinstance(cfg.get("elevenlabs_api_key"), str):
            cfg["elevenlabs_api_key"] = ""
        else:
            cfg["elevenlabs_api_key"] = str(cfg.get("elevenlabs_api_key") or "").strip()

        if not isinstance(cfg.get("elevenlabs_voice_id"), str):
            cfg["elevenlabs_voice_id"] = ""
        else:
            cfg["elevenlabs_voice_id"] = str(cfg.get("elevenlabs_voice_id") or "").strip()

        if not isinstance(cfg.get("elevenlabs_model_id"), str):
            cfg["elevenlabs_model_id"] = "eleven_flash_v2_5"
        else:
            model_id = str(cfg.get("elevenlabs_model_id") or "").strip()
            cfg["elevenlabs_model_id"] = model_id or "eleven_flash_v2_5"

        if not isinstance(cfg.get("model"), str):
            cfg["model"] = DEFAULT_CHAT_MODEL
        else:
            cfg["model"] = str(cfg.get("model") or "").strip() or DEFAULT_CHAT_MODEL

        if cfg.get("mic_device_index") in ("", None, "None"):
            cfg["mic_device_index"] = None
        else:
            try:
                cfg["mic_device_index"] = int(cfg["mic_device_index"])
            except Exception:
                cfg["mic_device_index"] = None

        try:
            cfg["temperature"] = float(cfg.get("temperature", DEFAULT_CHAT_TEMPERATURE))
        except Exception:
            cfg["temperature"] = DEFAULT_CHAT_TEMPERATURE
        cfg["temperature"] = max(0.0, min(1.0, cfg["temperature"]))

        try:
            cfg["max_tokens"] = int(cfg.get("max_tokens", DEFAULT_CHAT_MAX_TOKENS))
        except Exception:
            cfg["max_tokens"] = DEFAULT_CHAT_MAX_TOKENS
        cfg["max_tokens"] = max(80, min(1024, cfg["max_tokens"]))

        if not isinstance(cfg.get("output_device_name"), str):
            cfg["output_device_name"] = str(cfg.get("output_device_name") or "")
        if cfg.get("output_device_index") in ("", None, "None"):
            cfg["output_device_index"] = None
        else:
            try:
                cfg["output_device_index"] = int(cfg["output_device_index"])
            except Exception:
                cfg["output_device_index"] = None

        if not isinstance(cfg.get("auto_update"), bool):
            cfg["auto_update"] = bool(cfg.get("auto_update", True))

        # В публичном релизе всегда проверяем обновления на старте.
        cfg["update_check_on_start"] = True

        if not isinstance(cfg.get("first_run_done"), bool):
            cfg["first_run_done"] = False

        close_behavior = str(cfg.get("close_behavior", "exit") or "exit").strip().lower()
        if close_behavior not in {"exit", "tray"}:
            close_behavior = "exit"
        cfg["close_behavior"] = close_behavior

        theme_mode = str(cfg.get("theme_mode", "dark") or "dark").strip().lower()
        if theme_mode not in {"dark", "light"}:
            if "\u0441\u0432\u0435\u0442" in theme_mode or "light" in theme_mode:
                theme_mode = "light"
            elif "\u0442\u0435\u043c" in theme_mode or "dark" in theme_mode:
                theme_mode = "dark"
            else:
                theme_mode = "dark"
        cfg["theme_mode"] = theme_mode

        listening_profile = str(cfg.get("listening_profile", "normal") or "normal").strip().lower()
        if listening_profile not in {"normal", "boost", "aggressive"}:
            if listening_profile.startswith("1") or "\u0441\u0435\u0439\u0447\u0430\u0441" in listening_profile or "normal" in listening_profile:
                listening_profile = "normal"
            elif listening_profile.startswith("3") or "\u0435\u0449" in listening_profile or "aggressive" in listening_profile:
                listening_profile = "aggressive"
            elif listening_profile.startswith("2") or "\u0443\u0441\u0438\u043b\u0435\u043d" in listening_profile or "boost" in listening_profile:
                listening_profile = "boost"
            else:
                listening_profile = "normal"
        cfg["listening_profile"] = listening_profile

        if not isinstance(cfg.get("wake_word_boost"), bool):
            cfg["wake_word_boost"] = bool(cfg.get("wake_word_boost", True))

        if not isinstance(cfg.get("wake_debug_enabled"), bool):
            cfg["wake_debug_enabled"] = bool(cfg.get("wake_debug_enabled", True))

        if not isinstance(cfg.get("microphone_meter_enabled"), bool):
            cfg["microphone_meter_enabled"] = bool(cfg.get("microphone_meter_enabled", True))

        if not isinstance(cfg.get("background_self_check"), bool):
            cfg["background_self_check"] = bool(cfg.get("background_self_check", True))

        try:
            interval = int(cfg.get("self_check_interval_min", 10) or 10)
        except Exception:
            interval = 10
        cfg["self_check_interval_min"] = max(3, min(120, interval))

        if not isinstance(cfg.get("active_listening_enabled"), bool):
            cfg["active_listening_enabled"] = bool(cfg.get("active_listening_enabled", True))

        if not isinstance(cfg.get("safe_mode_enabled"), bool):
            cfg["safe_mode_enabled"] = bool(cfg.get("safe_mode_enabled", False))

        proxy_url = str(cfg.get("proxy_url", "") or "").strip()
        cfg["proxy_url"] = proxy_url

        avatar_path = str(cfg.get("user_avatar_path", "") or "").strip()
        cfg["user_avatar_path"] = avatar_path

        if not isinstance(cfg.get("free_chat_mode"), bool):
            cfg["free_chat_mode"] = bool(cfg.get("free_chat_mode", False))

        cfg["last_update_notice_version"] = str(cfg.get("last_update_notice_version", "") or "").strip()

        hosts = cfg.get("update_trusted_hosts", [])
        if not isinstance(hosts, list):
            hosts = []
        normalized_hosts = []
        for h in hosts:
            hs = str(h or "").strip().lower()
            if hs and hs not in normalized_hosts:
                normalized_hosts.append(hs)
        if not normalized_hosts:
            normalized_hosts = list(self.default_config["update_trusted_hosts"])
        else:
            for required in self.default_config["update_trusted_hosts"]:
                req = str(required or "").strip().lower()
                if req and req not in normalized_hosts:
                    normalized_hosts.append(req)
        cfg["update_trusted_hosts"] = normalized_hosts

        def _normalize_dynamic_list(items):
            if not isinstance(items, list):
                return []
            normalized = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key", "")).strip().lower()
                name = str(item.get("name", "")).strip()
                launch = str(item.get("launch", "")).strip()
                if not key or not name or not launch:
                    continue
                aliases = item.get("aliases", [])
                if not isinstance(aliases, list):
                    aliases = []
                aliases = [str(a).strip().lower() for a in aliases if str(a).strip()]
                close_exes = item.get("close_exes", [])
                if not isinstance(close_exes, list):
                    close_exes = []
                close_exes = [str(e).strip() for e in close_exes if str(e).strip()]
                normalized.append({
                    "key": key,
                    "name": name,
                    "launch": launch,
                    "aliases": aliases,
                    "close_exes": close_exes,
                    "source": str(item.get("source", "custom") or "custom").strip().lower(),
                })
            return normalized

        cfg["custom_apps"] = _normalize_dynamic_list(cfg.get("custom_apps", []))
        cfg["launcher_games"] = _normalize_dynamic_list(cfg.get("launcher_games", []))

        learned = cfg.get("learned_commands", [])
        if not isinstance(learned, list):
            learned = []
        learned_normalized = []
        seen = set()
        for item in learned:
            if not isinstance(item, dict):
                continue
            pattern = _normalize_pattern_text(item.get("pattern", ""))
            action = str(item.get("action", "")).strip().lower()
            arg = item.get("arg", "")
            if not pattern or not action or _is_learned_pattern_generic(pattern):
                continue
            dedupe_arg = json.dumps(arg, ensure_ascii=False, sort_keys=True) if isinstance(arg, (dict, list)) else str(arg)
            dedupe_key = (pattern, action, dedupe_arg)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            learned_normalized.append({
                "pattern": pattern,
                "action": action,
                "arg": arg,
            })
        cfg["learned_commands"] = learned_normalized[-120:]

        if not isinstance(cfg.get("self_learning_enabled"), bool):
            cfg["self_learning_enabled"] = bool(cfg.get("self_learning_enabled", True))

        cfg["config_version"] = CONFIG_SCHEMA_VERSION

    def save(self):
        try:
            with self._lock:
                snapshot = dict(self._config)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get(self, key, default=None):
        with self._lock:
            return self._config.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._config[key] = value
            self._validate()
        self.save()

    def set_many(self, updates: Dict[str, Any]):
        """Atomically applies multiple config updates and writes once."""
        if not isinstance(updates, dict):
            return
        with self._lock:
            self._config.update(updates)
            self._validate()
        self.save()

    def get_user_name(self): return self.get("user_name", "")
    def set_user_name(self, name): self.set("user_name", name or "")
    def get_user_login(self): return self.get("user_login", "")
    def set_user_login(self, login): self.set("user_login", login or "")
    def get_telegram_token(self): return self.get("telegram_token", "")
    def set_telegram_token(self, token): self.set("telegram_token", token or "")
    def get_telegram_user_id(self): return self.get("telegram_user_id", 0)
    def set_telegram_user_id(self, user_id):
        try:
            user_id = int(user_id)
        except Exception:
            user_id = 0
        self.set("telegram_user_id", user_id)
        self.set("allowed_user_ids", [user_id] if user_id else [])
    def get_allowed_user_ids(self): return self.get("allowed_user_ids", [])
    def set_allowed_user_ids(self, ids):
        try:
            ids = [int(x) for x in (ids or []) if str(x).strip()]
        except Exception:
            ids = []
        self.set("allowed_user_ids", ids[:1])
        self.set("telegram_user_id", ids[0] if ids else 0)
    def get_single_user_mode(self): return bool(self.get("single_user_mode", True))
    def set_single_user_mode(self, enabled): self.set("single_user_mode", bool(enabled))
    def get_github_repo(self): return self.get("github_repo", "")
    def set_github_repo(self, repo): self.set("github_repo", repo or "")
    def get_update_manifest_url(self): return self.get("update_manifest_url", "")
    def set_update_manifest_url(self, url): self.set("update_manifest_url", url or "")
    def get_update_download_url(self): return self.get("update_download_url", "")
    def set_update_download_url(self, url): self.set("update_download_url", url or "")
    def get_auto_update(self): return bool(self.get("auto_update", True))
    def set_auto_update(self, enabled): self.set("auto_update", bool(enabled))
    def get_update_check_on_start(self): return bool(self.get("update_check_on_start", True))
    def set_update_check_on_start(self, enabled): self.set("update_check_on_start", bool(enabled))
    def get_mic_device_index(self): return self.get("mic_device_index", None)
    def set_mic_device_index(self, idx):
        if idx in ("", None, "None"):
            idx = None
        try:
            idx = None if idx is None else int(idx)
        except Exception:
            idx = None
        self.set("mic_device_index", idx)
    def get_mic_device_name(self): return self.get("mic_device_name", "")
    def set_mic_device_name(self, name): self.set("mic_device_name", name or "")
    def get_output_device_index(self): return self.get("output_device_index", None)
    def set_output_device_index(self, idx):
        if idx in ("", None, "None"):
            idx = None
        try:
            idx = None if idx is None else int(idx)
        except Exception:
            idx = None
        self.set("output_device_index", idx)
    def get_output_device_name(self): return self.get("output_device_name", "")
    def set_output_device_name(self, name): self.set("output_device_name", name or "")
    def get_api_key(self): return self.get("api_key", "")
    def set_api_key(self, key): self.set("api_key", key or "")
    def get_model(self): return self.get("model", DEFAULT_CHAT_MODEL)
    def set_model(self, model): self.set("model", model or DEFAULT_CHAT_MODEL)
    def get_temperature(self): return self.get("temperature", DEFAULT_CHAT_TEMPERATURE)
    def set_temperature(self, temperature): self.set("temperature", float(temperature))
    def get_max_tokens(self): return self.get("max_tokens", DEFAULT_CHAT_MAX_TOKENS)
    def set_max_tokens(self, max_tokens): self.set("max_tokens", int(max_tokens))
    def get_autostart(self): return self.get("autostart", False)
    def set_autostart(self, enabled): self.set("autostart", enabled)
    def get_voice_index(self): return self.get("voice_index", 0)
    def set_voice_index(self, idx): self.set("voice_index", idx)
    def get_voice_rate(self): return self.get("voice_rate", 240)
    def set_voice_rate(self, rate): self.set("voice_rate", rate)
    def get_voice_volume(self): return self.get("voice_volume", 1.0)
    def set_voice_volume(self, volume): self.set("voice_volume", volume)
    def get_tts_provider(self): return self.get("tts_provider", "pyttsx3")
    def set_tts_provider(self, provider): self.set("tts_provider", str(provider or "pyttsx3").strip().lower())
    def get_edge_tts_voice(self): return self.get("edge_tts_voice", "ru-RU-DmitryNeural")
    def set_edge_tts_voice(self, voice): self.set("edge_tts_voice", str(voice or "ru-RU-DmitryNeural").strip() or "ru-RU-DmitryNeural")
    def get_elevenlabs_api_key(self): return self.get("elevenlabs_api_key", "")
    def set_elevenlabs_api_key(self, key): self.set("elevenlabs_api_key", str(key or "").strip())
    def get_elevenlabs_voice_id(self): return self.get("elevenlabs_voice_id", "")
    def set_elevenlabs_voice_id(self, voice_id): self.set("elevenlabs_voice_id", str(voice_id or "").strip())
    def get_elevenlabs_model_id(self): return self.get("elevenlabs_model_id", "eleven_flash_v2_5")
    def set_elevenlabs_model_id(self, model_id): self.set("elevenlabs_model_id", str(model_id or "").strip() or "eleven_flash_v2_5")
    def get_personality(self): return self.get("personality", "default")
    def set_personality(self, name): self.set("personality", name)
    def get_window_geometry(self): return self.get("window_geometry", "640x860+200+100")
    def set_window_geometry(self, geom): self.set("window_geometry", geom)
    def get_available_version(self): return self.get("available_version", "")
    def set_available_version(self, ver): self.set("available_version", ver or "")
    def get_theme_mode(self): return self.get("theme_mode", "dark")
    def set_theme_mode(self, mode): self.set("theme_mode", str(mode or "dark").strip().lower())
    def get_ui_density(self): return self.get("ui_density", "comfortable")
    def set_ui_density(self, mode): self.set("ui_density", str(mode or "comfortable").strip().lower())
    def get_focus_mode_enabled(self): return bool(self.get("focus_mode_enabled", False))
    def set_focus_mode_enabled(self, enabled): self.set("focus_mode_enabled", bool(enabled))
    def get_advanced_tabs_enabled(self): return bool(self.get("advanced_tabs_enabled", True))
    def set_advanced_tabs_enabled(self, enabled): self.set("advanced_tabs_enabled", bool(enabled))
    def get_empty_state_hints_enabled(self): return bool(self.get("empty_state_hints_enabled", True))
    def set_empty_state_hints_enabled(self, enabled): self.set("empty_state_hints_enabled", bool(enabled))
    def get_helper_guides_enabled(self): return bool(self.get("helper_guides_enabled", True))
    def set_helper_guides_enabled(self, enabled): self.set("helper_guides_enabled", bool(enabled))
    def get_close_behavior(self): return self.get("close_behavior", "exit")
    def set_close_behavior(self, value): self.set("close_behavior", str(value or "exit").strip().lower())
    def get_dpi_adaptation_enabled(self): return bool(self.get("dpi_adaptation_enabled", True))
    def set_dpi_adaptation_enabled(self, enabled): self.set("dpi_adaptation_enabled", bool(enabled))
    def get_ui_scale_percent(self): return int(self.get("ui_scale_percent", 100))
    def set_ui_scale_percent(self, value): self.set("ui_scale_percent", int(value))
    def get_listening_profile(self): return self.get("listening_profile", "normal")
    def set_listening_profile(self, profile):
        raw = str(profile or "normal").strip().lower()
        if raw not in {"normal", "boost", "aggressive"}:
            if raw.startswith("3") or "ещ" in raw or "aggressive" in raw:
                raw = "aggressive"
            elif raw.startswith("2") or "усилен" in raw or "boost" in raw:
                raw = "boost"
            else:
                raw = "normal"
        self.set("listening_profile", raw)
    def get_wake_word_boost_enabled(self): return bool(self.get("wake_word_boost", True))
    def set_wake_word_boost_enabled(self, enabled): self.set("wake_word_boost", bool(enabled))
    def get_wake_debug_enabled(self): return bool(self.get("wake_debug_enabled", True))
    def set_wake_debug_enabled(self, enabled): self.set("wake_debug_enabled", bool(enabled))
    def get_microphone_meter_enabled(self): return bool(self.get("microphone_meter_enabled", True))
    def set_microphone_meter_enabled(self, enabled): self.set("microphone_meter_enabled", bool(enabled))
    def get_active_listening_enabled(self): return bool(self.get("active_listening_enabled", True))
    def set_active_listening_enabled(self, enabled): self.set("active_listening_enabled", bool(enabled))
    def get_safe_mode_enabled(self): return bool(self.get("safe_mode_enabled", False))
    def set_safe_mode_enabled(self, enabled): self.set("safe_mode_enabled", bool(enabled))
    def get_noise_suppression_enabled(self): return bool(self.get("noise_suppression_enabled", True))
    def set_noise_suppression_enabled(self, enabled): self.set("noise_suppression_enabled", bool(enabled))
    def get_vad_enabled(self): return bool(self.get("vad_enabled", True))
    def set_vad_enabled(self, enabled): self.set("vad_enabled", bool(enabled))
    def get_hybrid_brain_enabled(self): return bool(self.get("hybrid_brain_enabled", True))
    def set_hybrid_brain_enabled(self, enabled): self.set("hybrid_brain_enabled", bool(enabled))
    def get_explain_actions_enabled(self): return bool(self.get("explain_actions_enabled", True))
    def set_explain_actions_enabled(self, enabled): self.set("explain_actions_enabled", bool(enabled))
    def get_auto_recovery_enabled(self): return bool(self.get("auto_recovery_enabled", True))
    def set_auto_recovery_enabled(self, enabled): self.set("auto_recovery_enabled", bool(enabled))
    def get_background_self_check(self): return bool(self.get("background_self_check", True))
    def set_background_self_check(self, enabled): self.set("background_self_check", bool(enabled))
    def get_self_check_interval_min(self): return int(self.get("self_check_interval_min", 10))
    def set_self_check_interval_min(self, minutes): self.set("self_check_interval_min", int(minutes))
    def get_proxy_url(self): return self.get("proxy_url", "")
    def set_proxy_url(self, value): self.set("proxy_url", str(value or "").strip())
    def get_user_avatar_path(self): return self.get("user_avatar_path", "")
    def set_user_avatar_path(self, value): self.set("user_avatar_path", str(value or "").strip())
    def get_free_chat_mode(self): return bool(self.get("free_chat_mode", False))
    def set_free_chat_mode(self, enabled): self.set("free_chat_mode", bool(enabled))
    def get_last_update_notice_version(self): return self.get("last_update_notice_version", "")
    def set_last_update_notice_version(self, value): self.set("last_update_notice_version", str(value or "").strip())
    def get_release_channel(self): return self.get("release_channel", "stable")
    def set_release_channel(self, value): self.set("release_channel", str(value or "stable").strip().lower())
    def get_snapshot_before_update(self): return bool(self.get("snapshot_before_update", True))
    def set_snapshot_before_update(self, enabled): self.set("snapshot_before_update", bool(enabled))
    def get_portable_bundle_enabled(self): return bool(self.get("portable_bundle_enabled", True))
    def set_portable_bundle_enabled(self, enabled): self.set("portable_bundle_enabled", bool(enabled))
    def get_release_lock_enabled(self): return bool(self.get("release_lock_enabled", True))
    def set_release_lock_enabled(self, enabled): self.set("release_lock_enabled", bool(enabled))
    def get_ai_simple_labels(self): return bool(self.get("ai_simple_labels", True))
    def set_ai_simple_labels(self, enabled): self.set("ai_simple_labels", bool(enabled))
    def get_user_memory_items(self): return self.get("user_memory_items", [])
    def set_user_memory_items(self, items): self.set("user_memory_items", items if isinstance(items, list) else [])
    def get_scenarios(self): return self.get("scenarios", [])
    def set_scenarios(self, items): self.set("scenarios", items if isinstance(items, list) else [])
    def get_current_scenario(self): return self.get("current_scenario", "")
    def set_current_scenario(self, value): self.set("current_scenario", str(value or "").strip())
    def get_last_control_center_section(self): return self.get("last_control_center_section", "main")
    def set_last_control_center_section(self, value): self.set("last_control_center_section", str(value or "main").strip().lower())
    def get_readiness_last_report(self): return self.get("readiness_last_report", [])
    def set_readiness_last_report(self, items): self.set("readiness_last_report", items if isinstance(items, list) else [])
    def get_readiness_last_summary(self): return self.get("readiness_last_summary", "")
    def set_readiness_last_summary(self, text): self.set("readiness_last_summary", str(text or "").strip())
    def get_human_log_entries(self): return self.get("human_log_entries", [])
    def set_human_log_entries(self, items): self.set("human_log_entries", items if isinstance(items, list) else [])
    def get_action_history_entries(self): return self.get("action_history_entries", [])
    def set_action_history_entries(self, items): self.set("action_history_entries", items if isinstance(items, list) else [])
    def get_device_profile_mode(self): return self.get("device_profile_mode", "auto")
    def set_device_profile_mode(self, value): self.set("device_profile_mode", str(value or "auto").strip().lower())
    def get_device_profile_overrides(self): return self.get("device_profile_overrides", dict(self.default_config["device_profile_overrides"]))
    def set_device_profile_overrides(self, value): self.set("device_profile_overrides", value if isinstance(value, dict) else dict(self.default_config["device_profile_overrides"]))
    def get_plugin_pack_last_path(self): return self.get("plugin_pack_last_path", "")
    def set_plugin_pack_last_path(self, value): self.set("plugin_pack_last_path", str(value or "").strip())
    def get_fullscreen_layout(self): return self.get("fullscreen_layout", "mission_control")
    def set_fullscreen_layout(self, value): self.set("fullscreen_layout", str(value or "mission_control").strip().lower())
    def get_update_trusted_hosts(self): return self.get("update_trusted_hosts", list(self.default_config["update_trusted_hosts"]))
    def set_update_trusted_hosts(self, hosts): self.set("update_trusted_hosts", hosts if isinstance(hosts, list) else [])
    def get_custom_apps(self): return self.get("custom_apps", [])
    def set_custom_apps(self, apps): self.set("custom_apps", apps if isinstance(apps, list) else [])
    def get_launcher_games(self): return self.get("launcher_games", [])
    def set_launcher_games(self, games): self.set("launcher_games", games if isinstance(games, list) else [])
    def get_learned_commands(self): return self.get("learned_commands", [])
    def set_learned_commands(self, entries): self.set("learned_commands", entries if isinstance(entries, list) else [])
    def get_self_learning_enabled(self): return bool(self.get("self_learning_enabled", True))
    def set_self_learning_enabled(self, enabled): self.set("self_learning_enabled", bool(enabled))
    def is_first_run(self): return not self.get("first_run_done", False)
    def set_first_run_done(self): self.set("first_run_done", True)

CONFIG_MGR = ConfigManager()
CONFIG = CONFIG_MGR._config
# =========================================================
# PROMPT MANAGER
# =========================================================
class PromptManager:
    def __init__(self):
        self.prompts_dir = get_prompts_dir()
        self._ensure_default_prompts()
        self.current_personality = CONFIG_MGR.get_personality()

    def _ensure_default_prompts(self):
        default_prompt = {
            "system": (
                "Ты мозг голосового помощника Джарвис. Понимай естественную русскую речь. "
                "Всегда отвечай кратко и по делу, но с эмпатией. Если пользователь жалуется, грустит или благодарит, реагируй соответствующе. "
                "Верни ТОЛЬКО JSON без markdown. "
                "Формат: {\"type\":\"commands|chat\",\"items\":[{\"type\":\"command|chat\",\"action\":\"...\",\"arg\":\"...\",\"reply\":\"...\"}]}. "
                "Если команда одна — items массив из одного объекта. Если действий несколько — несколько объектов в items. "
                "Если это обычный вопрос — type=chat, один item с type=chat, action=chat, reply=короткий ответ на русском. "
                "Допустимые action: music,youtube,ozon,wildberries,browser,cs2,fortnite,dbd,deadlock,steam,settings,twitch,roblox,discord,notepad,calc,taskmgr,explorer,downloads,documents,desktop,restart_explorer,restart_pc,search,time,date,weather,media_pause,media_play,media_next,media_prev,volume_up,volume_down,shutdown,lock,close_app,open_dynamic_app,reminder,history,repeat,telegram,timur_son. "
                "Для search клади запрос в arg. Для close_app клади ключ программы в arg (music, discord, cs2 и т.д.). Для reminder arg должен быть кортежем (секунды, текст) в виде строки \"30|проветрить\". "
                "Если речь о системных/локальных командах, отдавай command."
            )
        }
        default_path = os.path.join(self.prompts_dir, "default.json")
        if not os.path.exists(default_path):
            try:
                with open(default_path, "w", encoding="utf-8") as f:
                    json.dump(default_prompt, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Could not create default prompt: {e}")

    def get_system_prompt(self):
        prompt_file = os.path.join(self.prompts_dir, f"{self.current_personality}.json")
        if not os.path.exists(prompt_file):
            prompt_file = os.path.join(self.prompts_dir, "default.json")
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("system", "")
        except Exception as e:
            logger.error(f"Error loading prompt: {e}")
            return ""

    def set_personality(self, name):
        self.current_personality = name
        CONFIG_MGR.set_personality(name)


def _patched_ensure_default_prompts(self):
    default_prompt = {"system": DEFAULT_SYSTEM_PROMPT}
    default_path = os.path.join(self.prompts_dir, "default.json")
    should_write = not os.path.exists(default_path)
    if not should_write:
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            should_write = _prompt_needs_repair(existing.get("system", "")) if isinstance(existing, dict) else True
        except Exception:
            should_write = True
    if should_write:
        try:
            with open(default_path, "w", encoding="utf-8") as f:
                json.dump(default_prompt, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Could not create default prompt: {e}")


def _patched_get_system_prompt(self):
    prompt_file = os.path.join(self.prompts_dir, f"{self.current_personality}.json")
    if not os.path.exists(prompt_file):
        prompt_file = os.path.join(self.prompts_dir, "default.json")
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        prompt = data.get("system", "") if isinstance(data, dict) else ""
        if _prompt_needs_repair(prompt):
            self._ensure_default_prompts()
            return DEFAULT_SYSTEM_PROMPT
        return prompt
    except Exception as e:
        logger.error(f"Error loading prompt: {e}")
        return DEFAULT_SYSTEM_PROMPT


PromptManager._ensure_default_prompts = _patched_ensure_default_prompts
PromptManager.get_system_prompt = _patched_get_system_prompt

PROMPT_MGR = PromptManager()

# =========================================================
# DATABASE (с буферизацией)
# =========================================================
class Database:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.db_path = get_db_path()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    command TEXT,
                    result TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON commands(timestamp)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    role TEXT,
                    content TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_role ON context(role)")
        self.buffer = []
        self.context_buffer = []
        self.buffer_lock = threading.Lock()
        self._start_flush_thread()

    def _start_flush_thread(self):
        def flush_loop():
            while True:
                time.sleep(5)
                self._flush()
        threading.Thread(target=flush_loop, daemon=True).start()

    def _flush(self):
        with self.buffer_lock:
            if self.buffer:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.executemany("INSERT INTO commands (command, result) VALUES (?, ?)", self.buffer)
                    self.buffer.clear()
                except sqlite3.Error as e:
                    logger.error(f"DB flush error: {e}")
            if self.context_buffer:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.executemany("INSERT INTO context (role, content) VALUES (?, ?)", self.context_buffer)
                    self.context_buffer.clear()
                except sqlite3.Error as e:
                    logger.error(f"Context flush error: {e}")

    def save_command(self, cmd: str, result: str = None):
        with self.buffer_lock:
            self.buffer.append((cmd, result))

    def get_recent_history(self, limit: int = 8):
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT timestamp, command, result FROM commands ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            rows.reverse()
            return rows
        except sqlite3.Error as e:
            logger.error(f"DB history error: {e}")
            return []

    def history_text(self, limit: int = 8):
        rows = self.get_recent_history(limit)
        if not rows:
            return "История пуста."
        return "\n".join(f"{ts}: {cmd} -> {result or ''}" for ts, cmd, result in rows)

    def save_context(self, role: str, content: str):
        with self.buffer_lock:
            self.context_buffer.append((role, content))

    def load_context(self, limit: int = 7) -> List[Dict[str, str]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT role, content FROM context ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            rows.reverse()
            return [{"role": r[0], "content": r[1]} for r in rows]
        except sqlite3.Error as e:
            logger.error(f"Context load error: {e}")
            return []

    def clear_context(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM context")
        except sqlite3.Error as e:
            logger.error(f"Context clear error: {e}")

    def shutdown(self):
        self._flush()

db = Database()


__all__ = [
    "CONFIG",
    "CONFIG_MGR",
    "ConfigManager",
    "Database",
    "LOCAL_APPDATA",
    "PROMPT_MGR",
    "PromptManager",
    "ROAMING_APPDATA",
    "USER_PROFILE",
    "_is_learned_pattern_generic",
    "_normalize_pattern_text",
    "db",
    "get_config_path",
    "get_db_path",
    "get_prompts_dir",
]

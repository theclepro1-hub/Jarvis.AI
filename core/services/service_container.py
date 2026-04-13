from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from core.services.chat_history_store import ChatHistoryStore
from core.settings.settings_service import SettingsService
from core.settings.startup_manager import StartupManager
from core.settings.settings_store import SettingsStore
from core.routing.text_rules import (
    looks_like_broken_command,
    looks_like_system_command,
    normalize_text,
)

if TYPE_CHECKING:
    from core.actions.action_registry import ActionRegistry
    from core.ai.ai_service import AIService
    from core.ai.local_runtime_service import LocalRuntimeService
    from core.pc_control.service import PcControlService
    from core.registration.registration_service import RegistrationService
    from core.reminders.reminder_service import ReminderService
    from core.routing.batch_router import BatchRouter
    from core.routing.command_router import CommandRouter
    from core.telegram.telegram_service import HttpTelegramTransport, TelegramService
    from core.updates.update_service import UpdateService
    from core.voice.voice_service import VoiceService
    from core.voice.wake_service import WakeService

AIService = None
ActionRegistry = None
BatchRouter = None
CommandRouter = None
HttpTelegramTransport = None
LocalRuntimeService = None
PcControlService = None
RegistrationService = None
ReminderService = None
TelegramService = None
UpdateService = None
VoiceService = None
WakeService = None


def _boot_log(message: str) -> None:
    if os.environ.get("JARVIS_UNITY_BOOT_LOG") != "1":
        return
    try:
        start_ns = int(os.environ.get("JARVIS_UNITY_BOOT_T0_NS", "0") or "0")
        elapsed_ms = 0.0
        if start_ns > 0:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        log_path = Path.home() / "AppData" / "Local" / "JarvisAi_Unity" / "bootstrap.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{elapsed_ms:9.2f} ms] {message}\n")
    except Exception:
        pass


class ServiceContainer:
    def __init__(self) -> None:
        _boot_log("services:init:begin")
        self.settings_store = SettingsStore()
        _boot_log("services:init:settings-store")
        self.chat_history = ChatHistoryStore()
        _boot_log("services:init:chat-history")
        self.settings = SettingsService(self.settings_store)
        _boot_log("services:init:settings-service")
        self.startup = StartupManager()
        _boot_log("services:init:startup-manager")
        startup_enabled = self.startup.is_enabled()
        if bool(self.settings.get("startup_enabled", startup_enabled)) != startup_enabled:
            self.settings.set("startup_enabled", startup_enabled)
            _boot_log("services:init:startup-state:updated")
        else:
            _boot_log("services:init:startup-state:unchanged")
        registration_service_cls = RegistrationService
        if registration_service_cls is None:
            from core.registration.registration_service import RegistrationService as _RegistrationService

            globals()["RegistrationService"] = _RegistrationService
            registration_service_cls = _RegistrationService

        self.registration = registration_service_cls(self.settings)
        _boot_log("services:init:registration")
        self._lazy_lock = threading.RLock()
        self._telegram_history_lock = threading.RLock()
        self._telegram_history_by_chat_id: dict[str, deque[dict[str, str]]] = {}
        self._telegram_history_limit = 12
        self._reminders = None
        self._telegram = None
        self._voice = None
        self._wake = None
        self._updates = None
        self._ai = None
        self._local_runtime = None
        self._actions = None
        self._batch_router = None
        self._pc_control = None
        self._command_router = None
        _boot_log("services:init:lazy-heavy-services")

    TELEGRAM_CONTEXTUAL_REPLY_WORDS = {
        "да",
        "нет",
        "ок",
        "ладно",
        "угу",
        "ага",
        "понятно",
        "ясно",
        "спасибо",
        "сорри",
        "извини",
    }

    def _ensure_lazy_lock(self):
        if not hasattr(self, "_lazy_lock") or self._lazy_lock is None:
            self._lazy_lock = threading.RLock()
        return self._lazy_lock

    def handle_external_command(
        self,
        text: str,
        telegram_chat_id: str = "",
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        route = self.command_router.handle(text, source="telegram", telegram_chat_id=telegram_chat_id)
        clean = " ".join(route.commands).strip() if route.commands else text
        history = self._telegram_history(telegram_chat_id)
        if route.kind != "ai":
            if self._should_use_telegram_contextual_ai(clean, history):
                return self._run_telegram_ai(clean, history, status_callback=status_callback, telegram_chat_id=telegram_chat_id)
            if route.assistant_lines:
                return "\n".join(route.assistant_lines)
            if not route.commands:
                return ""
            return self._telegram_route_reply(route)
        return self._run_telegram_ai(clean, history, status_callback=status_callback, telegram_chat_id=telegram_chat_id)

    def classify_external_command(self, text: str, telegram_chat_id: str = "") -> str:
        try:
            route = self.command_router.preview(text, source="telegram", telegram_chat_id=telegram_chat_id)
        except Exception:
            return "fast"
        if str(getattr(route, "kind", "")).strip().casefold() == "ai":
            return "ai"
        if self._should_use_telegram_contextual_ai(text, self._telegram_history(telegram_chat_id)):
            return "ai"
        return "fast"

    @property
    def ai(self) -> AIService:
        if self._ai is None:
            with self._ensure_lazy_lock():
                if self._ai is None:
                    _boot_log("services:lazy:ai")
                    ai_service_cls = AIService
                    if ai_service_cls is None:
                        from core.ai.ai_service import AIService as _AIService

                        globals()["AIService"] = _AIService
                        ai_service_cls = _AIService
                    self._ai = ai_service_cls(self.settings)
        return self._ai

    @property
    def local_runtime(self) -> LocalRuntimeService:
        if self._local_runtime is None:
            with self._ensure_lazy_lock():
                if self._local_runtime is None:
                    _boot_log("services:lazy:local-runtime")
                    local_runtime_cls = LocalRuntimeService
                    if local_runtime_cls is None:
                        from core.ai.local_runtime_service import LocalRuntimeService as _LocalRuntimeService

                        globals()["LocalRuntimeService"] = _LocalRuntimeService
                        local_runtime_cls = _LocalRuntimeService
                    self._local_runtime = local_runtime_cls(self.settings)
        return self._local_runtime

    @property
    def actions(self) -> ActionRegistry:
        if self._actions is None:
            with self._ensure_lazy_lock():
                if self._actions is None:
                    _boot_log("services:lazy:actions")
                    actions_cls = ActionRegistry
                    if actions_cls is None:
                        from core.actions.action_registry import ActionRegistry as _ActionRegistry

                        globals()["ActionRegistry"] = _ActionRegistry
                        actions_cls = _ActionRegistry
                    self._actions = actions_cls(self.settings)
        return self._actions

    @property
    def batch_router(self) -> BatchRouter:
        if self._batch_router is None:
            with self._ensure_lazy_lock():
                if self._batch_router is None:
                    _boot_log("services:lazy:batch-router")
                    batch_router_cls = BatchRouter
                    if batch_router_cls is None:
                        from core.routing.batch_router import BatchRouter as _BatchRouter

                        globals()["BatchRouter"] = _BatchRouter
                        batch_router_cls = _BatchRouter
                    self._batch_router = batch_router_cls(self.actions)
        return self._batch_router

    @property
    def pc_control(self) -> PcControlService:
        if self._pc_control is None:
            with self._ensure_lazy_lock():
                if self._pc_control is None:
                    _boot_log("services:lazy:pc-control")
                    pc_control_cls = PcControlService
                    if pc_control_cls is None:
                        from core.pc_control.service import PcControlService as _PcControlService

                        globals()["PcControlService"] = _PcControlService
                        pc_control_cls = _PcControlService
                    self._pc_control = pc_control_cls(self.actions)
        return self._pc_control

    @property
    def command_router(self) -> CommandRouter:
        if self._command_router is None:
            with self._ensure_lazy_lock():
                if self._command_router is None:
                    _boot_log("services:lazy:command-router")
                    command_router_cls = CommandRouter
                    if command_router_cls is None:
                        from core.routing.command_router import CommandRouter as _CommandRouter

                        globals()["CommandRouter"] = _CommandRouter
                        command_router_cls = _CommandRouter
                    self._command_router = command_router_cls(
                        self.actions,
                        self.batch_router,
                        self.ai,
                        self.pc_control,
                        reminder_provider=lambda: self.reminders,
                    )
        return self._command_router

    @property
    def reminders(self) -> ReminderService:
        if self._reminders is None:
            with self._ensure_lazy_lock():
                if self._reminders is None:
                    _boot_log("services:lazy:reminders")
                    reminders_cls = ReminderService
                    if reminders_cls is None:
                        from core.reminders.reminder_service import ReminderService as _ReminderService

                        globals()["ReminderService"] = _ReminderService
                        reminders_cls = _ReminderService
                    self._reminders = reminders_cls()
        return self._reminders

    @property
    def telegram(self) -> TelegramService:
        if self._telegram is None:
            with self._ensure_lazy_lock():
                if self._telegram is None:
                    _boot_log("services:lazy:telegram")
                    telegram_service_cls = TelegramService
                    if telegram_service_cls is None:
                        from core.telegram.telegram_service import TelegramService as _TelegramService

                        globals()["TelegramService"] = _TelegramService
                        telegram_service_cls = _TelegramService
                    self._telegram = telegram_service_cls(
                        self.settings,
                        transport=self._create_telegram_transport(),
                        handler=self.handle_external_command,
                        classifier=self.classify_external_command,
                    )
        return self._telegram

    @property
    def voice(self) -> VoiceService:
        if self._voice is None:
            with self._ensure_lazy_lock():
                if self._voice is None:
                    _boot_log("services:lazy:voice")
                    voice_service_cls = VoiceService
                    if voice_service_cls is None:
                        from core.voice.voice_service import VoiceService as _VoiceService

                        globals()["VoiceService"] = _VoiceService
                        voice_service_cls = _VoiceService
                    self._voice = voice_service_cls(self.settings)
        return self._voice

    @property
    def wake(self) -> WakeService:
        if self._wake is None:
            with self._ensure_lazy_lock():
                if self._wake is None:
                    _boot_log("services:lazy:wake")
                    wake_service_cls = WakeService
                    if wake_service_cls is None:
                        from core.voice.wake_service import WakeService as _WakeService

                        globals()["WakeService"] = _WakeService
                        wake_service_cls = _WakeService
                    self._wake = wake_service_cls(self.settings, self.voice)
        return self._wake

    @property
    def updates(self) -> UpdateService:
        if self._updates is None:
            with self._ensure_lazy_lock():
                if self._updates is None:
                    _boot_log("services:lazy:updates")
                    update_service_cls = UpdateService
                    if update_service_cls is None:
                        from core.updates.update_service import UpdateService as _UpdateService

                        globals()["UpdateService"] = _UpdateService
                        update_service_cls = _UpdateService
                    self._updates = update_service_cls(self.settings)
        return self._updates

    def refresh_telegram_transport(self) -> None:
        telegram = self.telegram
        if hasattr(telegram, "refresh_configuration"):
            telegram.refresh_configuration()
            return
        telegram.transport = self._create_telegram_transport()
        telegram.load_offset()

    def prepare_for_data_reset(self) -> None:
        wake = getattr(self, "_wake", None)
        if wake is not None and hasattr(wake, "stop"):
            try:
                wake.stop()
            except Exception:
                pass

        voice = getattr(self, "_voice", None)
        if voice is not None:
            if hasattr(voice, "stop_manual_capture"):
                try:
                    voice.stop_manual_capture()
                except Exception:
                    pass
            if hasattr(voice, "cancel_active_pipeline"):
                try:
                    voice.cancel_active_pipeline()
                except Exception:
                    pass

        telegram = getattr(self, "_telegram", None)
        if telegram is not None and hasattr(telegram, "pause_for_reset"):
            try:
                telegram.pause_for_reset()
            except Exception:
                pass

        local_runtime = getattr(self, "_local_runtime", None)
        if local_runtime is not None and hasattr(local_runtime, "shutdown"):
            try:
                local_runtime.shutdown()
            except Exception:
                pass

    def _create_telegram_transport(self) -> HttpTelegramTransport | None:
        registration = self.settings.get_registration()
        token = str(registration.get("telegram_bot_token", "")).strip()
        if not token:
            return None
        transport_cls = HttpTelegramTransport
        if transport_cls is None:
            from core.telegram.telegram_service import HttpTelegramTransport as _HttpTelegramTransport

            globals()["HttpTelegramTransport"] = _HttpTelegramTransport
            transport_cls = _HttpTelegramTransport

        network = self.settings.get("network", {}) or {}
        timeout_value = network.get("timeout_seconds", 12.0)
        proxy_mode = str(network.get("proxy_mode", "system")).strip().lower()
        if proxy_mode not in {"system", "manual", "off"}:
            proxy_mode = "system"
        proxy_url = str(network.get("proxy_url", "")).strip()
        try:
            timeout = float(timeout_value)
        except (TypeError, ValueError):
            timeout = 12.0
        timeout = max(3.0, timeout)
        return transport_cls(
            token,
            timeout_seconds=timeout,
            proxy_mode=proxy_mode,
            proxy_url=proxy_url,
        )

    def _telegram_history(self, chat_id: str) -> list[dict[str, str]]:
        key = str(chat_id or "").strip()
        if not key:
            return []
        lock = getattr(self, "_telegram_history_lock", None)
        if lock is None:
            history = getattr(self, "_telegram_history_by_chat_id", {}).get(key)
            if history is None:
                return []
            return [dict(item) for item in history]
        with lock:
            history = self._telegram_history_by_chat_id.get(key)
            if history is None:
                return []
            return [dict(item) for item in history]

    def _telegram_recent_context(self, history: list[dict[str, str]], *, limit: int = 6) -> list[str]:
        recent = history[-limit:]
        lines: list[str] = []
        for item in recent:
            role = str(item.get("role", "") or "").strip().casefold()
            speaker = "Пользователь" if role == "user" else "JARVIS"
            text = self._telegram_limit_text(item.get("text", ""))
            if text:
                lines.append(f"{speaker}: {text}")
        return lines

    def _telegram_limit_text(self, text: object, *, limit: int = 120) -> str:
        clean = normalize_text(str(text or "").strip())
        if len(clean) <= limit:
            return clean
        return f"{clean[: max(0, limit - 1)].rstrip()}…"

    def _remember_telegram_exchange(self, chat_id: str, user_text: str, assistant_text: str) -> None:
        key = str(chat_id or "").strip()
        user = str(user_text or "").strip()
        assistant = str(assistant_text or "").strip()
        if not key or not user or not assistant:
            return
        with self._telegram_history_lock:
            history = self._telegram_history_by_chat_id.setdefault(
                key,
                deque(maxlen=self._telegram_history_limit),
            )
            history.append({"role": "user", "text": user})
            history.append({"role": "assistant", "text": assistant})

    def _telegram_ai_prompt(self, text: str, history: list[dict[str, str]]) -> str:
        clean = str(text or "").strip()
        if not clean:
            return ""
        prompt_lines = [
            "Ты отвечаешь в Telegram как JARVIS.",
            "Отвечай на языке пользователя.",
            "Держи ответы короткими, но не сухими.",
            "Если это команда, отвечай кратко и по делу без лишних вступлений.",
            "Если это обычный разговор, отвечай естественно и по-человечески.",
            "Если пользователь отвечает коротко вроде да/ок/ясно, опирайся на контекст.",
            "Если не уверен или не знаешь ответ, скажи это прямо и задай один короткий уточняющий вопрос.",
            "Не выдумывай факты.",
        ]
        context_lines = self._telegram_recent_context(history)
        if context_lines:
            prompt_lines.extend(["", "Контекст чата:"])
            prompt_lines.extend(context_lines)
        prompt_lines.extend(["", f"Текущий запрос: {clean}"])
        return "\n".join(prompt_lines)

    def _compact_telegram_reply(self, text: str, *, max_lines: int = 4) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            return ""
        return "\n".join(lines[:max_lines])

    def _run_telegram_ai(
        self,
        text: str,
        history: list[dict[str, str]],
        *,
        status_callback: Callable[[str], None] | None = None,
        telegram_chat_id: str = "",
    ) -> str:
        prompt = self._telegram_ai_prompt(text, history)
        if hasattr(self.ai, "generate_reply_result"):
            result = self.ai.generate_reply_result(prompt, history, status_callback=status_callback)
            reply = str(getattr(result, "text", "") or "").strip()
        else:
            if status_callback is not None:
                status_callback("telegram_ai")
            reply = str(self.ai.generate_reply(prompt, history) or "").strip()
        compact = self._compact_telegram_reply(reply)
        self._remember_telegram_exchange(telegram_chat_id, text, compact)
        return compact

    def _should_use_telegram_contextual_ai(self, text: str, history: list[dict[str, str]]) -> bool:
        clean = normalize_text(text).casefold()
        if not clean or not history:
            return False
        if looks_like_broken_command(clean) or looks_like_system_command(clean):
            return False
        words = clean.split()
        if len(words) > 3:
            return False
        return any(word in self.TELEGRAM_CONTEXTUAL_REPLY_WORDS for word in words)

    def _telegram_route_reply(self, route) -> str:  # noqa: ANN001
        execution_result = getattr(route, "execution_result", None)
        if execution_result is None:
            return ""
        lines: list[str] = []
        for step in getattr(execution_result, "steps", []) or []:
            title = str(getattr(step, "title", "") or "").strip()
            if not title:
                continue
            lines.append(title)
        return "\n".join(lines[:2])

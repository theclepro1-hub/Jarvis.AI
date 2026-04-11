from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, TypeVar

from core.services.chat_history_store import ChatHistoryStore
from core.settings.settings_service import SettingsService
from core.settings.startup_manager import StartupManager
from core.settings.settings_store import SettingsStore

if TYPE_CHECKING:
    from core.actions.action_registry import ActionRegistry
    from core.ai.ai_service import AIService
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
PcControlService = None
RegistrationService = None
ReminderService = None
TelegramService = None
UpdateService = None
VoiceService = None
WakeService = None

T = TypeVar("T")


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
        self._lazy_lock = threading.RLock()
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
        self._reminders = None
        self._telegram = None
        self._voice = None
        self._wake = None
        self._updates = None
        self._ai = None
        self._actions = None
        self._batch_router = None
        self._pc_control = None
        self._command_router = None
        _boot_log("services:init:lazy-heavy-services")

    def _get_or_create_lazy_service(self, attr_name: str, label: str, factory: Callable[[], T]) -> T:
        value = getattr(self, attr_name)
        if value is not None:
            return value
        with self._lazy_lock:
            value = getattr(self, attr_name)
            if value is None:
                _boot_log(f"services:lazy:{label}")
                value = factory()
                setattr(self, attr_name, value)
            return value

    def handle_external_command(self, text: str, telegram_chat_id: str = "") -> str:
        route = self.command_router.handle(text, source="telegram", telegram_chat_id=telegram_chat_id)
        if route.assistant_lines:
            return "\n".join(route.assistant_lines)
        if route.kind != "ai" and not route.commands:
            return ""
        clean = " ".join(route.commands).strip() if route.commands else text
        return self.ai.generate_reply(clean, [])

    @property
    def ai(self) -> AIService:
        def factory() -> AIService:
            ai_service_cls = AIService
            if ai_service_cls is None:
                from core.ai.ai_service import AIService as _AIService

                globals()["AIService"] = _AIService
                ai_service_cls = _AIService
            return ai_service_cls(self.settings)

        return self._get_or_create_lazy_service("_ai", "ai", factory)

    @property
    def actions(self) -> ActionRegistry:
        def factory() -> ActionRegistry:
            actions_cls = ActionRegistry
            if actions_cls is None:
                from core.actions.action_registry import ActionRegistry as _ActionRegistry

                globals()["ActionRegistry"] = _ActionRegistry
                actions_cls = _ActionRegistry
            return actions_cls(self.settings)

        return self._get_or_create_lazy_service("_actions", "actions", factory)

    @property
    def batch_router(self) -> BatchRouter:
        def factory() -> BatchRouter:
            batch_router_cls = BatchRouter
            if batch_router_cls is None:
                from core.routing.batch_router import BatchRouter as _BatchRouter

                globals()["BatchRouter"] = _BatchRouter
                batch_router_cls = _BatchRouter
            return batch_router_cls(self.actions)

        return self._get_or_create_lazy_service("_batch_router", "batch-router", factory)

    @property
    def pc_control(self) -> PcControlService:
        def factory() -> PcControlService:
            pc_control_cls = PcControlService
            if pc_control_cls is None:
                from core.pc_control.service import PcControlService as _PcControlService

                globals()["PcControlService"] = _PcControlService
                pc_control_cls = _PcControlService
            return pc_control_cls(self.actions)

        return self._get_or_create_lazy_service("_pc_control", "pc-control", factory)

    @property
    def command_router(self) -> CommandRouter:
        def factory() -> CommandRouter:
            command_router_cls = CommandRouter
            if command_router_cls is None:
                from core.routing.command_router import CommandRouter as _CommandRouter

                globals()["CommandRouter"] = _CommandRouter
                command_router_cls = _CommandRouter
            return command_router_cls(
                self.actions,
                self.batch_router,
                self.ai,
                self.pc_control,
                reminder_provider=lambda: self.reminders,
            )

        return self._get_or_create_lazy_service("_command_router", "command-router", factory)

    @property
    def reminders(self) -> ReminderService:
        def factory() -> ReminderService:
            reminders_cls = ReminderService
            if reminders_cls is None:
                from core.reminders.reminder_service import ReminderService as _ReminderService

                globals()["ReminderService"] = _ReminderService
                reminders_cls = _ReminderService
            return reminders_cls()

        return self._get_or_create_lazy_service("_reminders", "reminders", factory)

    @property
    def telegram(self) -> TelegramService:
        def factory() -> TelegramService:
            telegram_service_cls = TelegramService
            if telegram_service_cls is None:
                from core.telegram.telegram_service import TelegramService as _TelegramService

                globals()["TelegramService"] = _TelegramService
                telegram_service_cls = _TelegramService
            return telegram_service_cls(
                self.settings,
                transport=self._create_telegram_transport(),
                handler=self.handle_external_command,
            )

        return self._get_or_create_lazy_service("_telegram", "telegram", factory)

    @property
    def voice(self) -> VoiceService:
        def factory() -> VoiceService:
            voice_service_cls = VoiceService
            if voice_service_cls is None:
                from core.voice.voice_service import VoiceService as _VoiceService

                globals()["VoiceService"] = _VoiceService
                voice_service_cls = _VoiceService
            return voice_service_cls(self.settings)

        return self._get_or_create_lazy_service("_voice", "voice", factory)

    @property
    def wake(self) -> WakeService:
        def factory() -> WakeService:
            wake_service_cls = WakeService
            if wake_service_cls is None:
                from core.voice.wake_service import WakeService as _WakeService

                globals()["WakeService"] = _WakeService
                wake_service_cls = _WakeService
            return wake_service_cls(self.settings, self.voice)

        return self._get_or_create_lazy_service("_wake", "wake", factory)

    @property
    def updates(self) -> UpdateService:
        def factory() -> UpdateService:
            update_service_cls = UpdateService
            if update_service_cls is None:
                from core.updates.update_service import UpdateService as _UpdateService

                globals()["UpdateService"] = _UpdateService
                update_service_cls = _UpdateService
            return update_service_cls(self.settings)

        return self._get_or_create_lazy_service("_updates", "updates", factory)

    def refresh_telegram_transport(self) -> None:
        telegram = self.telegram
        if hasattr(telegram, "refresh_configuration"):
            telegram.refresh_configuration()
            return
        telegram.transport = self._create_telegram_transport()
        telegram.load_offset()

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
        try:
            timeout = float(timeout_value)
        except (TypeError, ValueError):
            timeout = 12.0
        timeout = max(3.0, timeout)
        proxy_mode = str(network.get("proxy_mode", "system") or "system").strip().lower()
        if proxy_mode not in {"system", "manual", "off"}:
            proxy_mode = "system"
        proxy_url = str(network.get("proxy_url", "") or "").strip()
        return transport_cls(
            token,
            timeout_seconds=timeout,
            proxy_mode=proxy_mode,
            proxy_url=proxy_url,
        )

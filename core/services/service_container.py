from __future__ import annotations

import os
import time
from pathlib import Path

from core.actions.action_registry import ActionRegistry
from core.ai.ai_service import AIService
from core.pc_control.service import PcControlService
from core.reminders.reminder_service import ReminderService
from core.services.chat_history_store import ChatHistoryStore
from core.registration.registration_service import RegistrationService
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter
from core.settings.settings_service import SettingsService
from core.settings.startup_manager import StartupManager
from core.settings.settings_store import SettingsStore
from core.telegram.telegram_service import HttpTelegramTransport, TelegramService
from core.updates.update_service import UpdateService
from core.voice.voice_service import VoiceService
from core.voice.wake_service import WakeService


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
        self.settings.set("startup_enabled", self.startup.is_enabled())
        _boot_log("services:init:startup-state")
        self.registration = RegistrationService(self.settings)
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
        if self._ai is None:
            _boot_log("services:lazy:ai")
            self._ai = AIService(self.settings)
        return self._ai

    @property
    def actions(self) -> ActionRegistry:
        if self._actions is None:
            _boot_log("services:lazy:actions")
            self._actions = ActionRegistry(self.settings)
        return self._actions

    @property
    def batch_router(self) -> BatchRouter:
        if self._batch_router is None:
            _boot_log("services:lazy:batch-router")
            self._batch_router = BatchRouter(self.actions)
        return self._batch_router

    @property
    def pc_control(self) -> PcControlService:
        if self._pc_control is None:
            _boot_log("services:lazy:pc-control")
            self._pc_control = PcControlService(self.actions)
        return self._pc_control

    @property
    def command_router(self) -> CommandRouter:
        if self._command_router is None:
            _boot_log("services:lazy:command-router")
            self._command_router = CommandRouter(
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
            _boot_log("services:lazy:reminders")
            self._reminders = ReminderService()
        return self._reminders

    @property
    def telegram(self) -> TelegramService:
        if self._telegram is None:
            _boot_log("services:lazy:telegram")
            self._telegram = TelegramService(
                self.settings,
                transport=self._create_telegram_transport(),
                handler=self.handle_external_command,
            )
        return self._telegram

    @property
    def voice(self) -> VoiceService:
        if self._voice is None:
            _boot_log("services:lazy:voice")
            self._voice = VoiceService(self.settings)
        return self._voice

    @property
    def wake(self) -> WakeService:
        if self._wake is None:
            _boot_log("services:lazy:wake")
            self._wake = WakeService(self.settings, self.voice)
        return self._wake

    @property
    def updates(self) -> UpdateService:
        if self._updates is None:
            _boot_log("services:lazy:updates")
            self._updates = UpdateService(self.settings)
        return self._updates

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
        network = self.settings.get("network", {}) or {}
        timeout_value = network.get("timeout_seconds", 12.0)
        try:
            timeout = float(timeout_value)
        except (TypeError, ValueError):
            timeout = 12.0
        timeout = max(3.0, timeout)
        return HttpTelegramTransport(token, timeout_seconds=timeout)

from __future__ import annotations

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
from core.voice.stt_service import STTService
from core.voice.voice_service import VoiceService
from core.voice.wake_service import WakeService


class ServiceContainer:
    def __init__(self) -> None:
        self.settings_store = SettingsStore()
        self.chat_history = ChatHistoryStore()
        self.settings = SettingsService(self.settings_store)
        self.startup = StartupManager()
        self.settings.set("startup_enabled", self.startup.is_enabled())
        self.registration = RegistrationService(self.settings)
        self.ai = AIService(self.settings)
        self.actions = ActionRegistry(self.settings)
        self.batch_router = BatchRouter(self.actions)
        self.pc_control = PcControlService(self.actions)
        self.reminders = ReminderService()
        self.command_router = CommandRouter(
            self.actions,
            self.batch_router,
            self.ai,
            self.pc_control,
            reminder_service=self.reminders,
        )
        self.telegram = TelegramService(
            self.settings,
            transport=self._create_telegram_transport(),
            handler=self.handle_external_command,
        )
        self.voice = VoiceService(self.settings)
        self.stt = STTService(self.settings)
        self.wake = WakeService(self.settings, self.voice)
        self.updates = UpdateService()

    def handle_external_command(self, text: str) -> str:
        route = self.command_router.handle(text)
        if route.assistant_lines:
            return "\n".join(route.assistant_lines)
        return self.ai.generate_reply(text, [])

    def _create_telegram_transport(self) -> HttpTelegramTransport | None:
        registration = self.settings.get_registration()
        token = str(registration.get("telegram_bot_token", "")).strip()
        if not token:
            return None
        network = self.settings.get("network", {}) or {}
        timeout = float(network.get("timeout_seconds", 12.0))
        return HttpTelegramTransport(token, timeout_seconds=timeout)

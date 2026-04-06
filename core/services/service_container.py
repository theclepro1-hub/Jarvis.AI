from __future__ import annotations

from core.actions.action_registry import ActionRegistry
from core.ai.ai_service import AIService
from core.services.chat_history_store import ChatHistoryStore
from core.registration.registration_service import RegistrationService
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter
from core.settings.settings_service import SettingsService
from core.settings.startup_manager import StartupManager
from core.settings.settings_store import SettingsStore
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
        self.command_router = CommandRouter(self.actions, self.batch_router, self.ai)
        self.voice = VoiceService(self.settings)
        self.stt = STTService()
        self.wake = WakeService(self.settings, self.voice)
        self.updates = UpdateService()

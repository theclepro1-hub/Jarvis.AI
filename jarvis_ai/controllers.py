from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .action_catalog import ActionSpec, get_action_spec
from .action_permissions import ask_permission, permission_action_label, permission_category_for_action


@dataclass
class UiShell:
    app: Any

    def refresh_layout(self) -> Any:
        refresh = getattr(self.app, "refresh_workspace_layout_mode", None)
        if callable(refresh):
            return refresh()
        apply_bounds = getattr(self.app, "_apply_main_container_bounds", None)
        if callable(apply_bounds):
            return apply_bounds()
        return None

    def open_settings(self, section: str = "general") -> Any:
        opener = getattr(self.app, "open_full_settings_view", None)
        if callable(opener):
            return opener(section=section)
        return None

    def close_settings(self) -> Any:
        closer = getattr(self.app, "close_full_settings_view", None)
        if callable(closer):
            return closer()
        return None


@dataclass
class ConversationController:
    app: Any

    def process_query(self, query: str, reply_callback=None) -> Any:
        return self.app.process_query(query, reply_callback=reply_callback)

    def dispatch_intents(self, intents, raw_cmd: str, reply_callback=None) -> Any:
        return self.app.dispatch_ai_intents(intents, raw_cmd, reply_callback=reply_callback)

    def add_message(self, text: str, role: str = "bot") -> Any:
        return self.app.add_msg(text, role)


@dataclass
class VoiceController:
    app: Any

    def toggle_manual_capture(self) -> Any:
        toggle = getattr(self.app, "toggle_recording", None)
        if callable(toggle):
            return toggle()
        return None

    def run_recording_test(self, callback=None) -> Any:
        tester = getattr(self.app, "run_voice_recording_test", None)
        if callable(tester):
            return tester(callback=callback)
        return None

    def speak(self, text: str) -> Any:
        return self.app.speak_msg(text)

    def stop_audio(self) -> None:
        stop_event = getattr(self.app, "_tts_stop_event", None)
        if stop_event is not None:
            stop_event.set()
        stopper = getattr(self.app, "_stop_active_audio_stream_locked", None)
        lock = getattr(self.app, "speaking_lock", None)
        if callable(stopper):
            if lock is None:
                stopper()
            else:
                with lock:
                    stopper()


@dataclass
class WindowController:
    app: Any

    def apply_bounds(self) -> Any:
        apply_bounds = getattr(self.app, "_apply_main_container_bounds", None)
        if callable(apply_bounds):
            return apply_bounds()
        return None

    def toggle_fullscreen(self) -> Any:
        toggle = getattr(self.app, "toggle_fullscreen", None)
        if callable(toggle):
            return toggle()
        return None

    def hide_to_tray(self) -> Any:
        hide = getattr(self.app, "hide_to_tray", None)
        if callable(hide):
            return hide()
        return None

    def toggle_window(self) -> Any:
        toggle = getattr(self.app, "toggle_window", None)
        if callable(toggle):
            return toggle()
        return None


@dataclass
class ActionExecutor:
    app: Any

    def metadata(self, action: str) -> ActionSpec | None:
        return get_action_spec(action)

    def describe(self, action: str, arg: Any = None) -> str:
        return permission_action_label(action, arg)

    def allow(self, action: str, arg: Any = None, origin: str = "voice/chat") -> bool:
        category = permission_category_for_action(action)
        if not category:
            return True
        return ask_permission(
            self.app,
            action,
            arg,
            category=category,
            origin=origin,
        )

    def dispatch(
        self,
        action: str,
        arg: Any = None,
        *,
        origin: str = "voice/chat",
        handler: Callable[[str, Any], Any] | None = None,
    ) -> Any:
        if not self.allow(action, arg, origin=origin):
            return None
        if not callable(handler):
            raise ValueError("ActionExecutor.dispatch requires an explicit handler")
        return handler(action, arg)


@dataclass
class AppControllers:
    ui_shell: UiShell
    conversation: ConversationController
    voice: VoiceController
    window: WindowController
    actions: ActionExecutor


def build_app_controllers(app: Any) -> AppControllers:
    return AppControllers(
        ui_shell=UiShell(app),
        conversation=ConversationController(app),
        voice=VoiceController(app),
        window=WindowController(app),
        actions=ActionExecutor(app),
    )


__all__ = [
    "ActionExecutor",
    "AppControllers",
    "ConversationController",
    "UiShell",
    "VoiceController",
    "WindowController",
    "build_app_controllers",
]

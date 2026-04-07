from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SettingsSnapshot:
    theme_mode: str
    startup_enabled: bool
    privacy_mode: str
    ai_mode: str
    ai_model: str
    voice_mode: str
    command_style: str

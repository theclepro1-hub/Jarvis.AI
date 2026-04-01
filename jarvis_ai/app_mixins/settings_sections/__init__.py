from .apps import build_apps_settings_section
from .diagnostics import build_diagnostics_settings_section
from .main import build_main_settings_section
from .system import build_system_settings_section
from .updates import build_updates_settings_section
from .voice import build_voice_settings_section

__all__ = [
    "build_apps_settings_section",
    "build_diagnostics_settings_section",
    "build_main_settings_section",
    "build_system_settings_section",
    "build_updates_settings_section",
    "build_voice_settings_section",
]

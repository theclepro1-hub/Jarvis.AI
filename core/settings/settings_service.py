from __future__ import annotations

from typing import Any

from core.state.settings_state import SettingsSnapshot


class SettingsService:
    def __init__(self, store) -> None:
        self.store = store
        self._settings = self.store.load()

    def snapshot(self) -> SettingsSnapshot:
        return SettingsSnapshot(
            theme_mode=self._settings["theme_mode"],
            startup_enabled=self._settings["startup_enabled"],
            privacy_mode=self._settings["privacy_mode"],
            ai_mode=self._settings["ai_mode"],
            ai_model=self._settings["ai_model"],
            voice_mode=self._settings["voice_mode"],
            command_style=self._settings["command_style"],
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value
        self.store.save(self._settings)

    def bulk_update(self, payload: dict[str, Any]) -> None:
        self._settings.update(payload)
        self.store.save(self._settings)

    def get_registration(self) -> dict[str, Any]:
        return dict(self._settings["registration"])

    def save_registration(self, payload: dict[str, str], skipped: bool = False) -> None:
        registration = dict(self._settings["registration"])
        registration.update(payload)
        registration["skipped"] = skipped
        self._settings["registration"] = registration
        self.store.save(self._settings)

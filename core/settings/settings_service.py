from __future__ import annotations

from typing import Any

from core.state.settings_state import SettingsSnapshot


class SettingsService:
    def __init__(self, store) -> None:
        self.store = store
        self._settings = self.store.load()

    def reload(self) -> None:
        self._settings = self.store.load()

    def snapshot(self) -> SettingsSnapshot:
        return SettingsSnapshot(
            theme_mode=self._settings["theme_mode"],
            startup_enabled=self._settings["startup_enabled"],
            privacy_mode=self._settings["privacy_mode"],
            assistant_mode=self._settings.get("assistant_mode", "standard"),
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

    def save_history_enabled(self) -> bool:
        return bool(self._settings.get("save_history_enabled", True))

    def set_save_history_enabled(self, value: bool) -> None:
        self._settings["save_history_enabled"] = bool(value)
        self.store.save(self._settings)

    def get_pinned_commands(self) -> list[str]:
        pinned = self._settings.get("pinned_commands", [])
        if not isinstance(pinned, list):
            return []
        return [str(item).strip() for item in pinned if str(item).strip()]

    def set_pinned_commands(self, values: list[str]) -> None:
        self._settings["pinned_commands"] = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        self.store.save(self._settings)

    def pin_command(self, command_id: str) -> list[str]:
        pinned = self.get_pinned_commands()
        normalized = str(command_id).strip()
        if normalized and normalized not in pinned:
            pinned.append(normalized)
            self.set_pinned_commands(pinned)
        return pinned

    def unpin_command(self, command_id: str) -> list[str]:
        normalized = str(command_id).strip()
        pinned = [item for item in self.get_pinned_commands() if item != normalized]
        self.set_pinned_commands(pinned)
        return pinned

    def clear_runtime_data(self) -> dict[str, Any]:
        result = self.store.delete_all_data()
        self.reload()
        return result

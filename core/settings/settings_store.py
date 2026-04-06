from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "theme_mode": "midnight",
    "startup_enabled": False,
    "privacy_mode": "balance",
    "ai_provider": "groq",
    "ai_model": "openai/gpt-oss-20b",
    "voice_mode": "balance",
    "command_style": "one_shot",
    "wake_word_enabled": True,
    "microphone_name": "Системный по умолчанию",
    "custom_apps": [],
    "registration": {
        "groq_api_key": "",
        "telegram_user_id": "",
        "telegram_bot_token": "",
        "skipped": False,
    },
}


class SettingsStore:
    def __init__(self) -> None:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            self.base_dir = Path(data_dir)
        else:
            appdata = Path(os.environ.get("APPDATA", Path.home()))
            self.base_dir = appdata / "JarvisAi_Unity"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.base_dir / "settings.json"

    def load(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return json.loads(json.dumps(DEFAULT_SETTINGS))
        with self.settings_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        merged = self._merge_defaults(data, DEFAULT_SETTINGS)
        microphone_name = str(merged.get("microphone_name", ""))
        if microphone_name.startswith("Р") and "Р" in microphone_name:
            merged["microphone_name"] = "Системный по умолчанию"
        return merged

    def save(self, payload: dict[str, Any]) -> None:
        with self.settings_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _merge_defaults(self, data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
        result = json.loads(json.dumps(defaults))
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key].update(value)
            else:
                result[key] = value
        return result

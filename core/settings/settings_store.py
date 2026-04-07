from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
from pathlib import Path
from typing import Any

from ctypes import wintypes


DEFAULT_SETTINGS: dict[str, Any] = {
    "theme_mode": "midnight",
    "startup_enabled": False,
    "minimize_to_tray_enabled": True,
    "start_minimized_enabled": True,
    "save_history_enabled": True,
    "privacy_mode": "balance",
    "ai_provider": "auto",
    "ai_mode": "auto",
    "ai_model": "openai/gpt-oss-20b",
    "ai_max_attempts": 1,
    "network": {
        "proxy_mode": "system",
        "proxy_url": "",
        "no_proxy": "localhost,127.0.0.1,::1",
        "timeout_seconds": 12.0,
    },
    "voice_mode": "balance",
    "command_style": "one_shot",
    "wake_word_enabled": True,
    "microphone_name": "Системный микрофон",
    "voice_output_name": "Системный вывод",
    "voice_response_enabled": False,
    "tts_engine": "system",
    "tts_voice_name": "Голос по умолчанию",
    "tts_rate": 185,
    "tts_volume": 85,
    "pinned_commands": [],
    "custom_apps": [],
    "default_music_app": "",
    "registration": {
        "groq_api_key": "",
        "cerebras_api_key": "",
        "gemini_api_key": "",
        "openrouter_api_key": "",
        "telegram_user_id": "",
        "telegram_bot_token": "",
        "skipped": False,
    },
}

SECRET_REGISTRATION_FIELDS = (
    "groq_api_key",
    "cerebras_api_key",
    "gemini_api_key",
    "openrouter_api_key",
    "telegram_user_id",
    "telegram_bot_token",
)
PROTECTED_SECRET_PREFIX = "dpapi:"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


class SettingsStore:
    def __init__(self) -> None:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            self.base_dir = Path(data_dir)
        else:
            appdata = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
            self.base_dir = appdata / "JarvisAi_Unity"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.base_dir / "settings.json"

    def load(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return json.loads(json.dumps(DEFAULT_SETTINGS))

        with self.settings_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        merged = self._merge_defaults(data, DEFAULT_SETTINGS)
        self._restore_registration_secrets(merged)
        microphone_name = str(merged.get("microphone_name", "")).strip()
        if not microphone_name:
            merged["microphone_name"] = DEFAULT_SETTINGS["microphone_name"]
        output_name = str(merged.get("voice_output_name", "")).strip()
        if not output_name:
            merged["voice_output_name"] = DEFAULT_SETTINGS["voice_output_name"]
        return merged

    def save(self, payload: dict[str, Any]) -> None:
        payload_to_write = self._prepare_for_save(payload)
        temp_path = self.settings_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload_to_write, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self.settings_path)

    def delete_all_data(self) -> dict[str, Any]:
        resolved_base_dir = self.base_dir.resolve()
        if not self._is_safe_runtime_dir(resolved_base_dir):
            raise ValueError(f"Refusing to clear unsafe runtime directory: {resolved_base_dir}")

        deleted_files = 0
        deleted_dirs = 0
        if resolved_base_dir.exists():
            for entry in sorted(resolved_base_dir.iterdir(), key=lambda path: path.name):
                deleted_files, deleted_dirs = self._delete_entry(entry, deleted_files, deleted_dirs)

        resolved_base_dir.mkdir(parents=True, exist_ok=True)
        return {
            "base_dir": str(resolved_base_dir),
            "deleted_files": deleted_files,
            "deleted_dirs": deleted_dirs,
            "restart_required": True,
            "registration_required": True,
        }

    def _merge_defaults(self, data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
        result = json.loads(json.dumps(defaults))
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key].update(value)
            else:
                result[key] = value
        return result

    def _prepare_for_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = json.loads(json.dumps(payload))
        registration = result.get("registration")
        if os.name != "nt" or not isinstance(registration, dict):
            return result

        protected_fields: dict[str, str] = {}
        for field in SECRET_REGISTRATION_FIELDS:
            value = str(registration.get(field, "")).strip()
            if not value:
                continue
            protected_fields[field] = self._protect_text(value)
            registration[field] = ""

        if protected_fields:
            result["registration_secrets"] = {
                "provider": "windows-dpapi",
                "fields": protected_fields,
            }
        return result

    def _restore_registration_secrets(self, payload: dict[str, Any]) -> None:
        if os.name != "nt":
            return

        registration = payload.get("registration")
        secrets = payload.get("registration_secrets")
        if not isinstance(registration, dict) or not isinstance(secrets, dict):
            return

        fields = secrets.get("fields", {})
        if not isinstance(fields, dict):
            return

        for field in SECRET_REGISTRATION_FIELDS:
            protected_value = fields.get(field)
            if not isinstance(protected_value, str) or not protected_value:
                continue
            registration[field] = self._unprotect_text(protected_value)

    def _protect_text(self, value: str) -> str:
        raw = value.encode("utf-8")
        blob_in, buffer = self._blob_from_bytes(raw)
        blob_out = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            "JarvisAi_Unity",
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        )
        _ = buffer
        if not ok:
            raise OSError(ctypes.get_last_error(), "CryptProtectData failed")

        try:
            encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
        return PROTECTED_SECRET_PREFIX + base64.b64encode(encrypted).decode("ascii")

    def _unprotect_text(self, protected_value: str) -> str:
        if not protected_value.startswith(PROTECTED_SECRET_PREFIX):
            return protected_value

        encrypted = base64.b64decode(protected_value[len(PROTECTED_SECRET_PREFIX) :])
        blob_in, buffer = self._blob_from_bytes(encrypted)
        blob_out = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        )
        _ = buffer
        if not ok:
            raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")

        try:
            raw = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
        return raw.decode("utf-8")

    def _blob_from_bytes(self, raw: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(raw, len(raw))
        blob = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        return blob, buffer

    def _delete_entry(self, entry: Path, deleted_files: int, deleted_dirs: int) -> tuple[int, int]:
        resolved_entry = entry.resolve()
        if not self._is_safe_child_path(resolved_entry):
            raise ValueError(f"Refusing to delete outside runtime directory: {resolved_entry}")

        if resolved_entry.is_dir():
            for child in sorted(resolved_entry.iterdir(), key=lambda path: path.name):
                deleted_files, deleted_dirs = self._delete_entry(child, deleted_files, deleted_dirs)
            shutil.rmtree(resolved_entry, ignore_errors=False)
            return deleted_files, deleted_dirs + 1

        resolved_entry.unlink(missing_ok=True)
        return deleted_files + 1, deleted_dirs

    def _is_safe_runtime_dir(self, resolved_path: Path) -> bool:
        if resolved_path.name != "JarvisAi_Unity":
            return False
        if os.environ.get("JARVIS_UNITY_DATA_DIR"):
            return True
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not appdata:
            return False
        try:
            return resolved_path.is_relative_to(Path(appdata).resolve())
        except ValueError:
            return False

    def _is_safe_child_path(self, resolved_path: Path) -> bool:
        try:
            return resolved_path.is_relative_to(self.base_dir.resolve())
        except ValueError:
            return False

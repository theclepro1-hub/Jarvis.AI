from __future__ import annotations

import base64
import ctypes
import json
import os
from pathlib import Path
from typing import Any

from ctypes import wintypes


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

SECRET_REGISTRATION_FIELDS = ("groq_api_key", "telegram_user_id", "telegram_bot_token")
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
        self._restore_registration_secrets(merged)
        microphone_name = str(merged.get("microphone_name", "")).strip()
        if not microphone_name:
            merged["microphone_name"] = "Системный по умолчанию"
        return merged

    def save(self, payload: dict[str, Any]) -> None:
        payload_to_write = self._prepare_for_save(payload)
        temp_path = self.settings_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload_to_write, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self.settings_path)

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

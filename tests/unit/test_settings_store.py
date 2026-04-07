from __future__ import annotations

import json
import os

from core.settings.settings_store import DEFAULT_SETTINGS, SettingsStore


def test_settings_store_round_trips_registration_without_plaintext_secrets(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store = SettingsStore()
    payload = json.loads(json.dumps(DEFAULT_SETTINGS))
    payload["registration"] = {
        "groq_api_key": "gsk_test_secret",
        "telegram_user_id": "123456789",
        "telegram_bot_token": "bot_test_secret",
        "skipped": False,
    }

    store.save(payload)

    raw = store.settings_path.read_text(encoding="utf-8")
    loaded = store.load()["registration"]
    assert loaded["groq_api_key"] == "gsk_test_secret"
    assert loaded["telegram_bot_token"] == "bot_test_secret"
    if os.name == "nt":
        assert "gsk_test_secret" not in raw
        assert "bot_test_secret" not in raw
        assert "windows-dpapi" in raw

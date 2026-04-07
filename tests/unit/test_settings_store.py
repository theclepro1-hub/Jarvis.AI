from __future__ import annotations

import json
import os

from core.settings.settings_store import DEFAULT_SETTINGS, SettingsStore
from core.services.chat_history_store import ChatHistoryStore
from core.reminders.reminder_store import ReminderStore
from core.telegram.telegram_service import TelegramOffsetStore


def test_settings_store_round_trips_registration_without_plaintext_secrets(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store = SettingsStore()
    payload = json.loads(json.dumps(DEFAULT_SETTINGS))
    payload["registration"] = {
        "groq_api_key": "fake_groq_test_secret",
        "cerebras_api_key": "cerebras_test_secret",
        "gemini_api_key": "gemini_test_secret",
        "openrouter_api_key": "openrouter_test_secret",
        "telegram_user_id": "123456789",
        "telegram_bot_token": "bot_test_secret",
        "skipped": False,
    }

    store.save(payload)

    raw = store.settings_path.read_text(encoding="utf-8")
    loaded = store.load()["registration"]
    assert loaded["groq_api_key"] == "fake_groq_test_secret"
    assert loaded["cerebras_api_key"] == "cerebras_test_secret"
    assert loaded["gemini_api_key"] == "gemini_test_secret"
    assert loaded["openrouter_api_key"] == "openrouter_test_secret"
    assert loaded["telegram_bot_token"] == "bot_test_secret"
    if os.name == "nt":
        assert "fake_groq_test_secret" not in raw
        assert "cerebras_test_secret" not in raw
        assert "gemini_test_secret" not in raw
        assert "openrouter_test_secret" not in raw
        assert "bot_test_secret" not in raw
        assert "windows-dpapi" in raw


def test_user_runtime_files_default_to_local_appdata(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    settings = SettingsStore()
    history = ChatHistoryStore()
    reminders = ReminderStore()
    telegram = TelegramOffsetStore()

    expected_base = tmp_path / "Local" / "JarvisAi_Unity"
    assert settings.settings_path == expected_base / "settings.json"
    assert history.history_path == expected_base / "chat_history.json"
    assert reminders.path == expected_base / "reminders.sqlite3"
    assert telegram.path == expected_base / "telegram_state.json"


def test_settings_store_defaults_cover_history_and_pinned_commands() -> None:
    payload = json.loads(json.dumps(DEFAULT_SETTINGS))

    assert payload["save_history_enabled"] is True
    assert payload["pinned_commands"] == []


def test_delete_all_data_clears_only_safe_runtime_dir(monkeypatch, tmp_path) -> None:
    runtime_dir = tmp_path / "JarvisAi_Unity"
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(runtime_dir))
    store = SettingsStore()

    nested_dir = store.base_dir / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "settings.json").write_text("{}", encoding="utf-8")
    (store.base_dir / "chat_history.json").write_text("[]", encoding="utf-8")
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("keep me", encoding="utf-8")

    result = store.delete_all_data()

    assert result["restart_required"] is True
    assert result["registration_required"] is True
    assert outside_file.exists()
    assert store.base_dir.exists()
    assert list(store.base_dir.iterdir()) == []

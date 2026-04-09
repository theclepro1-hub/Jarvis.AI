from __future__ import annotations

import json
import os
import threading
from pathlib import Path

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


def test_settings_store_falls_back_to_direct_write_when_replace_is_locked(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store = SettingsStore()

    initial = json.loads(json.dumps(DEFAULT_SETTINGS))
    initial["theme_mode"] = "midnight"
    store.save(initial)

    updated = json.loads(json.dumps(DEFAULT_SETTINGS))
    updated["theme_mode"] = "aurora"

    def locked_replace(self: Path, target: Path) -> Path:
        error = PermissionError("settings file is busy")
        error.winerror = 32
        raise error

    monkeypatch.setattr(Path, "replace", locked_replace)

    store.save(updated)

    persisted = json.loads(store.settings_path.read_text(encoding="utf-8"))
    assert persisted["theme_mode"] == "aurora"


def test_settings_store_raises_for_non_lock_replace_errors(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store = SettingsStore()
    payload = json.loads(json.dumps(DEFAULT_SETTINGS))

    def denied_replace(self: Path, target: Path) -> Path:
        error = PermissionError("access denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr(Path, "replace", denied_replace)

    try:
        store.save(payload)
    except PermissionError as exc:
        assert getattr(exc, "winerror", None) == 5
    else:
        raise AssertionError("expected save() to re-raise non-lock PermissionError")


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


def test_settings_store_concurrent_saves_keep_valid_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store_a = SettingsStore()
    store_b = SettingsStore()

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def writer(store: SettingsStore, theme_mode: str, pinned: str) -> None:
        try:
            payload = json.loads(json.dumps(DEFAULT_SETTINGS))
            payload["theme_mode"] = theme_mode
            payload["pinned_commands"] = [pinned]
            barrier.wait(timeout=2.0)
            store.save(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    thread_a = threading.Thread(target=writer, args=(store_a, "midnight", "youtube"))
    thread_b = threading.Thread(target=writer, args=(store_b, "steel", "discord"))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5.0)
    thread_b.join(timeout=5.0)

    assert not errors
    raw = store_a.settings_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["theme_mode"] in {"midnight", "steel"}
    assert parsed["pinned_commands"] in (["youtube"], ["discord"])
    assert list(store_a.base_dir.glob("*.tmp")) == []

from __future__ import annotations

import json

from core.services.chat_history_store import ChatHistoryStore, DEFAULT_MESSAGES


def test_chat_history_store_loads_utf8_bom_history(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store = ChatHistoryStore()
    history = [{"role": "user", "text": "hello", "time": "12:00"}]
    store.history_path.write_text("\ufeff" + json.dumps(history, ensure_ascii=False), encoding="utf-8")

    loaded = store.load()

    assert loaded == history


def test_chat_history_store_recovers_from_corrupt_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    store = ChatHistoryStore()
    store.history_path.write_text('{"role": "assistant",', encoding="utf-8")

    loaded = store.load()

    assert loaded == DEFAULT_MESSAGES
    backups = list(tmp_path.glob("chat_history.corrupt-*.json"))
    assert len(backups) == 1

import json

import jarvis_ai.custom_actions_store as store


def test_normalize_manifest_actions_filters_invalid_and_dedupes():
    normalized = store.normalize_manifest_actions(
        [
            {"name": "Docs", "launch": "https://example.com", "aliases": ["Docs", "docs", "Help"]},
            {"name": "Docs duplicate", "launch": "https://example.com/2", "key": "manifest_docs_1"},
            {"name": "", "launch": "missing-name"},
            {"name": "Missing launch"},
        ]
    )

    assert len(normalized) == 1
    assert normalized[0]["name"] == "Docs"
    assert normalized[0]["aliases"] == ["Docs", "Help"]
    assert normalized[0]["source"] == "manifest"


def test_upsert_manifest_action_updates_existing_key():
    items = [{"key": "manifest_docs", "name": "Docs", "launch": "https://example.com"}]

    updated = store.upsert_manifest_action(
        items,
        {"key": "manifest_docs", "name": "Docs 2", "launch": "https://example.com/new", "aliases": ["docs"]},
    )

    assert len(updated) == 1
    assert updated[0]["name"] == "Docs 2"
    assert updated[0]["launch"] == "https://example.com/new"


def test_save_and_load_manifest_actions_roundtrip(tmp_path, monkeypatch):
    manifest_path = tmp_path / "custom_actions.json"
    monkeypatch.setattr(store, "custom_actions_path", lambda: str(manifest_path))

    store.save_manifest_actions(
        [
            {"name": "Docs", "launch": "https://example.com", "aliases": ["docs"]},
            {"name": "Steam", "launch": r"C:\\Steam\\steam.exe", "close_exes": ["steam.exe"]},
        ]
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "actions" in payload

    loaded = store.load_manifest_actions()
    assert [item["name"] for item in loaded] == ["Docs", "Steam"]


def test_remove_manifest_action_drops_target_key():
    items = [
        {"key": "one", "name": "One", "launch": "https://one.example"},
        {"key": "two", "name": "Two", "launch": "https://two.example"},
    ]

    updated = store.remove_manifest_action(items, "two")

    assert [item["key"] for item in updated] == ["one"]

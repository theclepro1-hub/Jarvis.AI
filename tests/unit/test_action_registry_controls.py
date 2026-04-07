from __future__ import annotations

import json

from core.actions.action_registry import ActionRegistry
from core.actions.launcher_discovery import DiscoveredApp
from core.settings.settings_service import SettingsService
from core.settings.settings_store import DEFAULT_SETTINGS


class InMemoryStore:
    def __init__(self) -> None:
        self.payload = json.loads(json.dumps(DEFAULT_SETTINGS))

    def load(self):
        return json.loads(json.dumps(self.payload))

    def save(self, payload):
        self.payload = json.loads(json.dumps(payload))


def make_registry() -> tuple[ActionRegistry, SettingsService]:
    service = SettingsService(InMemoryStore())
    return ActionRegistry(service), service


def test_quick_actions_use_pinned_commands_before_defaults() -> None:
    registry, service = make_registry()
    service.set_pinned_commands(["youtube", "steam"])

    quick_actions = registry.quick_actions()

    assert [item["id"] for item in quick_actions[:2]] == ["youtube", "steam"]


def test_scan_and_import_reports_counts_without_noise() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_yandex_music",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            }
        ],
    )
    registry.catalog = registry._merged_catalog()

    class FakeDiscovery:
        def discover(self):
            return [
                DiscoveredApp(
                    source="Ярлыки Windows",
                    title="Яндекс Музыка",
                    target=r"C:\YandexMusic\Яндекс Музыка.exe",
                    kind="file",
                    other_names=["музыка"],
                    category="music",
                ),
                DiscoveredApp(
                    source="Ярлыки Windows",
                    title="Very Long Utility Launcher Name That Needs Review",
                    target=r"C:\Tools\utility.exe",
                    kind="file",
                    other_names=["utility"],
                    category="app",
                ),
            ]

    registry.discovery = FakeDiscovery()

    result = registry.scan_and_import_apps()

    assert result["added"] == 0
    assert result["already_existing"] == 1
    assert result["skipped"] >= 1
    assert result["conflict_count"] >= 0
    assert "Добавлено:" in result["summary"]

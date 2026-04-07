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


def test_quick_actions_are_curated_and_limited() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": f"custom_{index}",
                "title": f"Very Long Imported Game Name {index}",
                "aliases": [f"game {index}"],
                "kind": "uri",
                "target": f"steam://rungameid/{index}",
                "custom": True,
                "category": "game",
            }
            for index in range(20)
        ],
    )
    registry.catalog = registry._merged_catalog()

    quick = registry.quick_actions()

    assert [item["id"] for item in quick] == ["youtube", "browser", "music", "steam", "discord"]
    assert len(quick) <= 7


def test_generic_music_uses_single_custom_music_app() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\Users\me\AppData\Local\Programs\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            }
        ],
    )
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой музыку")

    assert question == ""
    assert items[0]["title"] == "Яндекс Музыка"


def test_exact_yandex_music_does_not_resolve_to_windows_music() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\Users\me\AppData\Local\Programs\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            }
        ],
    )
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой яндекс музыку")

    assert question == ""
    assert items[0]["title"] == "Яндекс Музыка"


def test_yandex_food_does_not_match_yandex_music() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
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

    items, question = registry.resolve_open_command("открой яндекс еду")

    assert question == ""
    assert items == []


def test_generic_music_asks_when_multiple_custom_music_apps_exist() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            },
            {
                "id": "custom_2",
                "title": "Spotify",
                "aliases": ["spotify", "музыка"],
                "kind": "file",
                "target": r"C:\Spotify\Spotify.exe",
                "custom": True,
                "category": "music",
            },
        ],
    )
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой музыку")

    assert items == []
    assert question == "Выберите основную музыку во вкладке «Приложения»."


def test_catalog_marks_music_default_for_ui_selector() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            },
            {
                "id": "custom_2",
                "title": "Spotify",
                "aliases": ["spotify", "спотифай", "музыка"],
                "kind": "file",
                "target": r"C:\Spotify\Spotify.exe",
                "custom": True,
                "category": "music",
            },
        ],
    )
    service.set("default_music_app", "custom_2")
    registry.catalog = registry._merged_catalog()

    by_title = {item["title"]: item for item in registry.app_catalog()}

    assert by_title["Яндекс Музыка"]["canBeDefaultMusic"] is True
    assert by_title["Яндекс Музыка"]["isDefaultMusic"] is False
    assert by_title["Spotify"]["isDefaultMusic"] is True


def test_user_catalog_hides_windows_music_when_real_music_exists() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            },
            {
                "id": "custom_2",
                "title": "Windows Media Player Legacy",
                "aliases": ["windows media player legacy", "windows media"],
                "kind": "file",
                "target": r"C:\Windows Media Player Legacy.lnk",
                "custom": True,
                "category": "music",
            },
        ],
    )
    registry.catalog = registry._merged_catalog()

    catalog = registry.app_catalog()
    titles = {item["title"] for item in catalog}
    ids = {item["id"] for item in catalog}

    assert "Яндекс Музыка" in titles
    assert "Windows Media Player Legacy" not in titles
    assert "music" not in ids


def test_catalog_marks_steam_section_without_swallowing_epic_games() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Deadlock",
                "aliases": ["deadlock", "steam"],
                "kind": "uri",
                "target": "steam://rungameid/1422450",
                "custom": True,
                "category": "game",
            },
            {
                "id": "custom_2",
                "title": "Fortnite",
                "aliases": ["fortnite", "epic"],
                "kind": "file",
                "target": r"D:\Fortnite\FortniteLauncher.exe",
                "custom": True,
                "category": "game",
            },
        ],
    )
    registry.catalog = registry._merged_catalog()

    by_title = {item["title"]: item["section"] for item in registry.app_catalog()}

    assert by_title["Steam"] == "steam"
    assert by_title["Deadlock"] == "steam"
    assert by_title["Fortnite"] == "app"


def test_exact_spotify_ignores_default_yandex_music() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            },
            {
                "id": "custom_2",
                "title": "Spotify",
                "aliases": ["spotify", "спотифай", "спотик", "музыка"],
                "kind": "file",
                "target": r"C:\Spotify\Spotify.exe",
                "custom": True,
                "category": "music",
            },
        ],
    )
    service.set("default_music_app", "custom_1")
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой spotify")

    assert question == ""
    assert items[0]["title"] == "Spotify"


def test_missing_explicit_spotify_returns_honest_app_message() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Яндекс Музыка",
                "aliases": ["яндекс музыка", "музыка"],
                "kind": "file",
                "target": r"C:\YandexMusic\Яндекс Музыка.exe",
                "custom": True,
                "category": "music",
            }
        ],
    )
    service.set("default_music_app", "custom_1")
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой спотифай")

    assert items == []
    assert question == "Spotify не найден. Добавьте приложение во вкладке «Приложения»."


def test_platform_launcher_alias_does_not_open_all_steam_games() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Deadlock",
                "aliases": ["deadlock", "steam"],
                "kind": "uri",
                "target": "steam://rungameid/1422450",
                "custom": True,
                "category": "game",
            }
        ],
    )
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой steam")

    assert question == ""
    assert [item["title"] for item in items] == ["Steam"]


def test_platform_launcher_alias_does_not_open_all_epic_games() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Epic Games Launcher",
                "aliases": ["epic", "epic games"],
                "kind": "file",
                "target": r"C:\ProgramData\Epic\Epic Games Launcher.lnk",
                "custom": True,
                "category": "launcher",
            },
            {
                "id": "custom_2",
                "title": "Fortnite",
                "aliases": ["fortnite", "epic"],
                "kind": "file",
                "target": r"D:\Fortnite\FortniteLauncher.exe",
                "custom": True,
                "category": "game",
            },
        ],
    )
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой epic games")

    assert question == ""
    assert [item["title"] for item in items] == ["Epic Games Launcher"]


def test_open_steam_launcher_does_not_match_every_steam_game() -> None:
    registry, service = make_registry()
    service.set(
        "custom_apps",
        [
            {
                "id": "custom_1",
                "title": "Deadlock",
                "aliases": ["deadlock", "steam", "стим"],
                "kind": "uri",
                "target": "steam://rungameid/1422450",
                "custom": True,
                "category": "game",
            }
        ],
    )
    registry.catalog = registry._merged_catalog()

    items, question = registry.resolve_open_command("открой steam")

    assert question == ""
    assert [item["title"] for item in items] == ["Steam"]


def test_scan_summary_mentions_review_candidates_when_auto_import_skips_them() -> None:
    registry, _service = make_registry()

    class FakeDiscovery:
        def discover(self):
            return [
                DiscoveredApp(
                    source="Ярлыки Windows",
                    title="Very Long Utility Launcher Name That Needs Review",
                    target=r"C:\Tools\utility.exe",
                    kind="file",
                    other_names=["utility"],
                    category="app",
                )
            ]

    registry.discovery = FakeDiscovery()

    result = registry.scan_and_import_apps()

    assert result["imported"] == []
    assert result["review"][0]["title"] == "Very Long Utility Launcher Name That Needs Review"
    assert result["summary"].startswith("Найдено для проверки:")

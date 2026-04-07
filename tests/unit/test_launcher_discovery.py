from __future__ import annotations

import json
from pathlib import Path

from core.actions.launcher_discovery import DiscoveryRoots, LauncherDiscovery, target_from_file_url


def make_roots(tmp_path: Path) -> DiscoveryRoots:
    return DiscoveryRoots(
        program_data=tmp_path / "ProgramData",
        app_data=tmp_path / "AppData" / "Roaming",
        local_app_data=tmp_path / "AppData" / "Local",
        program_files=tmp_path / "ProgramFiles",
        program_files_x86=tmp_path / "ProgramFilesX86",
        start_menu_all=tmp_path / "ProgramData" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        start_menu_user=tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    )


def test_discovers_steam_games_from_fake_manifest(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    steamapps = roots.program_files_x86 / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_1422450.acf").write_text(
        '"AppState"\n{\n    "appid" "1422450"\n    "name" "Deadlock"\n    "installdir" "Deadlock"\n}\n',
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()

    assert any(item.title == "Deadlock" and item.target == "steam://rungameid/1422450" for item in found)


def test_discovers_steam_libraries_from_libraryfolders_vdf(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    steam_root = roots.program_files_x86 / "Steam"
    default_steamapps = steam_root / "steamapps"
    library_steamapps = tmp_path / "Games" / "SteamLibrary" / "steamapps"
    default_steamapps.mkdir(parents=True)
    library_steamapps.mkdir(parents=True)
    (default_steamapps / "libraryfolders.vdf").write_text(
        f'"libraryfolders" {{ "1" {{ "path" "{str(library_steamapps.parent).replace(chr(92), chr(92) * 2)}" }} }}',
        encoding="utf-8",
    )
    (library_steamapps / "appmanifest_730.acf").write_text(
        '"AppState"\n{\n    "appid" "730"\n    "name" "Counter-Strike 2"\n}\n',
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()

    assert any(item.title == "Counter-Strike 2" and item.target == "steam://rungameid/730" for item in found)


def test_discovery_adds_natural_game_aliases_from_templates(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    steamapps = roots.program_files_x86 / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_730.acf").write_text(
        '"AppState"\n{\n    "appid" "730"\n    "name" "Counter-Strike 2"\n}\n',
        encoding="utf-8",
    )
    (steamapps / "appmanifest_381210.acf").write_text(
        '"AppState"\n{\n    "appid" "381210"\n    "name" "Dead by Daylight"\n}\n',
        encoding="utf-8",
    )
    (steamapps / "appmanifest_1422450.acf").write_text(
        '"AppState"\n{\n    "appid" "1422450"\n    "name" "Deadlock"\n}\n',
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()
    by_title = {item.title: item for item in found}

    assert "кс" in by_title["Counter-Strike 2"].other_names
    assert "кска" in by_title["Counter-Strike 2"].other_names
    assert "делочек" in by_title["Deadlock"].other_names
    assert "дбдшка" in by_title["Dead by Daylight"].other_names


def test_discovers_epic_games_from_fake_manifest(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    manifest_dir = roots.program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    install_dir = tmp_path / "EpicGames" / "Fortnite"
    binary = install_dir / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "fortnite.item").write_text(
        json.dumps(
            {
                "DisplayName": "Fortnite",
                "AppName": "Fortnite",
                "InstallLocation": str(install_dir),
                "LaunchExecutable": r"FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe",
            }
        ),
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()

    assert any(item.title == "Fortnite" and item.target == str(binary) for item in found)


def test_epic_fortnite_discovery_adds_natural_alias(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    manifest_dir = roots.program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    install_dir = tmp_path / "EpicGames" / "Fortnite"
    binary = install_dir / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "fortnite.item").write_text(
        json.dumps(
            {
                "DisplayName": "Fortnite",
                "AppName": "Fortnite",
                "InstallLocation": str(install_dir),
                "LaunchExecutable": r"FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe",
            }
        ),
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()
    fortnite = next(item for item in found if item.title == "Fortnite")

    assert "фортик" in fortnite.other_names


def test_discovers_known_music_apps_without_disk_wide_scan(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    spotify = roots.app_data / "Spotify" / "Spotify.exe"
    spotify.parent.mkdir(parents=True)
    spotify.write_text("", encoding="utf-8")

    found = LauncherDiscovery(roots).discover()

    assert any(item.title == "Spotify" and item.target == str(spotify) for item in found)
    assert any(item.title == "Музыка Windows" and item.target == "mswindowsmusic:" for item in found)


def test_discovers_more_music_shortcuts(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    for title in ("SoundCloud.lnk", "Apple Music.lnk"):
        shortcut = roots.start_menu_user / title
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        shortcut.write_text("", encoding="utf-8")

    found = LauncherDiscovery(roots).discover()
    titles = {item.title for item in found}

    assert "SoundCloud" in titles
    assert "Apple Music" in titles


def test_discovers_known_launcher_apps_from_common_paths(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    minecraft = roots.program_files_x86 / "Minecraft Launcher" / "MinecraftLauncher.exe"
    ubisoft = roots.program_files_x86 / "Ubisoft" / "Ubisoft Game Launcher" / "UbisoftConnect.exe"
    ea_app = roots.program_files / "Electronic Arts" / "EA Desktop" / "EA Desktop" / "EADesktop.exe"
    battle_net = roots.program_files_x86 / "Battle.net" / "Battle.net.exe"
    gog = roots.program_files_x86 / "GOG Galaxy" / "GalaxyClient.exe"
    epic = roots.program_files / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
    roblox = roots.local_app_data / "Roblox" / "Versions" / "version-a" / "RobloxPlayerBeta.exe"
    for path in (minecraft, ubisoft, ea_app, battle_net, gog, epic, roblox):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    found = LauncherDiscovery(roots).discover()
    by_title = {item.title: item for item in found}

    assert by_title["Minecraft Launcher"].target == str(minecraft)
    assert by_title["Ubisoft Connect"].target == str(ubisoft)
    assert by_title["EA app"].target == str(ea_app)
    assert by_title["Battle.net"].target == str(battle_net)
    assert by_title["GOG Galaxy"].target == str(gog)
    assert by_title["Epic Games Launcher"].target == str(epic)
    assert by_title["Roblox"].target == str(roblox)


def test_filters_steamworks_redistributables(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    steamapps = roots.program_files_x86 / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_228980.acf").write_text(
        '"AppState"\n{\n    "appid" "228980"\n    "name" "Steamworks Common Redistributables"\n}\n',
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()

    assert all(item.title != "Steamworks Common Redistributables" for item in found)


def test_dedupes_shortcut_and_direct_music_app(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    yandex_exe = roots.local_app_data / "Programs" / "YandexMusic" / "Яндекс Музыка.exe"
    yandex_exe.parent.mkdir(parents=True)
    yandex_exe.write_text("", encoding="utf-8")
    shortcut = roots.start_menu_user / "Яндекс Музыка.lnk"
    shortcut.parent.mkdir(parents=True)
    shortcut.write_text("", encoding="utf-8")

    found = LauncherDiscovery(roots).discover()
    yandex = [item for item in found if item.title == "Яндекс Музыка"]

    assert len(yandex) == 1
    assert yandex[0].target == str(yandex_exe)


def test_file_dialog_url_is_converted_to_windows_path() -> None:
    assert target_from_file_url("file:///C:/Games/Deadlock/deadlock.exe") == r"C:\Games\Deadlock\deadlock.exe"

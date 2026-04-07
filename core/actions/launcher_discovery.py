from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only module
    winreg = None  # type: ignore[assignment]


KNOWN_LAUNCHER_TERMS = (
    "steam",
    "epic",
    "epic games",
    "ubisoft",
    "ubisoft connect",
    "uplay",
    "gog",
    "galaxy",
    "battle.net",
    "battlenet",
    "blizzard",
    "ea app",
    "ea desktop",
    "electronic arts",
    "riot",
    "minecraft",
    "майнкрафт",
    "roblox",
    "роблокс",
)
KNOWN_MUSIC_TERMS = (
    "spotify",
    "яндекс музыка",
    "yandex music",
    "apple music",
    "itunes",
    "soundcloud",
    "саундклауд",
    "windows media",
    "media player",
)
JUNK_TITLE_TERMS = (
    "steamworks common redistributables",
    "redistributable",
    "redistributables",
    "redist",
    "directx",
    "runtime",
    "vulkan",
    "visual c++",
    "driver",
    "uninstall",
)
JUNK_TARGET_TERMS = (
    "uninstall",
    "unins",
    "redist",
    "redistributable",
    "redistributables",
)
NATURAL_ALIAS_TEMPLATES = (
    (
        ("counter-strike 2", "counter strike 2", "cs2"),
        ("кс", "кска", "кс2", "кс 2", "каэс", "контра", "контру", "counter strike", "counter-strike", "cs2", "cs 2"),
    ),
    (
        ("deadlock",),
        ("дедлок", "дедлока", "делочек", "дедлочек", "дэдлок", "deadlock"),
    ),
    (
        ("fortnite",),
        ("фортнайт", "фортик", "форт", "fortnite"),
    ),
    (
        ("dead by daylight", "dbd"),
        ("дбд", "дбдшка", "дбдшку", "дед бай дейлайт", "dead by daylight", "dbd"),
    ),
    (
        ("apple music",),
        ("эпл музыка", "эпл мьюзик", "эйпл мьюзик", "apple music"),
    ),
    (
        ("soundcloud",),
        ("саундклауд", "саунд клоуд", "soundcloud"),
    ),
)


@dataclass(slots=True)
class DiscoveryRoots:
    program_data: Path
    app_data: Path
    local_app_data: Path
    program_files: Path
    program_files_x86: Path
    start_menu_all: Path
    start_menu_user: Path

    @classmethod
    def from_environment(cls) -> DiscoveryRoots:
        home = Path.home()
        program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        app_data = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        return cls(
            program_data=program_data,
            app_data=app_data,
            local_app_data=local_app_data,
            program_files=program_files,
            program_files_x86=program_files_x86,
            start_menu_all=program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            start_menu_user=app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        )


@dataclass(slots=True)
class DiscoveredApp:
    source: str
    title: str
    target: str
    kind: str = "file"
    other_names: list[str] = field(default_factory=list)
    category: str = "app"

    @property
    def candidate_id(self) -> str:
        return _stable_candidate_id(self.source, self.title, self.target)

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.candidate_id,
            "source": self.source,
            "title": self.title,
            "target": self.target,
            "kind": self.kind,
            "category": self.category,
            "aliases": ", ".join(self.other_names),
        }


class LauncherDiscovery:
    def __init__(self, roots: DiscoveryRoots | None = None) -> None:
        self.roots = roots or DiscoveryRoots.from_environment()

    def discover(self) -> list[DiscoveredApp]:
        candidates: list[DiscoveredApp] = []
        candidates.extend(self._discover_steam_games())
        candidates.extend(self._discover_epic_games())
        candidates.extend(self._discover_known_launcher_apps())
        candidates.extend(self._discover_known_shortcuts())
        candidates.extend(self._discover_known_music_apps())
        candidates.extend(self._discover_installed_known_apps())
        return _dedupe_candidates([candidate for candidate in candidates if _is_user_facing_candidate(candidate)])

    def _discover_steam_games(self) -> list[DiscoveredApp]:
        steam_roots = _unique_paths([*self._steam_roots_from_registry(), *self._steam_roots_from_common_paths()])
        libraries: list[Path] = []
        for steam_root in steam_roots:
            steamapps = steam_root / "steamapps"
            if steamapps.exists():
                libraries.append(steamapps)
            libraries.extend(self._steam_libraries_from_vdf(steamapps / "libraryfolders.vdf"))

        candidates: list[DiscoveredApp] = []
        for steamapps in _unique_paths(libraries):
            for manifest_path in steamapps.glob("appmanifest_*.acf"):
                manifest = _parse_steam_acf(manifest_path)
                app_id = manifest.get("appid") or _first_regex(manifest_path.name, r"appmanifest_(\d+)\.acf")
                title = _canonical_title(manifest.get("name", ""))
                if not app_id or not title:
                    continue
                candidates.append(
                    DiscoveredApp(
                        source="Steam",
                        title=title,
                        target=f"steam://rungameid/{app_id}",
                        kind="uri",
                        other_names=_default_other_names(title),
                        category="game",
                    )
                )
        return candidates

    def _discover_known_launcher_apps(self) -> list[DiscoveredApp]:
        candidates: list[DiscoveredApp] = []
        specs = [
            (
                "Minecraft Launcher",
                [
                    self.roots.program_files_x86 / "Minecraft Launcher" / "MinecraftLauncher.exe",
                    self.roots.program_files / "Minecraft Launcher" / "MinecraftLauncher.exe",
                ],
                ["minecraft", "майнкрафт", "minecraft launcher"],
            ),
            (
                "Ubisoft Connect",
                [
                    self.roots.program_files_x86 / "Ubisoft" / "Ubisoft Game Launcher" / "UbisoftConnect.exe",
                    self.roots.program_files / "Ubisoft" / "Ubisoft Game Launcher" / "UbisoftConnect.exe",
                    self.roots.program_files_x86 / "Ubisoft" / "Ubisoft Game Launcher" / "Uplay.exe",
                ],
                ["ubisoft", "ubisoft connect", "uplay", "юбисофт"],
            ),
            (
                "EA app",
                [
                    self.roots.program_files / "Electronic Arts" / "EA Desktop" / "EA Desktop" / "EADesktop.exe",
                    self.roots.program_files / "Electronic Arts" / "EA Desktop" / "EA Desktop" / "EALauncher.exe",
                    self.roots.program_files_x86 / "Electronic Arts" / "EA Desktop" / "EA Desktop" / "EADesktop.exe",
                ],
                ["ea", "ea app", "ea desktop", "electronic arts"],
            ),
            (
                "Battle.net",
                [
                    self.roots.program_files_x86 / "Battle.net" / "Battle.net.exe",
                    self.roots.program_files / "Battle.net" / "Battle.net.exe",
                ],
                ["battle.net", "battlenet", "blizzard", "батлнет"],
            ),
            (
                "GOG Galaxy",
                [
                    self.roots.program_files_x86 / "GOG Galaxy" / "GalaxyClient.exe",
                    self.roots.program_files / "GOG Galaxy" / "GalaxyClient.exe",
                ],
                ["gog", "gog galaxy", "галакси"],
            ),
            (
                "Riot Client",
                [
                    Path(r"C:\Riot Games") / "Riot Client" / "RiotClientServices.exe",
                    self.roots.program_files / "Riot Games" / "Riot Client" / "RiotClientServices.exe",
                ],
                ["riot", "riot client", "райот"],
            ),
            (
                "Epic Games Launcher",
                [
                    self.roots.program_files_x86 / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win32" / "EpicGamesLauncher.exe",
                    self.roots.program_files / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
                ],
                ["epic", "epic games", "эпик", "эпик геймс"],
            ),
        ]

        for title, paths, aliases in specs:
            target = _first_existing_path(paths)
            if target:
                candidates.append(
                    DiscoveredApp(
                        source="Известные лаунчеры",
                        title=title,
                        target=str(target),
                        kind="file",
                        other_names=_dedupe_strings([title, title.casefold(), *aliases]),
                        category="launcher",
                    )
                )

        roblox_target = self._roblox_player_path()
        if roblox_target:
            candidates.append(
                DiscoveredApp(
                    source="Известные лаунчеры",
                    title="Roblox",
                    target=str(roblox_target),
                    kind="file",
                    other_names=["Roblox", "roblox", "роблокс"],
                    category="launcher",
                )
            )
        return candidates

    def _roblox_player_path(self) -> Path | None:
        versions_root = self.roots.local_app_data / "Roblox" / "Versions"
        if not versions_root.exists():
            return None
        candidates = [path for path in versions_root.glob("*/RobloxPlayerBeta.exe") if path.exists()]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _steam_roots_from_registry(self) -> list[Path]:
        if winreg is None:
            return []
        roots: list[Path] = []
        keys = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        )
        for hive, key_path, value_name in keys:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
            except OSError:
                continue
            if value:
                roots.append(Path(str(value)))
        return roots

    def _steam_roots_from_common_paths(self) -> list[Path]:
        return [
            self.roots.program_files_x86 / "Steam",
            self.roots.program_files / "Steam",
        ]

    def _steam_libraries_from_vdf(self, vdf_path: Path) -> list[Path]:
        if not vdf_path.exists():
            return []
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
        libraries: list[Path] = []
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', text):
            path = Path(raw_path.replace("\\\\", "\\"))
            steamapps = path / "steamapps"
            if steamapps.exists():
                libraries.append(steamapps)
        return libraries

    def _discover_epic_games(self) -> list[DiscoveredApp]:
        manifest_dir = self.roots.program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        candidates: list[DiscoveredApp] = []
        if not manifest_dir.exists():
            return candidates

        for manifest_path in manifest_dir.glob("*.item"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8", errors="ignore"))
            except json.JSONDecodeError:
                continue
            title = _canonical_title(str(payload.get("DisplayName") or payload.get("AppName") or ""))
            app_name = str(payload.get("AppName") or "").strip()
            install_location = Path(str(payload.get("InstallLocation") or "").strip())
            launch_executable = str(payload.get("LaunchExecutable") or "").strip()
            if not title:
                continue

            target = ""
            kind = "file"
            if launch_executable and install_location:
                executable_path = install_location / launch_executable
                if executable_path.exists():
                    target = str(executable_path)
            if not target and app_name:
                target = f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true"
                kind = "uri"
            if not target:
                continue

            candidates.append(
                DiscoveredApp(
                    source="Epic Games",
                    title=title,
                    target=target,
                    kind=kind,
                    other_names=_default_other_names(title),
                    category="game",
                )
            )
        return candidates

    def _discover_known_shortcuts(self) -> list[DiscoveredApp]:
        candidates: list[DiscoveredApp] = []
        for root in (self.roots.start_menu_all, self.roots.start_menu_user):
            if not root.exists():
                continue
            for shortcut_path in root.rglob("*.lnk"):
                title = _canonical_title(shortcut_path.stem)
                lower = title.casefold()
                if not _contains_known_term(lower, (*KNOWN_LAUNCHER_TERMS, *KNOWN_MUSIC_TERMS)):
                    continue
                category = "music" if _contains_known_term(lower, KNOWN_MUSIC_TERMS) else "launcher"
                candidates.append(
                    DiscoveredApp(
                        source="Ярлыки Windows",
                        title=title,
                        target=str(shortcut_path),
                        kind="file",
                        other_names=_default_other_names(title),
                        category=category,
                    )
                )
        return candidates

    def _discover_known_music_apps(self) -> list[DiscoveredApp]:
        candidates: list[DiscoveredApp] = []
        spotify_paths = [
            self.roots.app_data / "Spotify" / "Spotify.exe",
            self.roots.local_app_data / "Microsoft" / "WindowsApps" / "Spotify.exe",
        ]
        for spotify_path in spotify_paths:
            if spotify_path.exists():
                candidates.append(
                    DiscoveredApp(
                        source="Музыка",
                        title="Spotify",
                        target=str(spotify_path),
                        kind="file",
                        other_names=["спотифай", "спотик", "spotify", "музыка"],
                        category="music",
                    )
                )
                break

        yandex_paths = [
            self.roots.local_app_data / "Programs" / "YandexMusic" / "Яндекс Музыка.exe",
            self.roots.local_app_data / "Programs" / "YandexMusic" / "Yandex Music.exe",
        ]
        for yandex_path in yandex_paths:
            if yandex_path.exists():
                candidates.append(
                    DiscoveredApp(
                        source="Музыка",
                        title="Яндекс Музыка",
                        target=str(yandex_path),
                        kind="file",
                        other_names=["яндекс музыка", "музыка", "yandex music"],
                        category="music",
                    )
                )
                break

        candidates.append(
            DiscoveredApp(
                source="Музыка",
                title="Музыка Windows",
                target="mswindowsmusic:",
                kind="uri",
                other_names=["музыка", "плеер", "windows music"],
                category="music",
            )
        )
        return candidates

    def _discover_installed_known_apps(self) -> list[DiscoveredApp]:
        if winreg is None:
            return []
        candidates: list[DiscoveredApp] = []
        uninstall_roots = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        )
        for hive, key_path in uninstall_roots:
            try:
                with winreg.OpenKey(hive, key_path) as root_key:
                    subkey_count, _, _ = winreg.QueryInfoKey(root_key)
                    for index in range(subkey_count):
                        try:
                            subkey_name = winreg.EnumKey(root_key, index)
                            with winreg.OpenKey(root_key, subkey_name) as app_key:
                                candidate = self._candidate_from_uninstall_key(app_key)
                        except OSError:
                            continue
                        if candidate:
                            candidates.append(candidate)
            except OSError:
                continue
        return candidates

    def _candidate_from_uninstall_key(self, app_key) -> DiscoveredApp | None:
        title = _canonical_title(_query_registry_string(app_key, "DisplayName"))
        if not title:
            return None
        searchable = f"{title} {_query_registry_string(app_key, 'Publisher')}".casefold()
        if not _contains_known_term(searchable, (*KNOWN_LAUNCHER_TERMS, *KNOWN_MUSIC_TERMS)):
            return None

        target = _target_from_uninstall_key(app_key)
        if not target:
            return None
        category = "music" if _contains_known_term(searchable, KNOWN_MUSIC_TERMS) else "launcher"
        return DiscoveredApp(
            source="Установленные приложения",
            title=title,
            target=target,
            kind="file",
            other_names=_default_other_names(title),
            category=category,
        )


def _query_registry_string(key, value_name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(key, value_name)
    except OSError:
        return ""
    return str(value).strip()


def _target_from_uninstall_key(key) -> str:
    display_icon = _query_registry_string(key, "DisplayIcon")
    icon_target = _clean_executable_path(display_icon)
    if icon_target and Path(icon_target).exists():
        return icon_target

    install_location = _query_registry_string(key, "InstallLocation")
    if install_location:
        location = Path(install_location)
        if location.exists():
            for exe_path in location.glob("*.exe"):
                if exe_path.exists() and not _is_junk_target(str(exe_path)):
                    return str(exe_path)
    return ""


def _parse_steam_acf(manifest_path: Path) -> dict[str, str]:
    text = manifest_path.read_text(encoding="utf-8", errors="ignore")
    return {key.lower(): value for key, value in re.findall(r'"([^"]+)"\s+"([^"]*)"', text)}


def _contains_known_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _canonical_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title.strip())
    lower = cleaned.casefold()
    if "yandex" in lower and "music" in lower or "яндекс" in lower and "музык" in lower:
        return "Яндекс Музыка"
    if "apple" in lower and "music" in lower:
        return "Apple Music"
    if "soundcloud" in lower or "саундклауд" in lower:
        return "SoundCloud"
    if "minecraft" in lower or "майнкрафт" in lower:
        return "Minecraft Launcher"
    if "roblox" in lower or "роблокс" in lower:
        return "Roblox"
    if "ubisoft" in lower or "uplay" in lower or "юбисофт" in lower:
        return "Ubisoft Connect"
    if "battle.net" in lower or "battlenet" in lower or "blizzard" in lower:
        return "Battle.net"
    if lower in {"spotify"}:
        return "Spotify"
    if lower in {"steam"}:
        return "Steam"
    if lower in {"epic games launcher", "epic"}:
        return "Epic Games Launcher"
    return cleaned


def _default_other_names(title: str, *extra: str) -> list[str]:
    names = [title.strip(), title.casefold().strip(), *extra]
    names.extend(_natural_aliases_for_title(title))
    if "ё" in title:
        names.append(title.replace("ё", "е").casefold())
    if title.casefold().startswith("the "):
        names.append(title[4:].casefold())
    return _dedupe_strings(names)


def _natural_aliases_for_title(title: str) -> list[str]:
    normalized_title = re.sub(r"[\s_\-]+", " ", title.casefold()).strip()
    aliases: list[str] = []
    for title_tokens, natural_aliases in NATURAL_ALIAS_TEMPLATES:
        if any(token in normalized_title for token in title_tokens):
            aliases.extend(alias.casefold() for alias in natural_aliases)
    return aliases


def _stable_candidate_id(source: str, title: str, target: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "_", f"{source}_{title}").strip("_").casefold()
    checksum = hashlib.sha1(target.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"found_{slug}_{checksum}"


def _dedupe_candidates(candidates: list[DiscoveredApp]) -> list[DiscoveredApp]:
    by_key: dict[str, DiscoveredApp] = {}
    for candidate in candidates:
        title_key = _dedupe_title_key(candidate.title)
        target_key = candidate.target.casefold()
        key = title_key if title_key in by_key else f"{title_key}|{target_key}"
        existing = by_key.get(title_key) or by_key.get(key)
        if existing and _source_rank(existing.source) <= _source_rank(candidate.source):
            continue
        candidate.other_names = _dedupe_strings(candidate.other_names)
        if existing:
            by_key.pop(_dedupe_title_key(existing.title), None)
        by_key[title_key] = candidate
    return sorted(by_key.values(), key=lambda item: (_source_rank(item.source), item.title.casefold()))


def _dedupe_title_key(title: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", title.casefold()).strip()


def _source_rank(source: str) -> int:
    return {
        "Steam": 10,
        "Epic Games": 10,
        "Музыка": 15,
        "Ярлыки Windows": 40,
        "Установленные приложения": 60,
    }.get(source, 50)


def _is_user_facing_candidate(candidate: DiscoveredApp) -> bool:
    title = candidate.title.casefold()
    if not title:
        return False
    if any(term in title for term in JUNK_TITLE_TERMS):
        return False
    if _is_junk_target(candidate.target):
        return False
    return True


def _is_junk_target(target: str) -> bool:
    lower = target.casefold()
    return any(term in lower for term in JUNK_TARGET_TERMS)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _first_existing_path(paths: list[Path]) -> Path | None:
    for path in _unique_paths(paths):
        if path.exists():
            return path
    return None


def _clean_executable_path(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().strip('"')
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0]
    if cleaned.casefold().endswith(".exe") and Path(cleaned).exists() and not _is_junk_target(cleaned):
        return cleaned
    return ""


def _first_regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def target_from_file_url(value: str) -> str:
    if value.startswith("file:///"):
        return unquote(value[8:]).replace("/", "\\")
    if value.startswith("file://"):
        return unquote(value[7:]).replace("/", "\\")
    return value

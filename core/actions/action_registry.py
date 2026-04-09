from __future__ import annotations

import ctypes
import os
import re
import subprocess
import webbrowser
from typing import Iterable

from core.actions.launcher_discovery import DiscoveredApp, LauncherDiscovery
from core.models.action_models import ActionOutcome
from core.routing.text_rules import strip_leading_command_fillers


OPEN_VERBS = ("открой", "открыть", "запусти", "запустить", "включи", "включить")
MUSIC_WORDS = ("музыка", "музыку", "музычку", "музычка", "музычки", "music", "плеер", "плейлист")
EXACT_MUSIC_ALIASES = (
    ("яндекс", "yandex"),
    ("spotify", "спотифай", "спотик"),
    ("windows music", "музыка windows"),
)
QUICK_ACTION_IDS = ("youtube", "browser", "music", "steam", "discord")
QUICK_ACTION_LIMIT = 7
KNOWN_SHELL_FOLDERS = {
    "desktop": "shell:Desktop",
    "documents": "shell:Personal",
    "downloads": "shell:Downloads",
    "pictures": "shell:My Pictures",
    "videos": "shell:My Video",
    "music_folder": "shell:My Music",
}
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
OPEN_SEQUENCE_CONNECTOR_PATTERN = re.compile(r"^(?:[\s,.:;!?-]+|и\s+|а\s+ещ[её]\s+|потом\s+|по\s+)+", re.IGNORECASE)
SYSTEM_TARGET_IDS = {
    "system_settings",
    "system_explorer",
    "system_task_manager",
    "system_control_panel",
    "folder_desktop",
    "folder_documents",
    "folder_downloads",
    "folder_pictures",
    "folder_videos",
}
SYSTEM_ACTION_ALIASES: dict[str, tuple[str, ...]] = {
    "shutdown": (
        "выключи компьютер",
        "выключи пк",
        "выключи комп",
        "выключи систему",
        "выключить компьютер",
        "выключить пк",
        "выруби компьютер",
        "выруби пк",
        "выруби комп",
        "заверши работу",
        "shutdown",
    ),
    "restart": (
        "перезагрузи компьютер",
        "перезагрузи пк",
        "перезагрузи комп",
        "перезагрузи ноутбук",
        "перезагрузка",
        "перезапусти систему",
        "перезапусти компьютер",
        "restart",
        "reboot",
    ),
    "sleep": (
        "режим сна",
        "в сон",
        "усыпи компьютер",
        "усыпи пк",
        "усыпи комп",
        "переведи компьютер в сон",
        "переведи в сон",
        "отправь компьютер в сон",
        "sleep",
    ),
    "hibernate": (
        "гибернация",
        "в гибернацию",
        "отправь компьютер в гибернацию",
        "переведи компьютер в гибернацию",
        "усыпи компьютер надолго",
        "hibernate",
    ),
    "logoff": (
        "выйди из системы",
        "выйди из учетной записи",
        "выйди из учётной записи",
        "выход из системы",
        "разлогинь",
        "разлогинься",
        "логаут",
        "log off",
        "sign out",
        "logout",
    ),
    "lock": (
        "заблокируй экран",
        "заблокируй компьютер",
        "заблокируй пк",
        "блокируй экран",
        "локни экран",
        "lock screen",
        "lock workstation",
    ),
}
SYSTEM_ACTION_TITLES = {
    "shutdown": "Выключаю компьютер",
    "restart": "Перезагружаю компьютер",
    "sleep": "Перевожу компьютер в режим сна",
    "hibernate": "Перевожу компьютер в гибернацию",
    "logoff": "Выхожу из системы",
    "lock": "Блокирую экран",
}
SYSTEM_ACTION_CONFIRM_REQUIRED = {"shutdown", "restart", "sleep", "hibernate", "logoff"}
SYSTEM_ACTION_CONFIRM_PROMPTS = {
    "shutdown": "Подтвердите выключение: скажите «выключи компьютер подтверждаю».",
    "restart": "Подтвердите перезагрузку: скажите «перезагрузи компьютер подтверждаю».",
    "sleep": "Подтвердите режим сна: скажите «режим сна подтверждаю».",
    "hibernate": "Подтвердите гибернацию: скажите «гибернация подтверждаю».",
    "logoff": "Подтвердите выход из системы: скажите «выйди из системы подтверждаю».",
}
SYSTEM_POLITE_PREFIXES = ("пожалуйста ", "ну ", "давай ", "jarvis ", "джарвис ")


class ActionRegistry:
    VK_VOLUME_UP = 0xAF
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_MUTE = 0xAD

    def __init__(self, settings_service) -> None:
        self.settings = settings_service
        self.builtin_catalog = [
            {
                "id": "youtube",
                "title": "YouTube",
                "aliases": ["youtube", "ютуб", "ютубе", "ютюб", "ютубчик", "you tube"],
                "kind": "url",
                "target": "https://www.youtube.com",
                "category": "web",
            },
            {
                "id": "browser",
                "title": "Браузер",
                "aliases": ["браузер", "браузере", "browser", "chrome", "гугл", "гугле", "интернет"],
                "kind": "url",
                "target": "https://www.google.com",
                "category": "web",
            },
            {
                "id": "discord",
                "title": "Discord",
                "aliases": ["discord", "дискорд", "дискорде", "дискордик"],
                "kind": "uri",
                "target": "discord://",
                "category": "launcher",
            },
            {
                "id": "steam",
                "title": "Steam",
                "aliases": ["steam", "стим", "стиме", "стимчик", "с тим"],
                "kind": "uri",
                "target": "steam://open/main",
                "category": "launcher",
            },
            {
                "id": "music",
                "title": "Музыка",
                "aliases": ["музыка", "музыку", "музычку", "музычка", "music", "плеер"],
                "kind": "uri",
                "target": "mswindowsmusic:",
                "category": "music",
                "builtin_default": True,
            },
            {
                "id": "system_settings",
                "title": "Параметры Windows",
                "aliases": [
                    "параметры",
                    "настройки",
                    "настройки windows",
                    "настройки виндовс",
                    "параметры windows",
                    "параметры виндовс",
                    "windows settings",
                    "settings",
                ],
                "kind": "uri",
                "target": "ms-settings:",
                "category": "system",
            },
            {
                "id": "system_explorer",
                "title": "Проводник",
                "aliases": ["проводник", "проводнике", "explorer", "файлы", "файловый менеджер"],
                "kind": "uri",
                "target": "explorer.exe",
                "category": "system",
            },
            {
                "id": "system_task_manager",
                "title": "Диспетчер задач",
                "aliases": ["диспетчер задач", "task manager", "taskmgr"],
                "kind": "uri",
                "target": "taskmgr.exe",
                "category": "system",
            },
            {
                "id": "system_control_panel",
                "title": "Панель управления",
                "aliases": ["панель управления", "панель", "control panel", "control"],
                "kind": "uri",
                "target": "control.exe",
                "category": "system",
            },
            {
                "id": "folder_desktop",
                "title": "Рабочий стол",
                "aliases": ["рабочий стол", "desktop"],
                "kind": "shell",
                "target": "desktop",
                "category": "system",
            },
            {
                "id": "folder_documents",
                "title": "Документы",
                "aliases": ["документы", "documents", "папка документов", "папку документов"],
                "kind": "shell",
                "target": "documents",
                "category": "system",
            },
            {
                "id": "folder_downloads",
                "title": "Загрузки",
                "aliases": ["загрузки", "downloads", "папка загрузок", "папку загрузок"],
                "kind": "shell",
                "target": "downloads",
                "category": "system",
            },
            {
                "id": "folder_pictures",
                "title": "Изображения",
                "aliases": ["картинки", "изображения", "pictures", "фото"],
                "kind": "shell",
                "target": "pictures",
                "category": "system",
            },
            {
                "id": "folder_videos",
                "title": "Видео",
                "aliases": ["видео", "videos"],
                "kind": "shell",
                "target": "videos",
                "category": "system",
            },
        ]
        self.catalog = self._merged_catalog()
        self.discovery = LauncherDiscovery()

    def quick_actions(self) -> list[dict[str, str]]:
        pinned = [self._find_by_id(action_id) for action_id in self._pinned_command_ids()]
        curated: list[dict[str, str] | None] = []
        for action_id in QUICK_ACTION_IDS:
            if action_id == "music":
                curated.append(self._default_music_item())
                continue
            curated.append(self._find_by_id(action_id))
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in [*pinned, *curated]:
            if item is None:
                continue
            item_id = str(item["id"])
            if item_id in seen:
                continue
            if not self._is_safe_quick_action(item):
                continue
            seen.add(item_id)
            items.append(item)
            if len(items) >= QUICK_ACTION_LIMIT:
                break
        return [{"id": str(item["id"]), "title": str(item["title"])} for item in items]

    def app_catalog(self) -> list[dict[str, str]]:
        default_music_id = str(self.settings.get("default_music_app", "")).strip()
        pinned_ids = set(self._pinned_command_ids())
        return [
            {
                "id": str(item["id"]),
                "title": str(item["title"]),
                "aliases": ", ".join(item["aliases"]),
                "target": str(item["target"]),
                "custom": bool(item.get("custom", False)),
                "category": str(item.get("category", "app")),
                "section": self._catalog_section(item),
                "isDefaultMusic": str(item["id"]) == default_music_id,
                "isPinned": str(item["id"]) in pinned_ids,
                "canBeDefaultMusic": str(item.get("category", "")) == "music" and not item.get("builtin_default", False),
            }
            for item in self._user_visible_catalog()
        ]

    def find_items(self, text: str) -> list[dict[str, str]]:
        lower = text.casefold()
        target_text = self._strip_open_verb(text).casefold()
        exact_music = self._exact_music_item(target_text)
        if exact_music:
            return [exact_music]
        if self._looks_like_generic_music(target_text):
            default_music = self._default_music_item()
            return [default_music] if default_music else []

        found: list[dict[str, str]] = []
        for item in self.catalog:
            aliases = [str(alias).casefold() for alias in item.get("aliases", [])]
            if any(self._alias_matches(item, alias, target_text, lower) for alias in aliases):
                found.append(item)
        return found

    def resolve_open_command(self, command: str) -> tuple[list[dict[str, str]], str]:
        clean_command = strip_leading_command_fillers(command)
        target_text = self._strip_open_verb(clean_command).casefold()
        exact_music = self._exact_music_item(target_text)
        if exact_music:
            return [exact_music], ""
        requested_music = self._requested_known_music_target(target_text)
        if requested_music:
            return [], f"{requested_music} не найден. Добавьте приложение во вкладке «Приложения»."

        if self._looks_like_generic_music(target_text):
            default_music = self._default_music_item()
            if default_music:
                return [default_music], ""
            options = ", ".join(item["title"] for item in self._music_candidates(include_builtin=False))
            if options:
                return [], "Выберите основную музыку во вкладке «Приложения»."
            return [], "Музыкальное приложение не найдено. Добавьте его во вкладке «Приложения»."

        return self.find_items(target_text), ""

    def resolve_system_action(self, command: str) -> dict[str, object] | None:
        normalized = self._normalize_system_command(command)
        if not normalized:
            return None

        action = self._detect_system_action(normalized)
        if action:
            return {
                "action": action,
                "mode": "power",
                "title": SYSTEM_ACTION_TITLES[action],
                "detail": "Системная команда отправлена.",
                "requires_confirmation": action in SYSTEM_ACTION_CONFIRM_REQUIRED,
                "confirmation_prompt": SYSTEM_ACTION_CONFIRM_PROMPTS.get(action, ""),
            }

        if any(normalized.startswith(f"{verb} ") for verb in OPEN_VERBS):
            items, question = self.resolve_open_command(command)
            if question or len(items) != 1:
                return None

            item = items[0]
            if not self.is_system_item(item):
                return None

            return {
                "action": "open_target",
                "mode": "open",
                "title": f"Открываю {item['title']}",
                "detail": str(item.get("target", "")),
                "target": str(item.get("target", "")),
                "target_kind": str(item.get("kind", "file")),
                "item_id": str(item.get("id", "")),
            }

        items, question = self.resolve_open_command(normalized)
        if question or len(items) != 1:
            return None

        item = items[0]
        if not self.is_system_item(item):
            return None

        phrases, remainder = self.split_open_target_sequence(normalized)
        if remainder or len(phrases) != 1:
            return None

        return {
            "action": "open_target",
            "mode": "open",
            "title": f"Открываю {item['title']}",
            "detail": str(item.get("target", "")),
            "target": str(item.get("target", "")),
            "target_kind": str(item.get("kind", "file")),
            "item_id": str(item.get("id", "")),
        }

    def is_system_item(self, item: dict[str, str]) -> bool:
        item_id = str(item.get("id", "")).strip()
        category = str(item.get("category", "")).casefold()
        return category == "system" or item_id in SYSTEM_TARGET_IDS

    def can_resolve_open_target(self, text: str) -> bool:
        clean = self._consume_open_sequence_connectors(strip_leading_command_fillers(text))
        if not clean:
            return False
        return self._best_open_target_prefix(clean) is not None

    def split_open_target_sequence(self, text: str) -> tuple[list[str], str]:
        remaining = re.sub(r"\s+", " ", strip_leading_command_fillers(str(text or ""))).strip(" ,")
        phrases: list[str] = []
        while remaining:
            remaining = self._consume_open_sequence_connectors(remaining)
            if not remaining:
                break
            matched = self._best_open_target_prefix(remaining)
            if matched is None:
                break
            matched_phrase = matched.strip(" ,")
            if not matched_phrase:
                break
            phrases.append(matched_phrase)
            remaining = remaining[len(matched):].lstrip(" ,")
        return phrases, self._consume_open_sequence_connectors(remaining)

    def open_items(self, items: Iterable[dict[str, str]]) -> list[ActionOutcome]:
        outcomes: list[ActionOutcome] = []
        for item in items:
            try:
                self._open_target(str(item["kind"]), str(item["target"]))
                outcomes.append(ActionOutcome(True, f"Открываю {item['title']}", f"Запущено: {item['title']}"))
            except OSError as exc:
                outcomes.append(ActionOutcome(False, f"Не удалось открыть {item['title']}", str(exc)))
        return outcomes

    def test_item(self, app_id: str) -> ActionOutcome:
        item = self._find_by_id(app_id)
        if not item:
            return ActionOutcome(False, "Приложение не найдено", "Проверьте список приложений.")
        try:
            self._open_target(str(item["kind"]), str(item["target"]))
        except OSError as exc:
            return ActionOutcome(False, f"Не удалось запустить {item['title']}", str(exc))
        return ActionOutcome(True, f"Запускаю {item['title']}", f"Цель: {item['target']}")

    def _open_target(self, kind: str, target: str) -> None:
        if kind == "url":
            webbrowser.open(target)
            return
        if kind == "power":
            self._run_power_action(target)
            return
        if kind == "shell":
            shell_target = KNOWN_SHELL_FOLDERS.get(target, target)
            os.startfile(shell_target)  # type: ignore[attr-defined]
            return
        os.startfile(target)  # type: ignore[attr-defined]

    def _run_power_action(self, action: str) -> None:
        if os.name != "nt":
            raise OSError("power_actions_are_supported_only_on_windows")

        normalized = action.strip().casefold()
        if normalized == "lock":
            if not bool(ctypes.windll.user32.LockWorkStation()):
                raise OSError("lock_workstation_failed")
            return
        if normalized == "sleep":
            if not bool(ctypes.windll.powrprof.SetSuspendState(False, True, False)):
                raise OSError("sleep_failed")
            return
        if normalized == "hibernate":
            if not bool(ctypes.windll.powrprof.SetSuspendState(True, True, False)):
                raise OSError("hibernate_failed")
            return

        shutdown_commands = {
            "shutdown": ["shutdown", "/s", "/t", "0"],
            "restart": ["shutdown", "/r", "/t", "0"],
            "logoff": ["shutdown", "/l"],
        }
        command = shutdown_commands.get(normalized)
        if command is None:
            raise OSError(f"unknown_power_action:{action}")
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(
            getattr(subprocess, "DETACHED_PROCESS", 0)
        )
        subprocess.Popen(command, close_fds=True, creationflags=creationflags)  # noqa: S603

    def volume_up(self) -> ActionOutcome:
        self._press_volume_key(self.VK_VOLUME_UP)
        return ActionOutcome(True, "Прибавляю громкость", "Системная громкость увеличена")

    def volume_down(self) -> ActionOutcome:
        self._press_volume_key(self.VK_VOLUME_DOWN)
        return ActionOutcome(True, "Убавляю громкость", "Системная громкость снижена")

    def volume_mute(self) -> ActionOutcome:
        self._press_volume_key(self.VK_VOLUME_MUTE)
        return ActionOutcome(True, "Переключаю звук", "Системный звук переключён")

    def run_power_action(self, action: str, title: str) -> ActionOutcome:
        self._run_power_action(action)
        return ActionOutcome(
            True,
            title,
            "Системная команда отправлена.",
            status="sent_unverified",
        )

    def _press_volume_key(self, virtual_key: int) -> None:
        ctypes.windll.user32.keybd_event(virtual_key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(virtual_key, 0, 2, 0)

    def add_custom_app(self, title: str, target: str, aliases_input: str) -> None:
        aliases = self._aliases_from_input(title, aliases_input)
        self._append_custom_item(
            {
                "title": title.strip(),
                "aliases": aliases,
                "kind": self._infer_kind(target),
                "target": target.strip(),
                "custom": True,
                "category": self._infer_category(title, aliases),
            }
        )

    def update_custom_app(self, app_id: str, title: str, target: str, aliases_input: str) -> bool:
        custom_apps = list(self.settings.get("custom_apps", []))
        updated = False
        for item in custom_apps:
            if item.get("id") != app_id:
                continue
            aliases = self._aliases_from_input(title, aliases_input)
            item.update(
                {
                    "title": title.strip(),
                    "aliases": aliases,
                    "kind": self._infer_kind(target),
                    "target": target.strip(),
                    "custom": True,
                    "category": self._infer_category(title, aliases),
                }
            )
            updated = True
            break
        if not updated:
            return False
        self.settings.set("custom_apps", custom_apps)
        self.catalog = self._merged_catalog()
        return True

    def remove_custom_app(self, app_id: str) -> None:
        custom_apps = [item for item in self.settings.get("custom_apps", []) if item.get("id") != app_id]
        self.settings.set("custom_apps", custom_apps)
        self.catalog = self._merged_catalog()

    def discover_apps(self) -> list[dict[str, str]]:
        existing = self._existing_keys()
        candidates = []
        for candidate in self.discovery.discover():
            if self._candidate_exists(candidate, existing) or self._is_windows_music_candidate(candidate):
                continue
            candidates.append(candidate.to_dict())
        return candidates[:12]

    def scan_and_import_apps(self) -> dict[str, object]:
        existing = self._existing_keys()
        candidates = list(self.discovery.discover())
        imported: list[dict[str, str]] = []
        review: list[dict[str, str]] = []
        skipped = 0
        already_existing = 0

        for candidate in candidates:
            candidate_dict = candidate.to_dict()
            if self._candidate_exists(candidate, existing):
                already_existing += 1
                continue
            if self._is_windows_music_candidate(candidate):
                skipped += 1
                continue
            if self._can_auto_import(candidate):
                if self.add_discovered_app(candidate):
                    imported.append(candidate_dict)
                    existing = self._existing_keys()
                else:
                    skipped += 1
                continue
            review.append(candidate_dict)

        self._maybe_set_single_music_default()
        review_limited = review[:8]
        summary_titles = [item["title"] for item in imported[:8]]
        if len(imported) > 8:
            summary_titles.append(f"ещё {len(imported) - 8}")
        conflicts = self._music_conflicts()
        if summary_titles:
            summary = f"Найдено: {', '.join(summary_titles)}"
        elif review_limited:
            review_titles = ", ".join(item["title"] for item in review_limited[:6])
            summary = f"Найдено для проверки: {review_titles}"
        else:
            summary = "Новых безопасных приложений не найдено. Уже добавленное показано в категориях ниже."
        if conflicts:
            summary = f"{summary} Выберите основное музыкальное приложение в разделе «Музыка»."
        skipped_total = skipped + len(review)
        summary = (
            f"Добавлено: {len(imported)}, уже было: {already_existing}, "
            f"пропущено: {skipped_total}, конфликтов: {len(conflicts)}. {summary}"
        )
        return {
            "imported": imported,
            "review": review_limited,
            "conflicts": conflicts,
            "added": len(imported),
            "already_existing": already_existing,
            "skipped": skipped_total,
            "conflict_count": len(conflicts),
            "summary": summary,
        }

    def import_discovered_app(self, candidate: dict[str, str]) -> bool:
        title = candidate.get("title", "").strip()
        target = candidate.get("target", "").strip()
        if not title or not target:
            return False
        if self._already_exists(title, target):
            return False
        aliases = [part.strip().casefold() for part in candidate.get("aliases", "").split(",") if part.strip()]
        self._append_custom_item(
            {
                "title": title,
                "target": target,
                "aliases": aliases or [title.casefold()],
                "kind": candidate.get("kind") or self._infer_kind(target),
                "custom": True,
                "category": candidate.get("category") or self._infer_category(title, aliases),
            }
        )
        self._maybe_set_single_music_default()
        return True

    def add_discovered_app(self, candidate: DiscoveredApp) -> bool:
        return self.import_discovered_app(candidate.to_dict())

    def set_default_music_app(self, app_id: str) -> bool:
        item = self._find_by_id(app_id)
        if not item or item.get("category") != "music":
            return False
        self.settings.set("default_music_app", app_id)
        return True

    def set_pinned_commands(self, command_ids: list[str]) -> list[str]:
        normalized = [str(command_id).strip() for command_id in command_ids if str(command_id).strip()]
        self.settings.set_pinned_commands(normalized[:QUICK_ACTION_LIMIT])
        return self.settings.get_pinned_commands()

    def pin_command(self, command_id: str) -> list[str]:
        return self.settings.pin_command(command_id)

    def unpin_command(self, command_id: str) -> list[str]:
        return self.settings.unpin_command(command_id)

    def pinned_commands(self) -> list[dict[str, str]]:
        items = []
        for command_id in self.settings.get_pinned_commands():
            item = self._find_by_id(command_id)
            if item is not None:
                items.append({"id": str(item["id"]), "title": str(item["title"])})
        return items

    def _merged_catalog(self) -> list[dict[str, str]]:
        custom_apps = [self._normalize_catalog_item(item) for item in self.settings.get("custom_apps", [])]
        return [*self.builtin_catalog, *custom_apps]

    def _normalize_catalog_item(self, item: dict[str, str]) -> dict[str, str]:
        normalized = dict(item)
        title = str(normalized.get("title", "")).strip()
        aliases = self._normalized_aliases(title, normalized.get("aliases", []))
        normalized["aliases"] = aliases
        normalized.setdefault("category", self._infer_category(title, aliases))
        normalized.setdefault("kind", self._infer_kind(str(normalized.get("target", ""))))
        normalized.setdefault("custom", True)
        return normalized

    def _append_custom_item(self, item: dict[str, object]) -> None:
        custom_apps = list(self.settings.get("custom_apps", []))
        title = str(item.get("title", "")).strip()
        normalized_item = dict(item)
        normalized_item["aliases"] = self._normalized_aliases(title, normalized_item.get("aliases", []))
        custom_apps.append(
            {
                "id": f"custom_{len(custom_apps) + 1}",
                **normalized_item,
            }
        )
        self.settings.set("custom_apps", custom_apps)
        self.catalog = self._merged_catalog()

    def _already_exists(self, title: str, target: str) -> bool:
        title_key = title.casefold()
        target_key = target.casefold()
        return any(item["title"].casefold() == title_key or item["target"].casefold() == target_key for item in self.catalog)

    def _candidate_exists(self, candidate: DiscoveredApp, existing: set[tuple[str, str]]) -> bool:
        return (candidate.title.casefold(), candidate.target.casefold()) in existing or any(
            candidate.title.casefold() == title for title, _ in existing
        )

    def _existing_keys(self) -> set[tuple[str, str]]:
        return {(str(item["title"]).casefold(), str(item["target"]).casefold()) for item in self.catalog}

    def _find_by_id(self, app_id: str) -> dict[str, str] | None:
        for item in self.catalog:
            if item["id"] == app_id:
                return item
        return None

    def _infer_kind(self, target: str) -> str:
        lower = target.casefold()
        if lower.startswith("http://") or lower.startswith("https://"):
            return "url"
        if lower.endswith(".exe") or lower.endswith(".lnk") or os.path.exists(target):
            return "file"
        return "uri"

    def _infer_category(self, title: str, aliases: list[str]) -> str:
        haystack = " ".join([title, *aliases]).casefold()
        if any(word in haystack for word in MUSIC_WORDS) or any(word in haystack for group in EXACT_MUSIC_ALIASES for word in group):
            return "music"
        if "steam://" in haystack or "epic" in haystack:
            return "game"
        return "app"

    def _aliases_from_input(self, title: str, aliases_input: str) -> list[str]:
        aliases = [part.strip().casefold() for part in aliases_input.split(",") if part.strip()]
        aliases.append(title.strip().casefold())
        aliases.extend(self._natural_aliases_for_title(title))
        return list(dict.fromkeys(alias for alias in aliases if alias))

    def _strip_open_verb(self, command: str) -> str:
        lower = command.casefold().strip()
        for verb in OPEN_VERBS:
            prefix = f"{verb} "
            if lower.startswith(prefix):
                return command[len(prefix) :].strip()
        return command.strip()

    def _normalize_system_command(self, command: str) -> str:
        clean = strip_leading_command_fillers(str(command or ""))
        clean = re.sub(r"\s+", " ", clean.strip(" .,!?:;")).casefold()
        for prefix in SYSTEM_POLITE_PREFIXES:
            if clean.startswith(prefix):
                clean = clean[len(prefix) :].lstrip()
                break
        return clean

    def _detect_system_action(self, text: str) -> str | None:
        for action, aliases in SYSTEM_ACTION_ALIASES.items():
            if any(text == alias or text.startswith(f"{alias} ") for alias in aliases):
                return action
        return None

    def _looks_like_generic_music(self, target_text: str) -> bool:
        return any(word in target_text for word in MUSIC_WORDS) and not any(
            exact in target_text for group in EXACT_MUSIC_ALIASES for exact in group
        )

    def _exact_music_item(self, target_text: str) -> dict[str, str] | None:
        candidates = self._music_candidates(include_builtin=False)
        for item in candidates:
            if item.get("builtin_default") and any(exact in target_text for group in EXACT_MUSIC_ALIASES for exact in group):
                continue
            aliases = [str(alias).casefold() for alias in item.get("aliases", [])]
            title = str(item["title"]).casefold()
            if (
                "яндекс" in target_text
                and "яндекс" in title
                and any(token in target_text for token in ("музык", "music", "плеер"))
            ):
                return item
            if any(token in target_text for token in ("spotify", "спотифай", "спотик")) and "spotify" in title:
                return item
            if title and title != "музыка" and title in target_text:
                return item
            if any(alias and alias in target_text and not self._looks_like_generic_music(alias) for alias in aliases):
                return item
        return None

    def _requested_known_music_target(self, target_text: str) -> str:
        if any(token in target_text for token in ("spotify", "спотифай", "спотик")):
            return "Spotify"
        if "яндекс" in target_text and any(token in target_text for token in ("музык", "music", "плеер")):
            return "Яндекс Музыка"
        if any(token in target_text for token in ("apple music", "эпл музыка", "эпл мьюзик", "эйпл мьюзик")):
            return "Apple Music"
        if any(token in target_text for token in ("soundcloud", "саундклауд", "саунд клоуд")):
            return "SoundCloud"
        return ""

    def _alias_matches(self, item: dict[str, str], alias: str, target_text: str, full_text: str) -> bool:
        if not alias:
            return False
        generic_launcher_aliases = {"steam", "стим", "epic", "эпик"}
        target = str(item.get("target", "")).casefold()
        category = str(item.get("category", "")).casefold()
        if alias in generic_launcher_aliases and category == "game":
            if alias in {"steam", "стим"} and target_text in {"steam", "стим"} and target.startswith("steam://rungameid/"):
                return False
            if alias in {"epic", "эпик"} and target_text in {"epic", "epic games", "эпик", "эпик геймс"}:
                return False
        return self._alias_in_text(alias, full_text)

    def _alias_in_text(self, alias: str, text: str) -> bool:
        if not alias:
            return False
        if " " not in alias and "-" not in alias and len(alias) <= 4:
            return bool(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, flags=re.IGNORECASE))
        return alias in text

    def _alias_prefix_length(self, alias: str, text: str) -> int:
        candidate = text.strip()
        if not alias or not candidate:
            return 0
        if " " not in alias and "-" not in alias and len(alias) <= 4:
            match = re.match(rf"{re.escape(alias)}(?=$|[^\w])", candidate, flags=re.IGNORECASE)
            return len(match.group(0)) if match else 0
        if candidate.startswith(alias):
            if len(candidate) == len(alias):
                return len(alias)
            next_char = candidate[len(alias)]
            if next_char.isspace() or next_char in ",.:;!?-":
                return len(alias)
        return 0

    def _best_open_target_prefix(self, text: str) -> str | None:
        candidate = re.sub(r"\s+", " ", str(text or "").strip(" ,")).casefold()
        if not candidate:
            return None

        best_match = ""
        best_score = -1

        known_music_patterns = (
            r"^(яндекс\s+\w*музык\w*)(?=$|[\s,.:;!?-])",
            r"^((?:spotify|спотифай|спотик))(?=$|[\s,.:;!?-])",
            r"^((?:apple music|эпл музыка|эпл мьюзик|эйпл мьюзик))(?=$|[\s,.:;!?-])",
            r"^((?:soundcloud|саундклауд|саунд клоуд))(?=$|[\s,.:;!?-])",
        )
        for pattern in known_music_patterns:
            match = re.match(pattern, candidate, flags=re.IGNORECASE)
            if match:
                token = match.group(1)
                score = len(token) + 100
                if score > best_score:
                    best_match = token
                    best_score = score

        for word in sorted(MUSIC_WORDS, key=len, reverse=True):
            length = self._alias_prefix_length(word.casefold(), candidate)
            if length:
                score = length + 10
                if score > best_score:
                    best_match = candidate[:length]
                    best_score = score

        for item in self.catalog:
            aliases = [*item.get("aliases", []), item.get("title", "")]
            for alias in aliases:
                alias_value = str(alias).strip().casefold()
                if not alias_value:
                    continue
                length = self._alias_prefix_length(alias_value, candidate)
                if not length:
                    continue
                score = length
                if str(item.get("category", "")).casefold() == "system":
                    score += 5
                if score > best_score:
                    best_match = candidate[:length]
                    best_score = score

        return best_match or None

    def _consume_open_sequence_connectors(self, text: str) -> str:
        clean = re.sub(r"\s+", " ", str(text or "").strip(" ,"))
        while clean:
            updated = OPEN_SEQUENCE_CONNECTOR_PATTERN.sub("", clean, count=1)
            if updated == clean:
                break
            clean = updated.strip(" ,")
        return clean

    def _normalized_aliases(self, title: str, raw_aliases: object) -> list[str]:
        if isinstance(raw_aliases, str):
            aliases = [part.strip().casefold() for part in raw_aliases.split(",") if part.strip()]
        elif raw_aliases is None:
            aliases = []
        else:
            aliases = [str(alias).strip().casefold() for alias in raw_aliases if str(alias).strip()]
        aliases.append(title.strip().casefold())
        aliases.extend(self._natural_aliases_for_title(title))
        return list(dict.fromkeys(alias for alias in aliases if alias))

    def _natural_aliases_for_title(self, title: str) -> list[str]:
        normalized_title = re.sub(r"[\s_\-]+", " ", title.casefold()).strip()
        aliases: list[str] = []
        for title_tokens, natural_aliases in NATURAL_ALIAS_TEMPLATES:
            if any(token in normalized_title for token in title_tokens):
                aliases.extend(alias.casefold() for alias in natural_aliases)
        return aliases

    def _default_music_item(self) -> dict[str, str] | None:
        default_id = str(self.settings.get("default_music_app", "")).strip()
        if default_id:
            item = self._find_by_id(default_id)
            if item and not self._is_music_fallback_item(item):
                return item

        custom_music = self._music_candidates(include_builtin=False)
        if len(custom_music) == 1:
            return custom_music[0]
        if len(custom_music) > 1:
            return None
        return None

    def _music_candidates(self, include_builtin: bool) -> list[dict[str, str]]:
        candidates = [item for item in self.catalog if item.get("category") == "music"]
        if include_builtin:
            return candidates
        return [item for item in candidates if not item.get("builtin_default") and not self._is_music_fallback_item(item)]

    def _music_fallback_candidates(self) -> list[dict[str, str]]:
        return [item for item in self.catalog if item.get("category") == "music" and self._is_music_fallback_item(item)]

    def _maybe_set_single_music_default(self) -> None:
        if self.settings.get("default_music_app"):
            return
        custom_music = self._music_candidates(include_builtin=False)
        if len(custom_music) == 1:
            self.settings.set("default_music_app", custom_music[0]["id"])

    def _music_conflicts(self) -> list[dict[str, str]]:
        custom_music = self._music_candidates(include_builtin=False)
        if len(custom_music) <= 1 or self.settings.get("default_music_app"):
            return []
        return [{"id": str(item["id"]), "title": str(item["title"])} for item in custom_music]

    def _pinned_command_ids(self) -> list[str]:
        getter = getattr(self.settings, "get_pinned_commands", None)
        if getter is None:
            return []
        pinned = getter()
        if not isinstance(pinned, list):
            return []
        return [str(item).strip() for item in pinned if str(item).strip()]

    def _can_auto_import(self, candidate: DiscoveredApp) -> bool:
        if candidate.category == "music":
            return candidate.title != "Музыка Windows"
        return candidate.category in {"game", "launcher", "app"} and len(candidate.title) <= 42

    def _is_windows_music_candidate(self, candidate: DiscoveredApp) -> bool:
        title = candidate.title.casefold()
        target = candidate.target.casefold()
        return (
            target == "mswindowsmusic:"
            or "музыка windows" in title
            or "windows music" in title
            or "windows media player" in title
        )

    def _is_safe_quick_action(self, item: dict[str, str]) -> bool:
        title = str(item.get("title", ""))
        if len(title) > 28:
            return False
        return str(item.get("category", "")) in {"game", "music", "launcher", "web", "app", "system"}

    def _user_visible_catalog(self) -> list[dict[str, str]]:
        visible: list[dict[str, str]] = []
        for item in self.catalog:
            if self._is_hidden_user_music_fallback(item):
                continue
            visible.append(item)
        return visible

    def _catalog_section(self, item: dict[str, str]) -> str:
        target = str(item.get("target", "")).casefold()
        title = str(item.get("title", "")).casefold()
        category = str(item.get("category", "app"))
        aliases = " ".join(str(alias).casefold() for alias in item.get("aliases", []))

        if category == "music":
            return "music"
        if target.startswith("steam://") or title == "steam" or " steam" in f" {aliases} ":
            return "steam"
        if category == "launcher":
            return "launcher"
        if category == "web":
            return "web"
        return "app"

    def _is_hidden_user_music_fallback(self, item: dict[str, str]) -> bool:
        if item.get("category") != "music":
            return False
        if item.get("builtin_default"):
            return True
        return self._is_music_fallback_item(item) and bool(self._music_candidates(include_builtin=False))

    def _is_music_fallback_item(self, item: dict[str, str]) -> bool:
        title = str(item.get("title", "")).casefold()
        target = str(item.get("target", "")).casefold()
        aliases = " ".join(str(alias).casefold() for alias in item.get("aliases", []))
        return (
            target == "mswindowsmusic:"
            or "windows music" in title
            or "музыка windows" in title
            or "windows media player" in title
            or "windows media" in aliases
        )

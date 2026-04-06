from __future__ import annotations

import ctypes
import os
import webbrowser
from typing import Iterable

from core.models.action_models import ActionOutcome


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
                "aliases": ["youtube", "ютуб", "you tube"],
                "kind": "url",
                "target": "https://www.youtube.com",
            },
            {
                "id": "browser",
                "title": "Браузер",
                "aliases": ["браузер", "browser", "chrome", "гугл"],
                "kind": "url",
                "target": "https://www.google.com",
            },
            {
                "id": "discord",
                "title": "Discord",
                "aliases": ["discord", "дискорд"],
                "kind": "uri",
                "target": "discord://",
            },
            {
                "id": "steam",
                "title": "Steam",
                "aliases": ["steam", "стим"],
                "kind": "uri",
                "target": "steam://open/main",
            },
            {
                "id": "music",
                "title": "Музыка",
                "aliases": ["музыка", "music", "плеер"],
                "kind": "uri",
                "target": "mswindowsmusic:",
            },
        ]
        self.catalog = self._merged_catalog()

    def quick_actions(self) -> list[dict[str, str]]:
        return [{"id": item["id"], "title": item["title"]} for item in self.catalog]

    def app_catalog(self) -> list[dict[str, str]]:
        return [
            {
                "id": item["id"],
                "title": item["title"],
                "aliases": ", ".join(item["aliases"]),
                "target": item["target"],
            }
            for item in self.catalog
        ]

    def find_items(self, text: str) -> list[dict[str, str]]:
        lower = text.lower()
        found: list[dict[str, str]] = []
        for item in self.catalog:
            if any(alias in lower for alias in item["aliases"]):
                found.append(item)
        return found

    def open_items(self, items: Iterable[dict[str, str]]) -> list[ActionOutcome]:
        outcomes: list[ActionOutcome] = []
        for item in items:
            try:
                self._open_target(item["kind"], item["target"])
                outcomes.append(ActionOutcome(True, f"Открываю {item['title']}", f"Запущено: {item['title']}"))
            except OSError as exc:
                outcomes.append(ActionOutcome(False, f"Не удалось открыть {item['title']}", str(exc)))
        return outcomes

    def _open_target(self, kind: str, target: str) -> None:
        if kind == "url":
            webbrowser.open(target)
            return
        os.startfile(target)  # type: ignore[attr-defined]

    def volume_up(self) -> ActionOutcome:
        self._press_volume_key(self.VK_VOLUME_UP)
        return ActionOutcome(True, "Прибавляю громкость", "Системная громкость увеличена")

    def volume_down(self) -> ActionOutcome:
        self._press_volume_key(self.VK_VOLUME_DOWN)
        return ActionOutcome(True, "Убавляю громкость", "Системная громкость снижена")

    def volume_mute(self) -> ActionOutcome:
        self._press_volume_key(self.VK_VOLUME_MUTE)
        return ActionOutcome(True, "Переключаю mute", "Системный звук переключён")

    def _press_volume_key(self, virtual_key: int) -> None:
        ctypes.windll.user32.keybd_event(virtual_key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(virtual_key, 0, 2, 0)

    def add_custom_app(self, title: str, target: str, aliases_input: str) -> None:
        aliases = [part.strip().lower() for part in aliases_input.split(",") if part.strip()]
        custom_apps = list(self.settings.get("custom_apps", []))
        custom_apps.append(
            {
                "id": f"custom_{len(custom_apps) + 1}",
                "title": title.strip(),
                "aliases": aliases or [title.strip().lower()],
                "kind": self._infer_kind(target),
                "target": target.strip(),
                "custom": True,
            }
        )
        self.settings.set("custom_apps", custom_apps)
        self.catalog = self._merged_catalog()

    def remove_custom_app(self, app_id: str) -> None:
        custom_apps = [item for item in self.settings.get("custom_apps", []) if item.get("id") != app_id]
        self.settings.set("custom_apps", custom_apps)
        self.catalog = self._merged_catalog()

    def _merged_catalog(self) -> list[dict[str, str]]:
        custom_apps = list(self.settings.get("custom_apps", []))
        return [*self.builtin_catalog, *custom_apps]

    def _infer_kind(self, target: str) -> str:
        lower = target.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return "url"
        return "uri"

from __future__ import annotations

import webbrowser
from dataclasses import dataclass, field

from core.models.action_models import ActionOutcome
from core.pc_control.browser_control import BrowserControl
from core.pc_control.media_control import MediaControl


@dataclass(slots=True)
class PcControlService:
    action_registry: object
    media: MediaControl = field(init=False, repr=False)
    browser: BrowserControl = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.media = MediaControl()
        self.browser = BrowserControl()

    def open_items(self, items):
        if hasattr(self.action_registry, "open_items"):
            return self.action_registry.open_items(items)
        outcomes = []
        for item in items:
            target = str(item.get("target", ""))
            try:
                self._open_target(str(item.get("kind", "file")), target)
                outcomes.append(ActionOutcome(True, f"Открываю {item['title']}", f"Запущено: {item['title']}"))
            except OSError as exc:
                outcomes.append(ActionOutcome(False, f"Не удалось открыть {item['title']}", str(exc)))
        return outcomes

    def open_url(self, url: str, title: str) -> ActionOutcome:
        if self.browser.open_url(url):
            return ActionOutcome(True, f"Открываю {title}", f"Запущено: {title}")
        return ActionOutcome(False, f"Не удалось открыть {title}", url)

    def search_web(self, query: str) -> ActionOutcome:
        if self.browser.search(query):
            return ActionOutcome(True, f"Ищу в интернете: {query}", f"Запрос: {query}")
        return ActionOutcome(False, f"Не удалось найти: {query}", query)

    def play_pause(self) -> ActionOutcome:
        return self._media_outcome(
            self.media.play_pause(),
            "Команда паузы/воспроизведения отправлена",
            "Windows приняла медиа-клавишу, но плеер не подтверждает выполнение.",
            unverified=True,
        )

    def next_track(self) -> ActionOutcome:
        return self._media_outcome(
            self.media.next_track(),
            "Команда следующего трека отправлена",
            "Windows приняла медиа-клавишу, но плеер не подтверждает выполнение.",
            unverified=True,
        )

    def previous_track(self) -> ActionOutcome:
        return self._media_outcome(
            self.media.previous_track(),
            "Команда предыдущего трека отправлена",
            "Windows приняла медиа-клавишу, но плеер не подтверждает выполнение.",
            unverified=True,
        )

    def volume_up(self) -> ActionOutcome:
        return self._media_outcome(self.media.volume_up(), "Прибавляю громкость", "Системная громкость увеличена")

    def volume_down(self) -> ActionOutcome:
        return self._media_outcome(self.media.volume_down(), "Убавляю громкость", "Системная громкость снижена")

    def volume_mute(self) -> ActionOutcome:
        return self._media_outcome(self.media.mute(), "Переключаю звук", "Системный звук переключён")

    def _media_outcome(self, success: bool, title: str, detail: str, *, unverified: bool = False) -> ActionOutcome:
        if success:
            return ActionOutcome(True, title, detail, status="sent_unverified" if unverified else "")
        return ActionOutcome(
            False,
            f"Не удалось: {title}",
            "Windows не приняла системную медиа-команду. Действие не засчитано.",
        )

    def _open_target(self, kind: str, target: str) -> None:
        if kind == "url":
            webbrowser.open(target)
            return
        import os

        os.startfile(target)  # type: ignore[attr-defined]

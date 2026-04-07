from __future__ import annotations

import re
from dataclasses import dataclass

from core.models.action_models import ExecutionPlan, ExecutionStep


OPEN_VERBS = ("открой", "открыть", "запусти", "запустить", "включи", "включить")
SEARCH_VERBS = ("найди", "поиск", "поищи", "ищи")
MEDIA_PLAY_PAUSE = (
    "пауза",
    "play/pause",
    "play pause",
    "воспроизведение",
    "стоп музыка",
    "поставь на паузу",
    "останови",
    "продолжи",
    "продолжить",
    "играй",
)
MEDIA_NEXT = ("следующ", "следущ", "next", "вперёд", "вперед", "далее")
MEDIA_PREVIOUS = ("назад", "назат", "previous", "предыдущ", "обратно")
MEDIA_VOLUME_UP = (
    "прибавь",
    "громче",
    "увеличь громкость",
    "прибавить",
    "подними",
    "поднимай",
    "поднять громкость",
    "подними звук",
    "добавь звук",
    "сделай громче",
)
MEDIA_VOLUME_DOWN = (
    "убавь",
    "тише",
    "уменьши громкость",
    "убавить",
    "опусти",
    "снизь звук",
    "сделай тише",
)
MEDIA_MUTE = ("mute", "без звука", "выключи звук", "приглуши")

YANDEX_EDA_URL = "https://eda.yandex.ru/"
YANDEX_EDA_ALIASES = (
    "яндекс еда",
    "яндекс еду",
    "яндекс еды",
    "яндекс еде",
    "яндекс едой",
    "еда яндекс",
    "yandex food",
)


@dataclass(slots=True)
class IntentRouter:
    action_registry: object

    def build(self, command: str) -> ExecutionPlan | None:
        text = self._normalize(command)
        if not text:
            return None

        lower = text.casefold()
        if self._looks_like_search(lower):
            query = self._search_query(text)
            if not query:
                return ExecutionPlan(command=text, question="Что найти?")
            return ExecutionPlan(
                command=text,
                steps=[
                    ExecutionStep(
                        id=self._step_id(text, "search_web"),
                        kind="search_web",
                        title=f"Ищу в интернете: {query}",
                        detail=query,
                        payload={"query": query},
                    )
                ],
            )

        media_step = self._build_media_step(text, lower)
        if media_step is not None:
            return ExecutionPlan(command=text, steps=[media_step])

        if any(lower.startswith(f"{verb} ") for verb in OPEN_VERBS):
            if self._looks_like_yandex_eda(lower):
                return ExecutionPlan(
                    command=text,
                    steps=[
                        ExecutionStep(
                            id=self._step_id(text, "open_url"),
                            kind="open_url",
                            title="Открываю Яндекс Еду",
                            detail=YANDEX_EDA_URL,
                            payload={"url": YANDEX_EDA_URL, "title": "Яндекс Еда"},
                        )
                    ],
                )

            items, question = self._resolve_open_command(text)
            if question:
                resolver = "default_music" if "музыкой по умолчанию" in question else "missing_app"
                step_kind = "resolve_default_music" if resolver == "default_music" else "missing_app"
                return ExecutionPlan(
                    command=text,
                    steps=[
                        ExecutionStep(
                            id=self._step_id(text, step_kind),
                            kind=step_kind,
                            title=question,
                            detail=(
                                "Выберите приложение по умолчанию во вкладке «Приложения»."
                                if resolver == "default_music"
                                else "JARVIS не нашёл это приложение среди добавленных."
                            ),
                            status="needs_input",
                            supported=False,
                            payload={"resolver": resolver},
                        )
                    ],
                )
            if items:
                titles = [str(item.get("title", "")).strip() for item in items if str(item.get("title", "")).strip()]
                summary = titles[0] if len(titles) == 1 else ", ".join(titles)
                return ExecutionPlan(
                    command=text,
                    steps=[
                        ExecutionStep(
                            id=self._step_id(text, "open_items"),
                            kind="open_items",
                            title=f"Открываю {summary}",
                            detail=summary,
                            payload={"items": items},
                        )
                    ],
                )
            return ExecutionPlan(command=text, question="Что открыть?")

        return None

    def _build_media_step(self, text: str, lower: str) -> ExecutionStep | None:
        if self._matches_any(lower, MEDIA_PLAY_PAUSE):
            return self._step(text, "media_play_pause", "Переключаю воспроизведение")
        if self._matches_any(lower, MEDIA_NEXT):
            return self._step(text, "media_next", "Следующий трек")
        if self._matches_any(lower, MEDIA_PREVIOUS):
            return self._step(text, "media_previous", "Предыдущий трек")
        if self._matches_any(lower, MEDIA_MUTE):
            return self._step(text, "media_mute", "Переключаю звук")
        if self._matches_any(lower, MEDIA_VOLUME_UP):
            return self._step(text, "volume_up", "Прибавляю громкость")
        if self._matches_any(lower, MEDIA_VOLUME_DOWN):
            return self._step(text, "volume_down", "Убавляю громкость")
        return None

    def _resolve_open_command(self, command: str) -> tuple[list[dict[str, str]], str]:
        if hasattr(self.action_registry, "resolve_open_command"):
            return self.action_registry.resolve_open_command(command)
        return self.action_registry.find_items(command), ""

    def _search_query(self, text: str) -> str:
        query = text.casefold()
        query = re.sub(r"^(найди|поищи|ищи|поиск)\s+(в интернете\s+|в сети\s+|в браузере\s+)?", "", query).strip()
        query = re.sub(r"^(в интернете|в сети|в браузере)\s+", "", query).strip()
        return query.strip(" ,.")

    def _looks_like_search(self, lower: str) -> bool:
        return any(lower.startswith(f"{verb} ") for verb in SEARCH_VERBS) or lower.startswith("найди в интернете")

    def _looks_like_yandex_eda(self, lower: str) -> bool:
        return any(alias in lower for alias in YANDEX_EDA_ALIASES)

    def _matches_any(self, lower: str, tokens: tuple[str, ...]) -> bool:
        return any(token in lower for token in tokens)

    def _step(self, text: str, kind: str, title: str) -> ExecutionStep:
        return ExecutionStep(
            id=self._step_id(text, kind),
            kind=kind,
            title=title,
        )

    def _step_id(self, text: str, kind: str) -> str:
        safe = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", "_", text.casefold()).strip("_")
        return f"{kind}:{safe[:48] or 'command'}"

    def _normalize(self, command: str) -> str:
        return re.sub(r"\s+", " ", command.strip())

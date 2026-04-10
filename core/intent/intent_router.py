from __future__ import annotations

import re
from dataclasses import dataclass

from core.models.action_models import ExecutionPlan, ExecutionStep
from core.routing.text_rules import strip_leading_command_fillers


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
POWER_ACTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "lock",
        (
            "заблокируй экран",
            "заблокируй компьютер",
            "заблокируй пк",
            "заблокируй ноутбук",
            "блокируй экран",
            "lock screen",
        ),
        "Блокирую экран",
    ),
    (
        "restart",
        (
            "перезагрузи компьютер",
            "перезагрузи пк",
            "перезагрузи ноутбук",
            "перезагрузи",
            "перезапусти компьютер",
            "restart computer",
            "restart pc",
        ),
        "Перезагружаю компьютер",
    ),
    (
        "shutdown",
        (
            "выключи компьютер",
            "выключи пк",
            "выключи ноутбук",
            "заверши работу",
            "отключи компьютер",
            "shutdown computer",
            "shutdown pc",
        ),
        "Выключаю компьютер",
    ),
    (
        "sleep",
        (
            "усыпи компьютер",
            "усыпи пк",
            "переведи компьютер в сон",
            "переведи в сон",
            "отправь компьютер в сон",
            "спящий режим",
        ),
        "Перевожу компьютер в сон",
    ),
    (
        "hibernate",
        (
            "гибернация",
            "отправь компьютер в гибернацию",
            "переведи компьютер в гибернацию",
            "усыпи компьютер надолго",
        ),
        "Перевожу компьютер в гибернацию",
    ),
    (
        "logoff",
        (
            "выйди из системы",
            "выйди из учетной записи",
            "выйди из учётной записи",
            "выход из системы",
            "log off",
            "sign out",
        ),
        "Выхожу из системы",
    ),
)

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

POWER_CONFIRM_REQUIRED: set[str] = set()
POWER_ALIASES: dict[str, tuple[str, ...]] = {
    "shutdown": (
        "выключи компьютер",
        "выключи пк",
        "выключи систему",
        "выключить компьютер",
        "выключить пк",
        "заверши работу",
        "заверши работу",
        "shutdown",
    ),
    "restart": (
        "перезагрузи компьютер",
        "перезагрузи пк",
        "перезагрузи компьютер",
        "перезагрузи пк",
        "перезагрузка",
        "перезапусти систему",
        "restart",
        "reboot",
    ),
    "sleep": (
        "режим сна",
        "в сон",
        "усыпи компьютер",
        "усыпи пк",
        "sleep",
    ),
    "hibernate": (
        "гибернация",
        "в гибернацию",
        "hibernate",
    ),
    "logoff": (
        "выйди из системы",
        "выход из системы",
        "выйти из системы",
        "разлогинь",
        "logoff",
        "logout",
    ),
    "lock": (
        "заблокируй экран",
        "заблокируй компьютер",
        "заблокируй пк",
        "блокировка экрана",
        "lock screen",
        "lock workstation",
    ),
}

POWER_TITLES = {
    "shutdown": "Выключаю компьютер",
    "restart": "Перезагружаю компьютер",
    "sleep": "Перевожу компьютер в режим сна",
    "hibernate": "Перевожу компьютер в гибернацию",
    "logoff": "Выхожу из системы",
    "lock": "Блокирую экран",
}

POWER_CONFIRM_PROMPTS = {
    "shutdown": "Подтвердите выключение: скажите «выключи компьютер подтверждаю».",
    "restart": "Подтвердите перезагрузку: скажите «перезагрузи компьютер подтверждаю».",
    "sleep": "Подтвердите режим сна: скажите «режим сна подтверждаю».",
    "hibernate": "Подтвердите гибернацию: скажите «гибернация подтверждаю».",
    "logoff": "Подтвердите выход из системы: скажите «выйди из системы подтверждаю».",
}


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

        power_plan = self._build_power_plan(text, lower)
        if power_plan is not None:
            return power_plan

        builtin_system_plan = self._build_builtin_system_plan(text, lower)
        if builtin_system_plan is not None:
            return builtin_system_plan

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
                resolver = "default_music" if "музыкой по умолчанию" in question.casefold() else "missing_app"
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
            if items and not self._open_command_is_confident(text, items):
                return ExecutionPlan(command=text, question="Что открыть?")
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

    def _build_builtin_system_plan(self, text: str, lower: str) -> ExecutionPlan | None:
        if any(lower.startswith(f"{verb} ") for verb in OPEN_VERBS):
            return None
        resolver = getattr(self.action_registry, "resolve_open_command", None)
        if not callable(resolver):
            return None

        items, question = resolver(text)
        if question or len(items) != 1:
            return None

        item = items[0]
        item_id = str(item.get("id", "")).strip()
        if not (item_id.startswith("system_") or item_id.startswith("folder_")):
            return None

        splitter = getattr(self.action_registry, "split_open_target_sequence", None)
        if callable(splitter):
            phrases, remainder = splitter(text)
            if remainder or len(phrases) != 1:
                return None

        return ExecutionPlan(
            command=text,
            steps=[
                ExecutionStep(
                    id=self._step_id(text, "open_items"),
                    kind="open_items",
                    title=f"Открываю {item.get('title', text)}",
                    detail=str(item.get("target", "")),
                    payload={
                        "items": [
                            {
                                "id": item_id,
                                "title": str(item.get("title", text)),
                                "kind": str(item.get("kind", "file")),
                                "target": str(item.get("target", "")),
                            }
                        ]
                    },
                )
            ],
        )

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

    def _build_power_step(self, text: str, lower: str) -> ExecutionStep | None:
        clean = lower.strip()
        for action, phrases, title in POWER_ACTIONS:
            if any(clean == phrase or clean.startswith(f"{phrase} ") for phrase in phrases):
                return ExecutionStep(
                    id=self._step_id(text, f"power_{action}"),
                    kind="power_action",
                    title=title,
                    detail="Системная команда отправлена.",
                    payload={"action": action, "title": title},
                )
        return None

    def _build_power_plan(self, text: str, lower: str) -> ExecutionPlan | None:
        normalized = self._strip_polite_prefix(lower.strip(" .,!?:;"))
        action = self._detect_power_action(normalized)
        if action is None:
            return None
        title = POWER_TITLES[action]
        step = ExecutionStep(
            id=self._step_id(text, "power_action"),
            kind="power_action",
            title=title,
            detail="Системная команда отправлена.",
            payload={"action": action, "title": title},
        )
        return ExecutionPlan(command=text, steps=[step])

    def _detect_power_action(self, lower: str) -> str | None:
        for action, aliases in POWER_ALIASES.items():
            if any(lower.startswith(alias) for alias in aliases):
                return action
        return None

    def _strip_polite_prefix(self, lower: str) -> str:
        for prefix in ("пожалуйста ", "ну ", "jarvis ", "джарвис "):
            if lower.startswith(prefix):
                return lower[len(prefix) :].lstrip()
        return lower

    def _resolve_open_command(self, command: str) -> tuple[list[dict[str, str]], str]:
        if hasattr(self.action_registry, "resolve_open_command"):
            return self.action_registry.resolve_open_command(command)
        return self.action_registry.find_items(command), ""

    def _open_command_is_confident(self, command: str, items: list[dict[str, str]]) -> bool:
        target_text = self._strip_open_verb(command)
        splitter = getattr(self.action_registry, "split_open_target_sequence", None)
        if callable(splitter):
            phrases, remainder = splitter(target_text)
            if remainder.strip():
                return False
            if len(phrases) != len(items):
                return False
            return bool(phrases)
        return len(items) == 1

    def _strip_open_verb(self, command: str) -> str:
        text = self._normalize(command)
        lower = text.casefold()
        for verb in OPEN_VERBS:
            prefix = f"{verb} "
            if lower.startswith(prefix):
                return text[len(verb) :].lstrip()
        return text

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
        normalized = lower.strip()
        return any(
            normalized.startswith(token)
            or normalized.startswith(f"и {token}")
            or normalized.startswith(f"а {token}")
            for token in tokens
        )

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
        clean = strip_leading_command_fillers(command)
        return re.sub(r"\s+", " ", clean.strip())

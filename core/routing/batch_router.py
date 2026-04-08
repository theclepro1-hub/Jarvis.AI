from __future__ import annotations

import re


OPEN_VERBS = ("открой", "открыть", "запусти", "запустить", "включи", "включить")
SEARCH_VERBS = ("найди", "поищи", "ищи", "поиск")
NON_TARGET_START_TOKENS = ("как", "что", "почему", "зачем", "когда", "кто", "где", "объясни", "помоги")
MEDIA_ACTION_PREFIXES = (
    "прибавь",
    "убавь",
    "подними",
    "поднимай",
    "сделай",
    "добавь",
    "снизь",
    "пауза",
    "стоп",
    "останови",
    "продолжи",
    "играй",
    "следующее",
    "следующая",
    "следущая",
    "следующий",
    "следущий",
    "далее",
    "назад",
    "назат",
    "обратно",
    "предыдущее",
    "предыдущая",
    "предыдущий",
    "mute",
)
SHORT_ACTION_PREFIXES = (*MEDIA_ACTION_PREFIXES, *OPEN_VERBS, *SEARCH_VERBS)
ACTION_START_PATTERN = re.compile(
    r"(?<!\S)("
    + "|".join(re.escape(word) for word in sorted(SHORT_ACTION_PREFIXES, key=len, reverse=True))
    + r")(?=\s|$)",
    re.IGNORECASE,
)


class BatchRouter:
    def __init__(self, action_registry) -> None:
        self.action_registry = action_registry

    def split(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return []

        segments = [segment.strip(" ,") for segment in re.split(r"[.!?;,\n]+", normalized) if segment.strip(" ,")]
        expanded: list[str] = []
        for segment in segments:
            if self._starts_with_search(segment):
                expanded.extend(self._split_search_segment(segment))
                continue
            for action_segment in self._split_by_action_starts(segment):
                expanded.extend(self._expand_segment(action_segment))
        inherited = self._apply_open_verb_inheritance(expanded)
        return inherited or [normalized]

    def _starts_with_search(self, segment: str) -> bool:
        lower = segment.casefold().strip()
        return any(lower.startswith(f"{verb} ") for verb in SEARCH_VERBS)

    def _split_search_segment(self, segment: str) -> list[str]:
        pattern = re.compile(
            r"\s+(?:и|потом|а ещё|а еще)\s+(?=(?:"
            + "|".join(re.escape(word) for word in sorted(SHORT_ACTION_PREFIXES, key=len, reverse=True))
            + r")(?=\s|$))",
            re.IGNORECASE,
        )
        parts = [self._strip_connectors(part) for part in pattern.split(segment) if self._strip_connectors(part)]
        return parts or [self._strip_connectors(segment)]

    def _split_by_action_starts(self, segment: str) -> list[str]:
        matches = list(ACTION_START_PATTERN.finditer(segment.casefold()))
        if len(matches) <= 1:
            return [self._strip_connectors(segment)]

        parts: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(segment)
            part = self._strip_connectors(segment[start:end])
            if part:
                parts.append(part)
        return parts or [self._strip_connectors(segment)]

    def _expand_segment(self, segment: str) -> list[str]:
        segment = self._strip_connectors(segment)
        lower = segment.casefold()
        for verb in OPEN_VERBS:
            prefix = f"{verb} "
            if lower.startswith(prefix):
                tail = segment[len(prefix) :].strip()
                parts = [part.strip() for part in re.split(r"\s+и\s+", tail) if part.strip()]
                if len(parts) > 1 and all(not self._looks_like_short_action(part.casefold()) for part in parts):
                    return [f"{verb} {part}" for part in parts]

        if " и " not in lower:
            return [segment]

        parts = [part.strip() for part in re.split(r"\s+и\s+", segment) if part.strip()]
        if len(parts) <= 1:
            return [segment]

        if self._looks_like_short_action(parts[0].casefold()):
            first, rest = segment.split(" и ", 1)
            return [first.strip(), *self._expand_segment(rest.strip())]

        expanded = [parts[0]]
        for part in parts[1:]:
            if self._looks_like_short_action(part.casefold()):
                expanded.append(part)
            else:
                expanded[-1] = f"{expanded[-1]} и {part}"
        return expanded

    def _looks_like_short_action(self, text: str) -> bool:
        return text.startswith(SHORT_ACTION_PREFIXES) or any(token in text for token in ("громче", "тише", "mute"))

    def _strip_connectors(self, text: str) -> str:
        clean = re.sub(r"\s+", " ", text.strip(" ,"))
        clean = re.sub(r"^(и|а ещё|а еще|потом)\s+", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s+(и|а ещё|а еще|потом)$", "", clean, flags=re.IGNORECASE)
        return clean.strip(" ,")

    def _apply_open_verb_inheritance(self, commands: list[str]) -> list[str]:
        """
        Keep one open verb for following object fragments until a new action starts.
        Example: "открой steam, яндекс музыку и прибавь громкость"
        -> ["открой steam", "открой яндекс музыку", "прибавь громкость"].
        """
        inherited: list[str] = []
        carry_open_verb = ""
        for command in commands:
            clean = self._strip_connectors(command)
            if not clean:
                continue

            open_verb = self._leading_open_verb(clean)
            if open_verb:
                carry_open_verb = open_verb
                inherited.append(clean)
                continue

            lower = clean.casefold()
            starts_action = self._starts_with_action(lower)

            if carry_open_verb and not starts_action and self._looks_like_open_target(clean):
                inherited.append(f"{carry_open_verb} {clean}")
                continue

            inherited.append(clean)
            if starts_action:
                carry_open_verb = ""

        return inherited

    def _starts_with_action(self, text: str) -> bool:
        return bool(ACTION_START_PATTERN.match(text.strip()))

    def _leading_open_verb(self, text: str) -> str:
        stripped = text.strip()
        lower = stripped.casefold()
        for verb in OPEN_VERBS:
            prefix = f"{verb} "
            if lower.startswith(prefix):
                return stripped.split(" ", 1)[0]
        return ""

    def _looks_like_open_target(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        first_token = stripped.casefold().split(" ", 1)[0]
        return first_token not in NON_TARGET_START_TOKENS

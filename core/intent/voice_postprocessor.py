from __future__ import annotations

import re
from dataclasses import dataclass

from core.routing.text_rules import normalize_text, strip_leading_command_fillers


OPEN_VERBS = ("открой", "открыть", "запусти", "запустить", "включи", "включить")
FOLLOWUP_ACTION_VERBS = (
    "прибавь",
    "убавь",
    "подними",
    "поднимай",
    "сделай",
    "найди",
    "поищи",
    "ищи",
    "поиск",
    "напомни",
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
    "mute",
)

NOISY_OPEN_PREFIXES = {
    "откр",
    "откры",
    "откро",
    "открь",
    "откри",
    "отрой",
    "окрой",
    "сотру",
    "сотри",
    "сорту",
    "сокрыт",
}
NOISY_VOLUME_REPLACEMENTS = (
    ("погромче", "громче"),
    ("по громче", "громче"),
    ("потише", "тише"),
    ("по тише", "тише"),
)


@dataclass(slots=True)
class VoicePostProcessResult:
    original: str
    normalized: str
    changed: bool


class VoiceCommandPostProcessor:
    def __init__(self, action_registry) -> None:
        self.action_registry = action_registry
        self._followup_pattern = re.compile(
            r"\s+и\s+(?=(" + "|".join(re.escape(token) for token in FOLLOWUP_ACTION_VERBS) + r")(?=\s|$))",
            re.IGNORECASE,
        )

    def normalize(self, text: str) -> VoicePostProcessResult:
        original = normalize_text(text)
        if not original:
            return VoicePostProcessResult(original="", normalized="", changed=False)
        normalized = self._normalize_noisy_transcript(original)
        normalized = self._normalize_open_multi_target(normalized)
        normalized = normalize_text(normalized)
        return VoicePostProcessResult(original=original, normalized=normalized, changed=(normalized != original))

    def _normalize_noisy_transcript(self, text: str) -> str:
        normalized = strip_leading_command_fillers(text)
        normalized = self._normalize_volume_inflections(normalized)
        normalized = self._normalize_open_prefix_fragment(normalized)
        return normalized

    def _normalize_volume_inflections(self, text: str) -> str:
        normalized = text
        for source, target in NOISY_VOLUME_REPLACEMENTS:
            normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized, flags=re.IGNORECASE)
        return normalized

    def _normalize_open_prefix_fragment(self, text: str) -> str:
        parts = text.split(" ")
        if not parts:
            return text
        first = parts[0].casefold()
        if first in {"открой", "открыть"}:
            return text
        if first in NOISY_OPEN_PREFIXES:
            parts[0] = "открой"
            return " ".join(parts)
        return text

    def _normalize_open_multi_target(self, text: str) -> str:
        lower = text.casefold()
        verb = ""
        for token in OPEN_VERBS:
            prefix = f"{token} "
            if lower.startswith(prefix):
                verb = text.split(" ", 1)[0]
                break
        if not verb:
            return text

        if " и " in text and "," in text:
            return text

        tail = text[len(verb) :].strip()
        if not tail:
            return text

        boundary = self._followup_pattern.search(tail.casefold())
        if boundary is not None:
            object_chunk = tail[: boundary.start()].strip()
            suffix = tail[boundary.start() :].strip()
        else:
            object_chunk = tail.strip()
            suffix = ""

        if not object_chunk or "," in object_chunk or " и " in object_chunk:
            return text

        words = [part for part in object_chunk.split(" ") if part]
        if len(words) < 2:
            return text

        split_with_registry = getattr(self.action_registry, "split_open_target_sequence", None)
        if callable(split_with_registry):
            phrases, remainder = split_with_registry(object_chunk)
            normalized_phrases = [self._clean_mention(phrase) for phrase in phrases]
            normalized_phrases = [phrase for phrase in normalized_phrases if phrase]
            if normalized_phrases and remainder and self._looks_like_followup_action(remainder):
                rebuilt = f"{verb} {' и '.join(normalized_phrases)} и {remainder}"
                if suffix:
                    rebuilt = f"{rebuilt} {suffix}"
                return rebuilt
            if len(normalized_phrases) >= 2 and not remainder:
                rebuilt = f"{verb} {' и '.join(normalized_phrases)}"
                if suffix:
                    rebuilt = f"{rebuilt} {suffix}"
                return rebuilt

        items, question = self.action_registry.resolve_open_command(f"{verb} {object_chunk}")
        if question or len(items) < 2:
            return text

        mentions = self._extract_mentions(object_chunk, items)
        if len(mentions) < 2:
            return text

        rebuilt = f"{verb} {' и '.join(mentions)}"
        if suffix:
            rebuilt = f"{rebuilt} {suffix}"
        return rebuilt

    def _extract_mentions(self, chunk: str, items: list[dict[str, str]]) -> list[str]:
        source = chunk
        lower_chunk = source.casefold()
        spans: list[tuple[int, int, str]] = []
        used_ranges: list[tuple[int, int]] = []
        for item in items:
            candidates = self._item_candidates(item)
            match = self._best_candidate_span(lower_chunk, candidates)
            if match is None:
                continue
            start, end = match
            if any(not (end <= used_start or start >= used_end) for used_start, used_end in used_ranges):
                continue
            used_ranges.append((start, end))
            spans.append((start, end, source[start:end]))

        spans.sort(key=lambda span: span[0])
        if len(spans) >= 2:
            return [self._clean_mention(text) for _start, _end, text in spans]

        # Fallback: if we confidently detected multiple app items but not textual spans,
        # split by words to keep one-verb-many-objects structure for voice parser.
        words = [word for word in source.split(" ") if word]
        if len(words) >= 2:
            return [words[0], " ".join(words[1:])]
        return []

    def _item_candidates(self, item: dict[str, str]) -> list[str]:
        raw = [str(item.get("title", "")).strip(), *[str(alias).strip() for alias in item.get("aliases", [])]]
        unique = [value.casefold() for value in raw if value]
        # longest first so "яндекс музыка" is preferred over "музыка"
        return sorted(set(unique), key=len, reverse=True)

    def _best_candidate_span(self, lower_chunk: str, candidates: list[str]) -> tuple[int, int] | None:
        for candidate in candidates:
            index = lower_chunk.find(candidate)
            if index >= 0:
                return index, index + len(candidate)
        return None

    def _clean_mention(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip(" ,"))

    def _looks_like_followup_action(self, text: str) -> bool:
        lower = normalize_text(text).casefold()
        if not lower:
            return False
        return any(lower.startswith(token) for token in FOLLOWUP_ACTION_VERBS)

from __future__ import annotations

import re


OPEN_VERBS = ("открой", "открыть", "запусти", "запустить", "включи", "включить")
SHORT_ACTION_PREFIXES = ("прибавь", "убавь", "сделай", "вруби", "поставь", "открой", "запусти")


class BatchRouter:
    def __init__(self, action_registry) -> None:
        self.action_registry = action_registry

    def split(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return []

        segments = [
            segment.strip(" ,")
            for segment in re.split(r"[.!?;]+", normalized)
            if segment.strip(" ,")
        ]
        expanded: list[str] = []
        for segment in segments:
            expanded.extend(self._expand_segment(segment))
        return expanded or [normalized]

    def _expand_segment(self, segment: str) -> list[str]:
        lower = segment.lower()
        for verb in OPEN_VERBS:
            if lower.startswith(f"{verb} "):
                tail = segment[len(verb) :].strip()
                parts = [part.strip() for part in re.split(r"\s+и\s+", tail) if part.strip()]
                if len(parts) > 1 and all(not self._looks_like_short_action(part.lower()) for part in parts):
                    return [f"{verb} {part}" for part in parts]

        if " и " not in lower:
            return [segment]

        parts = [part.strip() for part in re.split(r"\s+и\s+", segment) if part.strip()]
        if len(parts) <= 1:
            return [segment]

        expanded = [parts[0]]
        for part in parts[1:]:
            if self._looks_like_short_action(part.lower()):
                expanded.append(part)
            else:
                expanded[-1] = f"{expanded[-1]} и {part}"
        return expanded

    def _looks_like_short_action(self, text: str) -> bool:
        return text.startswith(SHORT_ACTION_PREFIXES) or any(
            token in text for token in ("громче", "тише", "mute")
        )

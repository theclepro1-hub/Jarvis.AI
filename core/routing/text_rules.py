from __future__ import annotations

import re


WAKE_PREFIX_ALIASES = (
    "гарви с",
    "джарвис",
    "жарвис",
    "джервис",
    "джарвес",
    "джарис",
    "гарвис",
    "jarvis",
)

STRICT_WAKE_ALIASES = (
    "джарвис",
    "жарвис",
    "джервис",
    "jarvis",
)

COMMAND_FRAGMENT_TOKENS = (
    "открой",
    "открыть",
    "включи",
    "включить",
    "запусти",
    "запустить",
    "найди",
    "поищи",
    "ищи",
    "поиск",
    "напомни",
    "сделай",
    "прибавь",
    "убавь",
    "подними",
    "поднимай",
    "закрой",
    "сверни",
)

OPEN_COMMAND_TOKENS = ("открой", "открыть", "запусти", "запустить")
ENABLE_COMMAND_TOKENS = ("включи", "включить")
SEARCH_COMMAND_TOKENS = ("найди", "поищи", "ищи", "поиск")
REMINDER_COMMAND_TOKENS = ("напомни",)

CONVERSATION_PREFIXES = (
    "привет",
    "здравствуй",
    "здравствуйте",
    "как дела",
    "что умеешь",
    "что ты умеешь",
    "что можешь",
    "что ты можешь",
    "объясни",
    "помоги",
    "расскажи",
    "в чём разница",
    "в чем разница",
    "как лучше",
    "как сделать",
    "почему",
    "зачем",
    "когда",
    "кто",
    "где",
)

QUESTION_WORDS = (
    "как",
    "что",
    "почему",
    "зачем",
    "когда",
    "кто",
    "где",
    "можешь",
    "умеешь",
)

COMMAND_FILLER_PREFIXES = (
    "ну",
    "пожалуйста",
    "давай",
    "давайте",
)


def _compile_wake_prefix_pattern(aliases: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"^\s*(?:"
        + "|".join(re.escape(token) for token in sorted(aliases, key=len, reverse=True))
        + r")(?=$|[\s,.:;!?-])[\s,.:;!?-]*",
        re.IGNORECASE,
    )


WAKE_PREFIX_PATTERN = _compile_wake_prefix_pattern(WAKE_PREFIX_ALIASES)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def strip_leading_wake_prefix(text: str, aliases: tuple[str, ...] = WAKE_PREFIX_ALIASES) -> str:
    clean = normalize_text(text)
    if not clean:
        return ""
    pattern = WAKE_PREFIX_PATTERN if aliases == WAKE_PREFIX_ALIASES else _compile_wake_prefix_pattern(aliases)
    stripped = pattern.sub("", clean, count=1)
    stripped = stripped.lstrip(" ,.:;!?-")
    return normalize_text(stripped)


def strip_leading_command_fillers(text: str) -> str:
    clean = normalize_text(text)
    if not clean:
        return ""

    stripped = clean
    while True:
        parts = stripped.split(" ", 1)
        if len(parts) < 2:
            break
        first = parts[0].casefold()
        if first not in COMMAND_FILLER_PREFIXES:
            break
        stripped = parts[1].lstrip(" ,.:;!?-")
        if not stripped:
            return clean
    return normalize_text(stripped)


def looks_like_broken_command(text: str) -> bool:
    clean = normalize_text(text).casefold()
    if not clean:
        return False
    if clean in COMMAND_FRAGMENT_TOKENS:
        return True
    if clean.endswith((" и", " или", " потом")) and any(clean.startswith(f"{token} ") for token in COMMAND_FRAGMENT_TOKENS):
        return True
    return False


def clarification_question(text: str) -> str:
    clean = normalize_text(text).casefold()
    if not clean:
        return ""
    if clean.endswith((" и", " или", " потом")):
        return "Что ещё сделать?"
    if clean in OPEN_COMMAND_TOKENS:
        return "Что открыть?"
    if clean in ENABLE_COMMAND_TOKENS:
        return "Что включить?"
    if clean in SEARCH_COMMAND_TOKENS:
        return "Что найти?"
    if clean in REMINDER_COMMAND_TOKENS:
        return "Что напомнить?"
    return ""


def looks_like_conversation(text: str) -> bool:
    clean = normalize_text(text)
    lower = clean.casefold()
    if not lower:
        return False
    if any(lower.startswith(prefix) for prefix in CONVERSATION_PREFIXES):
        return True
    if clean.endswith("?"):
        return True
    first_word = lower.split(" ", 1)[0]
    if first_word in QUESTION_WORDS:
        return True
    if len(lower.split()) <= 7 and not any(lower.startswith(f"{token} ") or lower == token for token in COMMAND_FRAGMENT_TOKENS):
        return True
    return False

from __future__ import annotations

from difflib import SequenceMatcher
import re


WAKE_PREFIX_ALIASES = (
    "гарви с",
    "гарви",
    "гарри",
    "гаррис",
    "гарби",
    "гаривис",
    "джарвис",
    "жарвис",
    "жаравис",
    "дарвис",
    "джаврис",
    "дар вис",
    "рыж",
    "джервис",
    "джарвес",
    "джарис",
    "джарви",
    "жарви",
    "гарвис",
    "jarvis",
)

STRICT_WAKE_ALIASES = (
    "джарвис",
    "жарвис",
    "жаравис",
    "дарвис",
    "гарри",
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
    "громче",
    "тише",
    "пауза",
    "стоп",
    "следующее",
    "следующий",
    "назад",
    "дальше",
    "далее",
)

OPEN_COMMAND_TOKENS = ("открой", "открыть", "запусти", "запустить")
ENABLE_COMMAND_TOKENS = ("включи", "включить")
SEARCH_COMMAND_TOKENS = ("найди", "поищи", "ищи", "поиск")
REMINDER_COMMAND_TOKENS = ("напомни",)
SYSTEM_COMMAND_PREFIXES = (
    "выключ",
    "перезагруз",
    "перезапуст",
    "рестарт",
    "ребут",
    "сон",
    "усыпи",
    "режим сна",
    "гибернац",
    "выйди из",
    "выход из",
    "разлогин",
    "логаут",
    "заблокир",
    "блокировк",
    "блокируй",
    "локни",
)

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

SHORT_CONVERSATION_TOKENS = (
    "прив",
    "приветик",
    "ага",
    "ок",
    "окей",
    "угу",
    "ясно",
    "ясн",
    "лол",
    "да",
    "нет",
    "неа",
    "че",
    "чего",
    "сори",
    "спасибо",
    "здорова",
    "здарова",
    "здоров",
    "хай",
    "йо",
    "понятно",
    "пон",
    "норм",
    "нормально",
    "топ",
)

QUESTION_WORDS = (
    "как",
    "что",
    "сколько",
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

VOICE_CONVERSATION_WORDS = (
    "ты",
    "тебя",
    "тебе",
    "мне",
    "меня",
    "дела",
    "дело",
    "куча",
    "привет",
    "прив",
    "спасибо",
    "ладно",
    "да",
    "нет",
    "ок",
    "ага",
    "угу",
    "неа",
    "че",
    "чего",
    "сори",
    "все",
    "топ",
    "погоди",
    "подожди",
    "ща",
    "норм",
    "нормально",
    "сегодня",
    "сейчас",
)

FUZZY_WAKE_MIN_RATIO = 0.72


def _compile_wake_prefix_pattern(aliases: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"^\s*(?:"
        + "|".join(re.escape(token) for token in sorted(aliases, key=len, reverse=True))
        + r")(?=$|[\s,.:;!?-])[\s,.:;!?-]*",
        re.IGNORECASE,
    )


WAKE_PREFIX_PATTERN = _compile_wake_prefix_pattern(WAKE_PREFIX_ALIASES)


def _normalized_token(value: str) -> str:
    return normalize_text(value).casefold().strip(" ,.:;!?-")


def _best_fuzzy_wake_alias(candidate: str, aliases: tuple[str, ...]) -> str:
    normalized_candidate = _normalized_token(candidate)
    if not normalized_candidate:
        return ""

    if normalized_candidate in aliases:
        return normalized_candidate
    if len(normalized_candidate) < 5:
        return ""

    best_alias = ""
    best_ratio = 0.0
    for alias in aliases:
        ratio = SequenceMatcher(None, normalized_candidate, alias).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_alias = alias

    if best_ratio >= FUZZY_WAKE_MIN_RATIO:
        return best_alias
    return ""


def _fuzzy_strip_leading_wake_prefix(text: str, aliases: tuple[str, ...]) -> str:
    word_matches = list(re.finditer(r"\S+", text))
    if not word_matches:
        return ""

    candidates: list[tuple[str, int]] = []
    first = _normalized_token(word_matches[0].group(0))
    if first:
        candidates.append((first, 1))
    if len(word_matches) >= 2:
        combined = f"{word_matches[0].group(0)} {word_matches[1].group(0)}"
        combined_normalized = _normalized_token(combined)
        if combined_normalized:
            candidates.append((combined_normalized, 2))

    best_words = 0
    best_ratio = 0.0
    for candidate, words_used in candidates:
        alias = _best_fuzzy_wake_alias(candidate, aliases)
        if not alias:
            continue
        ratio = SequenceMatcher(None, candidate, alias).ratio()
        if words_used > best_words or ratio > best_ratio:
            best_words = words_used
            best_ratio = ratio

    if best_words <= 0:
        return text

    end_index = word_matches[best_words - 1].end()
    return normalize_text(text[end_index:].lstrip(" ,.:;!?-"))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def strip_leading_wake_prefix(text: str, aliases: tuple[str, ...] = WAKE_PREFIX_ALIASES) -> str:
    clean = normalize_text(text)
    if not clean:
        return ""
    pattern = WAKE_PREFIX_PATTERN if aliases == WAKE_PREFIX_ALIASES else _compile_wake_prefix_pattern(aliases)
    stripped = pattern.sub("", clean, count=1)
    stripped = normalize_text(stripped.lstrip(" ,.:;!?-"))
    if stripped != clean:
        return stripped
    return _fuzzy_strip_leading_wake_prefix(clean, aliases)


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


def looks_like_system_command(text: str) -> bool:
    lower = normalize_text(text).casefold()
    if not lower:
        return False
    return any(lower.startswith(prefix) for prefix in SYSTEM_COMMAND_PREFIXES)


def looks_like_explicit_conversation(text: str) -> bool:
    clean = normalize_text(text)
    lower = clean.casefold()
    if not lower:
        return False
    if looks_like_system_command(lower):
        return False
    if any(lower.startswith(prefix) for prefix in CONVERSATION_PREFIXES):
        return True
    if clean.endswith("?"):
        return True
    first_word = lower.split(" ", 1)[0]
    if first_word in QUESTION_WORDS:
        return True
    return False


def looks_like_conversation(text: str) -> bool:
    clean = normalize_text(text)
    lower = clean.casefold()
    if not lower:
        return False
    if looks_like_explicit_conversation(lower):
        return True
    words = lower.split()
    if len(words) == 1 and lower in SHORT_CONVERSATION_TOKENS:
        return True
    if not 3 <= len(words) <= 7:
        return False
    if any(lower.startswith(f"{token} ") or lower == token for token in COMMAND_FRAGMENT_TOKENS):
        return False
    return True


def looks_like_voice_conversation(text: str) -> bool:
    clean = normalize_text(text)
    lower = clean.casefold()
    if not lower:
        return False
    if looks_like_explicit_conversation(lower):
        return True
    if looks_like_system_command(lower):
        return False
    words = lower.split()
    if any(lower.startswith(f"{token} ") or lower == token for token in COMMAND_FRAGMENT_TOKENS):
        return False
    if len(words) == 1:
        return lower in SHORT_CONVERSATION_TOKENS or words[0] in VOICE_CONVERSATION_WORDS
    if len(words) > 4:
        return False
    return any(word in VOICE_CONVERSATION_WORDS for word in words)

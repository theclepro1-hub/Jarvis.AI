import hashlib
import logging
import re
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .branding import APP_LOGGER_NAME
from .custom_actions import load_custom_action_entries
from .state import CONFIG_MGR, _is_learned_pattern_generic

logger = logging.getLogger(APP_LOGGER_NAME)

REPLACEMENTS = {
    "дискор": "дискорд", "ю туб": "ютуб", "ютьюб": "ютуб",
    "вайлберис": "wildberries", "вайлдберис": "wildberries", "вэб": "wildberries",
    "твищ": "твич", "твит": "твич", "кс два": "кс2", "дбдэ": "дбд",
    "дед лок": "дедлок", "плей музыку": "музыка", "открой браузер": "браузер",
    "запусти браузер": "браузер", "фортнайта": "фортнайт", "фортнайте": "фортнайт",
    "следущая": "следующая", "следущий": "следующий", "предыдущая": "предыдущ",
    "предыдущий": "предыдущ", "назат": "назад", "вперёд": "вперёд",
    "следующая песня": "следующая", "предыдущая песня": "предыдущ",
}
SPLIT_PATTERN = re.compile(r"\s*(?:,|;| и потом | потом | затем | далее | и ещё | и также | и)\s*", re.IGNORECASE)
OPEN_VERBS = {"включи", "открой", "запусти", "включить", "запустить", "стартуй", "старт", "открыть"}
CLOSE_VERBS = {"выключи", "закрой", "выруби", "закрыть", "выключить", "отключи"}
STOP_TRIGGERS = {"пауза", "стоп музыка", "останови", "поставь на паузу", "стоп"}
PLAY_TRIGGERS = {"продолжи", "играй", "продолжить", "включи музыку"}
VOLUME_UP_TRIGGERS = {"громче", "прибавь", "увеличь громкость", "подними громкость", "добавь звук"}
VOLUME_DOWN_TRIGGERS = {"тише", "убавь", "уменьши громкость", "сделай тише", "снизь звук"}
NEXT_TRACK_TRIGGERS = {"следующ", "вперёд", "далее", "следующая", "следующее"}
PREV_TRACK_TRIGGERS = {"предыдущ", "назад", "обратно"}
SHUTDOWN_TRIGGERS = {"самоликвидация", "выключи пк", "выключи компьютер", "выруби комп", "выключись",
                      "выключить пк", "выключить компьютер", "выключить систему", "заверши работу", "вырубись", "отключись"}
RESTART_TRIGGERS = {"перезагрузи пк", "перезагрузи компьютер", "рестарт пк", "перезапусти пк",
                    "перезагрузить пк", "перезагрузить компьютер", "ребут", "перезагрузись", "рестарт", "перезапустить систему"}
LOCK_TRIGGERS = {"заблокируй", "лок экран", "заблокируй экран", "lock"}

COMMANDS = {
    "music": {"triggers": ["музык", "яндекс музыка", "плейлист"], "reply": "Музыка."},
    "youtube": {"triggers": ["ютуб", "youtube", "видео"], "reply": "Ютуб."},
    "ozon": {"triggers": ["озон", "ozon"], "reply": "Озон."},
    "wildberries": {"triggers": ["вб", "vb", "wb", "wildberries", "вэб", "вайдберес", "вайлдберес", "вайлдберриз"], "reply": "Вайлдберриз."},
    "browser": {"triggers": ["браузер", "хром", "chrome", "сайт"], "reply": "Браузер."},
    "cs2": {"triggers": ["кс", "кс2", "кс 2", "контра", "counter strike"], "reply": "CS2."},
    "fortnite": {"triggers": ["фортнайт", "fortnite", "эпик", "epic"], "reply": "Фортнайт."},
    "dbd": {"triggers": ["дбд", "dead by daylight", "дэбэдэ"], "reply": "DBD."},
    "deadlock": {"triggers": ["дедлок", "deadlock"], "reply": "Дедлок."},
    "steam": {"triggers": ["стим", "steam"], "reply": "Стим."},
    "settings": {"triggers": ["настройки", "параметры", "settings"], "reply": "Настройки."},
    "twitch": {"triggers": ["твитч", "твич", "twitch"], "reply": "Твич."},
    "discord": {"triggers": ["дискорд", "discord", "дс"], "reply": "Дискорд."},
    "notepad": {"triggers": ["блокнот", "notepad"], "reply": "Блокнот."},
    "calc": {"triggers": ["калькулятор", "calculator"], "reply": "Калькулятор."},
    "taskmgr": {"triggers": ["диспетчер задач", "task manager", "taskmgr"], "reply": "Диспетчер задач."},
    "explorer": {"triggers": ["проводник", "explorer", "файлы"], "reply": "Проводник."},
    "downloads": {"triggers": ["загрузки", "downloads", "скачки"], "reply": "Загрузки."},
    "documents": {"triggers": ["документы", "мои документы"], "reply": "Документы."},
    "desktop": {"triggers": ["рабочий стол", "рабочий стол"], "reply": "Рабочий стол."},
    "restart_explorer": {"triggers": ["перезапусти проводник", "рестарт проводника", "обнови проводник"], "reply": "Проводник перезапущен."},
    "restart_pc": {"triggers": ["перезагрузи пк", "перезагрузи компьютер", "рестарт пк", "перезапусти пк"], "reply": "Перезагрузка."},
    "lock": {"triggers": ["заблокируй экран", "лок экран", "заблокируй"], "reply": "Экран заблокирован."},
    "weather": {"triggers": ["погода", "какая погода"], "reply": "Погода."},
    "time": {"triggers": ["который час", "время", "час"], "reply": "Время."},
    "date": {"triggers": ["дата", "сегодня", "какое число"], "reply": "Дата."},
    "search": {"triggers": [], "reply": "Ищу."},
    "history": {"triggers": ["история", "последние команды", "что я говорил"], "reply": "История."},
    "repeat": {"triggers": ["повтори", "ещё раз", "скажи ещё раз"], "reply": "Повторяю."},
    "telegram": {"triggers": ["телеграм", "телеграмм", "telegram", "тг"], "reply": "Телеграм."},
    "roblox": {"triggers": ["роблокс", "roblox", "roblox studio", "роблокс студио"], "reply": "Роблокс."},
}

APP_CLOSE_EXES = {
    "music": ["Яндекс Музыка.exe"], "discord": ["Discord.exe"], "steam": ["Steam.exe"],
    "notepad": ["notepad.exe"], "calc": ["calc.exe"], "taskmgr": ["Taskmgr.exe"],
    "explorer": ["explorer.exe"], "deadlock": ["project8.exe"], "dbd": ["DeadByDaylight.exe"],
    "cs2": ["cs2.exe"],
    "fortnite": ["FortniteClient-Win64-Shipping.exe", "FortniteClient-Win64-Shipping_EAC.exe",
                 "FortniteClient-Win64-Shipping_BE.exe", "FortniteClient-Win64-Shipping_EOS.exe",
                 "FortniteLauncher.exe", "EpicGamesLauncher.exe"],
    "settings": ["SystemSettings.exe"], "telegram": ["Telegram.exe"],
    "roblox": ["RobloxPlayerBeta.exe", "RobloxPlayerLauncher.exe", "RobloxStudioBeta.exe"],
}

SIMPLE_BATCH_ACTIONS = {
    "music", "youtube", "ozon", "wildberries", "browser", "cs2", "fortnite", "dbd", "deadlock",
    "steam", "settings", "twitch", "discord", "notepad", "calc", "taskmgr", "explorer", "downloads",
    "documents", "desktop", "restart_explorer", "close_app", "history", "repeat", "telegram", "roblox",
    "media_play", "timur_son", "search", "open_dynamic_app"
}

def normalize_text(text: str) -> str:
    text = (text or "").lower().strip().replace("ё", "е")
    pattern = re.compile(r'\b(?:джервис|джэрвис|джарвес|джирвис|жарвис|дарвис)\b')
    text = pattern.sub('джарвис', text)
    for bad, good in REPLACEMENTS.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text)


WAKE_WORD_FORMS = (
    "джарвис", "джарвиса", "джарвису", "джарвисом", "джарвисе",
    "жарвис", "жарвиса", "жарвису",
    "дарвис", "дарвиса", "джарвес", "джирвис", "джервис", "джервис",
    "джавис", "джавес", "жавес", "джарис", "жарис",
    "jarvis", "jarviss", "jarwis", "javis", "jarves", "jarvies",
)
WAKE_WORD_BASE = (
    "джарвис",
    "жарвис",
    "дарвис",
    "джарвес",
    "джирвис",
    "джервис",
    "джавис",
    "джавес",
    "джарис",
    "jarvis",
)


def detect_wake_word(norm_text: str) -> Tuple[bool, str]:
    text = normalize_text(norm_text)
    if not text:
        return False, ""

    # Быстрый путь: прямое вхождение/морфологические окончания.
    wake_pattern = re.compile(r"\b(?:джарвис|жарвис|дарвис|джарвес|джирвис|джервис|джервис|jarvis)(?:а|у|ом|е|ы|и)?\b")
    direct = wake_pattern.search(text)
    if direct:
        return True, direct.group(0)

    tokens = re.findall(r"[a-zа-я0-9]+", text)
    if not tokens:
        return False, ""

    candidates = list(tokens)
    for left, right in zip(tokens, tokens[1:]):
        if len(left) <= 5 and len(right) <= 5:
            candidates.append(f"{left}{right}")
        candidates.append(f"{left}-{right}")

    best_match = ("", 0.0)
    for tok in candidates:
        cleaned = tok.replace("-", "")
        stripped = re.sub(r"(а|у|ом|е|ы|и|о)$", "", cleaned)
        variants = [cleaned, stripped]
        for v in variants:
            if v in WAKE_WORD_FORMS:
                return True, cleaned
            close = get_close_matches(v, WAKE_WORD_BASE, n=1, cutoff=0.68)
            if close:
                return True, cleaned
            ratio = max(SequenceMatcher(None, v, base).ratio() for base in WAKE_WORD_BASE)
            if ratio > best_match[1]:
                best_match = (cleaned, ratio)
    if best_match[1] >= 0.64:
        return True, best_match[0]
    return False, ""


def strip_wake_word(text: str) -> str:
    norm = normalize_text(text)
    if not norm:
        return ""
    stripped = re.sub(
        r"^.*?\b(?:джарвис|жарвис|дарвис|джарвес|джирвис|джервис|джервис|jarvis)(?:а|у|ом|е|ы|и)?\b[,:;!\-\s]*",
        "",
        norm,
        count=1,
    )
    return stripped.strip()

@lru_cache(maxsize=1)
def static_trigger_map():
    return {normalize_text(tr): key for key, data in COMMANDS.items() for tr in data["triggers"]}

def find_app_key(app_part: str) -> Optional[str]:
    q = normalize_text(app_part)
    if q in {"роблокс", "roblox", "roblox studio", "роблокс студио"}:
        return "roblox"
    best, best_ratio = None, 0.0
    for key, data in COMMANDS.items():
        if any(tr == q for tr in data["triggers"]):
            return key
        if len(q) >= 3:
            scores = [SequenceMatcher(None, q, normalize_text(tr)).ratio() for tr in data["triggers"]]
            scores.append(SequenceMatcher(None, q, key).ratio())
            max_sc = max(scores)
            if max_sc > best_ratio:
                best_ratio, best = max_sc, key
    return best if best_ratio > 0.65 else None

def make_dynamic_key(name: str, prefix: str = "app") -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    if not base:
        digest = hashlib.sha1((name or "app").encode("utf-8", errors="ignore")).hexdigest()[:8]
        base = f"{prefix}_{digest}"
    return f"{prefix}_{base}"[:80]

def _normalize_aliases(aliases):
    if not isinstance(aliases, list):
        return []
    seen = set()
    out = []
    for a in aliases:
        aa = normalize_text(str(a or "").strip())
        if aa and aa not in seen:
            seen.add(aa)
            out.append(aa)
    return out

def get_dynamic_entries() -> List[Dict[str, Any]]:
    entries = []
    seen_keys = set()
    for items in (CONFIG_MGR.get_custom_apps(), CONFIG_MGR.get_launcher_games(), load_custom_action_entries()):
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip().lower()
            name = str(item.get("name", "")).strip()
            launch = str(item.get("launch", "")).strip()
            if not key or not name or not launch or key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append({
                "key": key,
                "name": name,
                "launch": launch,
                "aliases": _normalize_aliases(item.get("aliases", [])),
                "close_exes": [str(x).strip() for x in (item.get("close_exes", []) or []) if str(x).strip()],
                "source": str(item.get("source", "custom") or "custom").strip().lower(),
            })
    return entries

def get_dynamic_entry_by_key(key: str) -> Optional[Dict[str, Any]]:
    k = str(key or "").strip().lower()
    if not k:
        return None
    for entry in get_dynamic_entries():
        if entry["key"] == k:
            return entry
    return None

def find_dynamic_entry(query: str) -> Optional[Dict[str, Any]]:
    q = normalize_text(query)
    if not q:
        return None
    best = None
    best_ratio = 0.0
    for entry in get_dynamic_entries():
        triggers = [normalize_text(entry.get("name", ""))] + entry.get("aliases", [])
        for tr in triggers:
            if not tr:
                continue
            if tr == q or tr in q or q in tr:
                return entry
            ratio = SequenceMatcher(None, q, tr).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best = entry
    return best if best_ratio >= 0.72 else None

class CommandParser:
    @staticmethod
    def _parse_reminder(c: str) -> Optional[Tuple[int, str]]:
        m = re.search(r'(?:напомни|напомни мне|создай напоминание|поставь напоминание|запомни)\s+(.+?)\s+через\s+(\d+)\s+(минут|минуты|минуту|час|часа|часов)', c)
        if m:
            text, num, unit = m.group(1).strip(), int(m.group(2)), m.group(3)
            seconds = num * 60 if unit.startswith("минут") else num * 3600
            return seconds, text
        m = re.search(r'через\s+(\d+)\s+(минут|минуты|минуту|час|часа|часов)\s+(?:напомни|напомни мне|создай напоминание|поставь напоминание|запомни)\s+(.+)', c)
        if m:
            num, unit, text = int(m.group(1)), m.group(2), m.group(3).strip()
            seconds = num * 60 if unit.startswith("минут") else num * 3600
            return seconds, text
        m = re.search(r'запомни\s+(.+?)\s+на\s+(\d+)\s+(минут|минуты|минуту|час|часа|часов)', c)
        if m:
            text, num, unit = m.group(1).strip(), int(m.group(2)), m.group(3)
            seconds = num * 60 if unit.startswith("минут") else num * 3600
            return seconds, text
        return None

    @staticmethod
    def _match_learned_command(c: str) -> Tuple[Optional[str], Any]:
        if not CONFIG_MGR.get_self_learning_enabled():
            return None, None
        for learned in CONFIG_MGR.get_learned_commands():
            if not isinstance(learned, dict):
                continue
            pattern = normalize_text(learned.get("pattern", ""))
            action = str(learned.get("action", "")).strip().lower()
            arg = learned.get("arg", None)
            if not pattern or not action or _is_learned_pattern_generic(pattern):
                continue
            if c == pattern:
                return action, arg
            if len(pattern.split()) >= 2 and pattern in c:
                return action, arg
            if len(pattern) >= 8 and SequenceMatcher(None, c, pattern).ratio() >= 0.94:
                return action, arg
        return None, None

    @staticmethod
    def classify_local(cmd: str) -> Tuple[Optional[str], Any]:
        c = normalize_text(cmd)
        logger.info(f"Classifying local command: {c}")

        if "тимур сын" in c or "тимуркин сын" in c:
            return "timur_son", None

        if any(re.search(fr'\b{p}\b', c) for p in SHUTDOWN_TRIGGERS):
            return "shutdown", None
        if any(re.search(fr'\b{p}\b', c) for p in RESTART_TRIGGERS):
            return "restart_pc", None
        if any(re.search(fr'\b{p}\b', c) for p in LOCK_TRIGGERS):
            return "lock", None

        words = c.split()
        if words and words[0] in OPEN_VERBS and len(words) > 1:
            target_name = " ".join(words[1:])
            target_norm = normalize_text(target_name)
            direct_targets = {
                "youtube": "youtube",
                "ютуб": "youtube",
                "steam": "steam",
                "стим": "steam",
                "discord": "discord",
                "дискорд": "discord",
                "роблокс": "roblox",
                "roblox": "roblox",
                "браузер": "browser",
                "chrome": "browser",
                "проводник": "explorer",
            }
            for token, action in direct_targets.items():
                if token in target_norm:
                    return action, None
            key = find_app_key(target_name)
            if key:
                return key, None
            dyn = find_dynamic_entry(target_name)
            if dyn:
                return "open_dynamic_app", dyn["key"]
        if words and words[0] in CLOSE_VERBS and len(words) > 1:
            target_name = " ".join(words[1:])
            key = find_app_key(target_name)
            if key:
                return "close_app", key
            dyn = find_dynamic_entry(target_name)
            if dyn:
                return "close_app", dyn["key"]

        search_match = re.search(
            r'(?:найди|поиск|ищи|search|гугл|погугли|найди в гугле|поищи в интернете|найди информацию о)\s+(?:в интернете\s+)?(.+)',
            c, re.IGNORECASE
        )
        if search_match:
            query = search_match.group(1).strip()
            return "search", query

        reminder = CommandParser._parse_reminder(c)
        if reminder:
            return "reminder", reminder

        for tr, key in static_trigger_map().items():
            if len(tr) <= 2:
                if re.search(rf'(?<!\w){re.escape(tr)}(?!\w)', c):
                    return key, None
            elif tr in c:
                return key, None

        if any(p in c for p in STOP_TRIGGERS): return "media_pause", None
        if any(p in c for p in PLAY_TRIGGERS): return "media_play", None
        if any(p in c for p in VOLUME_UP_TRIGGERS): return "volume_up", None
        if any(p in c for p in VOLUME_DOWN_TRIGGERS): return "volume_down", None
        if any(p in c for p in NEXT_TRACK_TRIGGERS): return "media_next", None
        if any(p in c for p in PREV_TRACK_TRIGGERS): return "media_prev", None

        if any(w in c for w in ("время","который час","час")): return "time", None
        if any(w in c for w in ("дата","сегодня","какое число")): return "date", None
        if "погода" in c: return "weather", None
        if "история" in c or "последние команды" in c or "что я говорил" in c: return "history", None
        if "повтори" in c or "ещё раз" in c or "скажи ещё раз" in c: return "repeat", None

        dyn = find_dynamic_entry(c)
        if dyn and (c == normalize_text(dyn.get("name", "")) or c in dyn.get("aliases", [])):
            return "open_dynamic_app", dyn["key"]

        learned_action, learned_arg = CommandParser._match_learned_command(c)
        if learned_action:
            return learned_action, learned_arg

        return None, None

__all__ = [
    "CommandParser",
    "SIMPLE_BATCH_ACTIONS",
    "SPLIT_PATTERN",
    "detect_wake_word",
    "find_dynamic_entry",
    "find_app_key",
    "get_dynamic_entries",
    "get_dynamic_entry_by_key",
    "make_dynamic_key",
    "normalize_text",
    "strip_wake_word",
]

import ctypes
import logging
import re
import sys
import time
import warnings
from typing import Any, Dict, List, Optional

try:
    import ctypes.wintypes as wintypes
except Exception:
    wintypes = None

import speech_recognition as sr

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import pyaudio
except Exception:
    pyaudio = None

try:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="'audioop' is deprecated and slated for removal in Python 3.13",
            category=DeprecationWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work",
            category=RuntimeWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Couldn't find ffprobe or avprobe - defaulting to ffprobe, but may not work",
            category=RuntimeWarning,
        )
        from pydub import AudioSegment
except Exception:
    AudioSegment = None

from .branding import APP_LOGGER_NAME
from .audio_runtime import compressed_audio_decoder_available

logger = logging.getLogger(APP_LOGGER_NAME)

# =========================================================
# AUDIO DEVICE HELPERS (only real microphones/outputs)
# =========================================================
_MIC_DEVICE_CACHE = {"ts": 0.0, "names": []}
_OUTPUT_DEVICE_CACHE = {"ts": 0.0, "names": []}
_AUDIO_DEVICE_INFO_CACHE = {
    "ts": 0.0,
    "devices": [],
    "by_index": {},
    "defaults": {"input": [], "output": []},
}
_HOSTAPI_PRIORITY = {
    "windows wasapi": 420,
    "windows wdm-ks": 320,
    "windows directsound": 220,
    "mme": 120,
}
_AUDIO_MODEL_ALIASES = (
    (r"\b(?:logitech\s+)?pro\s*x(?:\s+se)?\b", "pro x"),
    (r"\bg435\b", "g435"),
    (r"\b(?:station|станция)\s+mini(?:\s+new)?\b", "station mini"),
)
def _dedupe_names(names):
    seen = set()
    unique = []
    for n in names or []:
        name = re.sub(r"\s+", " ", str(n or "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return unique


def _clean_audio_device_name(name: str) -> str:
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text:
        return ""
    text = _repair_mojibake_text(text)
    text = re.sub(r"^\d+:\s*", "", text)
    text = re.sub(r"\s*\((?:mme|wasapi|wdm-ks|directsound|windows directsound|primary sound driver)\)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*-\s*(?:input|output)\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("Headset Earphone", "Наушники гарнитуры")
    text = text.replace("Headphones", "Наушники")
    text = text.replace("Speakers", "Динамики")
    text = text.replace("Microphone", "Микрофон")
    return text.strip(" -")


def _repair_mojibake_text(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""

    def _noise_score(value: str) -> int:
        low = value.lower()
        bad = (
            "рџ", "рµ", "р°", "сѓ", "с‚", "с…", "с€",
            "рњ", "рё", "рє", "рѕ", "р½", "с„", "сЂ", "сЏ",
            "ð", "ñ",
        )
        score = sum(low.count(token) for token in bad)
        score += sum(value.count(ch) for ch in "ÐÑРС") // 2
        return score

    base_score = _noise_score(raw)
    if base_score == 0:
        return raw

    best = raw
    best_score = base_score
    for enc in ("cp1251", "latin1"):
        try:
            fixed = raw.encode(enc, errors="strict").decode("utf-8", errors="strict")
        except Exception:
            continue
        fixed_score = _noise_score(fixed)
        if fixed_score < best_score and fixed.strip():
            best = fixed
            best_score = fixed_score
    return best


def _audio_device_family_key(name: str) -> str:
    text = _clean_audio_device_name(name).lower().replace("ё", "е")
    if not text:
        return ""
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    for pattern, replacement in _AUDIO_MODEL_ALIASES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return replacement
    if "realtek" in text:
        if re.search(r"\b(?:digital|spdif|s pdif|hdmi|optical)\b", text, flags=re.IGNORECASE):
            return "realtek digital"
        if re.search(r"(?:стерео\s+микшер|stereo\s+mix|stereo\s+input)", text, flags=re.IGNORECASE):
            return "realtek stereo mix"
        if re.search(r"(?:line\s+in|line\s+input|лин\s*\.?\s*вход)", text, flags=re.IGNORECASE):
            return "realtek line in"
        if re.search(r"(?:mic\s+input|\bmic\b|\bmicrophone\b|микрофон)", text, flags=re.IGNORECASE):
            return "realtek mic"
        return "realtek analog output"
    text = text.replace("[", " ").replace("]", " ")
    text = text.replace("(", " ").replace(")", " ")
    text = re.sub(
        r"\b(?:default|communication|communications|device|audio|endpoint|render|capture|output|input|headset|headphone|headphones|speaker|speakers|mic|microphone|wireless|gaming|наушники|гарнитура|гарнитуры|динамик|динамики|микрофон|колонка|колонки)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _is_secondary_audio_choice(name: str, kind: str = "output") -> bool:
    low = _clean_audio_device_name(name).lower().replace("ё", "е")
    if not low:
        return True
    shared_tokens = (
        "hands-free",
        "hands free",
        "hf audio",
        "communications",
        "communication",
    )
    if any(token in low for token in shared_tokens):
        return True
    if kind == "input":
        input_tokens = (
            "stereo mix",
            "стерео микшер",
            "stereo input",
            "what u hear",
            "line in",
            "line input",
            "лин. вход",
            "virtual",
            "loopback",
        )
        return any(token in low for token in input_tokens)
    output_tokens = (
        "digital output",
        "spdif",
        "s/pdif",
        "hdmi",
    )
    return any(token in low for token in output_tokens)


def _compressed_audio_decoder_available() -> bool:
    if AudioSegment is None:
        return False
    return compressed_audio_decoder_available()


def _host_api_priority(host_api: str) -> int:
    key = re.sub(r"\s+", " ", str(host_api or "")).strip().lower()
    return _HOSTAPI_PRIORITY.get(key, 40)


def _host_api_short_label(host_api: str) -> str:
    key = re.sub(r"\s+", " ", str(host_api or "")).strip().lower()
    mapping = {
        "windows wasapi": "WASAPI",
        "windows wdm-ks": "WDM-KS",
        "windows directsound": "DirectSound",
        "mme": "MME",
    }
    return mapping.get(key, str(host_api or "").strip())


def _enumerate_portaudio_devices(refresh: bool = False) -> List[Dict[str, Any]]:
    now = time.monotonic()
    cache = _AUDIO_DEVICE_INFO_CACHE
    if not refresh and cache["devices"] and (now - cache["ts"] < 5.0):
        return list(cache["devices"])

    devices: List[Dict[str, Any]] = []
    by_index: Dict[int, Dict[str, Any]] = {}
    defaults = {"input": [], "output": []}

    if pyaudio is not None:
        pa = None
        try:
            pa = pyaudio.PyAudio()
            host_names = {}
            for host_idx in range(int(pa.get_host_api_count() or 0)):
                try:
                    info = pa.get_host_api_info_by_index(host_idx) or {}
                except Exception:
                    continue
                host_name = str(info.get("name", "") or "").strip()
                host_names[host_idx] = host_name
                default_in = info.get("defaultInputDevice", info.get("default_input_device", -1))
                default_out = info.get("defaultOutputDevice", info.get("default_output_device", -1))
                try:
                    default_in = int(default_in)
                    if default_in >= 0:
                        defaults["input"].append(default_in)
                except Exception:
                    pass
                try:
                    default_out = int(default_out)
                    if default_out >= 0:
                        defaults["output"].append(default_out)
                except Exception:
                    pass

            for idx in range(int(pa.get_device_count() or 0)):
                try:
                    info = pa.get_device_info_by_index(idx) or {}
                except Exception:
                    continue
                name = str(info.get("name", "") or "").strip()
                host_api_idx = info.get("hostApi", info.get("hostapi", -1))
                try:
                    host_api_idx = int(host_api_idx)
                except Exception:
                    host_api_idx = -1
                host_api = host_names.get(host_api_idx, "")
                max_input = int(float(info.get("maxInputChannels", info.get("max_input_channels", 0)) or 0))
                max_output = int(float(info.get("maxOutputChannels", info.get("max_output_channels", 0)) or 0))
                default_rate = float(info.get("defaultSampleRate", info.get("default_samplerate", 0)) or 0)
                clean_name = _clean_audio_device_name(name)
                item = {
                    "index": idx,
                    "name": name,
                    "clean_name": clean_name or name,
                    "family": _audio_device_family_key(clean_name or name),
                    "host_api": host_api,
                    "host_api_priority": _host_api_priority(host_api),
                    "max_input_channels": max_input,
                    "max_output_channels": max_output,
                    "default_samplerate": default_rate,
                    "is_default_input": idx in defaults["input"],
                    "is_default_output": idx in defaults["output"],
                }
                devices.append(item)
                by_index[idx] = item
        except Exception as e:
            logger.warning(f"PortAudio enumeration error: {e}")
        finally:
            if pa is not None:
                try:
                    pa.terminate()
                except Exception:
                    pass

    if not devices and sd is not None:
        try:
            hostapis = sd.query_hostapis()
            queried = sd.query_devices()
            for host_idx, host in enumerate(hostapis or []):
                try:
                    default_in = int(host.get("default_input_device", -1))
                    if default_in >= 0:
                        defaults["input"].append(default_in)
                except Exception:
                    pass
                try:
                    default_out = int(host.get("default_output_device", -1))
                    if default_out >= 0:
                        defaults["output"].append(default_out)
                except Exception:
                    pass
            for idx, info in enumerate(queried or []):
                host_idx = info.get("hostapi", -1)
                try:
                    host_idx = int(host_idx)
                except Exception:
                    host_idx = -1
                host_name = ""
                if 0 <= host_idx < len(hostapis or []):
                    host_name = str((hostapis or [])[host_idx].get("name", "") or "").strip()
                name = str(info.get("name", "") or "").strip()
                clean_name = _clean_audio_device_name(name)
                item = {
                    "index": idx,
                    "name": name,
                    "clean_name": clean_name or name,
                    "family": _audio_device_family_key(clean_name or name),
                    "host_api": host_name,
                    "host_api_priority": _host_api_priority(host_name),
                    "max_input_channels": int(float(info.get("max_input_channels", 0) or 0)),
                    "max_output_channels": int(float(info.get("max_output_channels", 0) or 0)),
                    "default_samplerate": float(info.get("default_samplerate", 0) or 0),
                    "is_default_input": idx in defaults["input"],
                    "is_default_output": idx in defaults["output"],
                }
                devices.append(item)
                by_index[idx] = item
        except Exception as e:
            logger.warning(f"sounddevice enumeration fallback error: {e}")

    cache["devices"] = list(devices)
    cache["by_index"] = dict(by_index)
    cache["defaults"] = {
        "input": sorted(set(int(x) for x in defaults["input"] if isinstance(x, int) or str(x).isdigit())),
        "output": sorted(set(int(x) for x in defaults["output"] if isinstance(x, int) or str(x).isdigit())),
    }
    cache["ts"] = now
    return list(devices)


def _get_audio_device_entry(index: Optional[int], refresh: bool = False) -> Optional[Dict[str, Any]]:
    if index in ("", None, "None"):
        return None
    try:
        idx = int(index)
    except Exception:
        return None
    _enumerate_portaudio_devices(refresh=refresh)
    item = _AUDIO_DEVICE_INFO_CACHE["by_index"].get(idx)
    return dict(item) if item else None


def list_input_device_entries_safe(refresh: bool = False) -> List[Dict[str, Any]]:
    entries = []
    for item in _enumerate_portaudio_devices(refresh=refresh):
        if int(item.get("max_input_channels", 0) or 0) <= 0:
            continue
        entries.append(dict(item))
    return entries


def list_output_device_entries_safe(refresh: bool = False) -> List[Dict[str, Any]]:
    entries = []
    for item in _enumerate_portaudio_devices(refresh=refresh):
        if int(item.get("max_output_channels", 0) or 0) <= 0:
            continue
        entries.append(dict(item))
    return entries


def _find_audio_device_entry_by_name(name: str, kind: str = "output", refresh: bool = False) -> Optional[Dict[str, Any]]:
    raw_name = str(name or "").strip()
    if not raw_name:
        return None
    clean_name = _clean_audio_device_name(raw_name)
    family = _audio_device_family_key(clean_name or raw_name)
    entries = list_input_device_entries_safe(refresh=refresh) if kind == "input" else list_output_device_entries_safe(refresh=refresh)
    best = None
    best_score = -10**9
    for item in entries:
        item_name = item.get("clean_name") or _clean_audio_device_name(item.get("name"))
        if not item_name:
            continue
        item_family = item.get("family") or _audio_device_family_key(item_name)
        same_name = item_name.lower() == clean_name.lower()
        same_family = family and item_family == family
        if not same_name and not same_family:
            continue
        score = int(item.get("host_api_priority", 0) or 0)
        if same_name:
            score += 500
        if same_family:
            score += 120
        if _is_secondary_audio_choice(item_name, kind=kind):
            score -= 80
        score += len(item_name)
        if kind == "input" and item.get("is_default_input"):
            score += 80
        if kind == "output" and item.get("is_default_output"):
            score += 80
        if score > best_score:
            best = item
            best_score = score
    return dict(best) if best else None


def _expand_audio_device_name(name: str, kind: str = "input") -> str:
    base = _clean_audio_device_name(name)
    if not base:
        return ""
    family = _audio_device_family_key(base)
    if not family:
        return base
    best = base
    candidates = list_input_device_entries_safe(refresh=False) if kind == "input" else list_output_device_entries_safe(refresh=False)
    for item in candidates:
        cand = _clean_audio_device_name(item.get("name") or item.get("clean_name"))
        if not cand:
            continue
        if _audio_device_family_key(cand) != family:
            continue
        cand_len = len(cand) + int(item.get("host_api_priority", 0) or 0) // 100
        best_len = len(best)
        if cand_len > best_len:
            best = cand
    return best


def _is_audio_garbage_name(name: str) -> bool:
    low = str(name or "").strip().lower().replace("ё", "е")
    if not low:
        return True
    garbage_tokens = (
        "@system32\\drivers",
        "bthhfenum.sys",
        "primary sound driver",
        "primary sound capture driver",
        "первичный звуковой драйвер",
        "первичный драйвер записи звука",
        "mapper",
        "stereo mix",
        "стерео микшер",
        "what u hear",
        "virtual",
        "spdif",
        "hdmi",
        "nvidia high definition",
        "line output",
        "line in",
        "line input",
        "лин. вход",
        "линейный вход",
        "loopback",
        "переназнач",
        "назначение звуков",
        "communication device",
        "communications device",
        "default audio",
        "default device",
        "primary driver",
    )
    if any(token in low for token in garbage_tokens):
        return True
    if low.endswith("()") or low.endswith("( )"):
        return True
    if low.startswith(("input (", "output (", "вход (", "выход (")):
        return True
    if low in {"input", "output", "микрофон", "динамики"}:
        return True
    mojibake_tokens = ("рџ", "рµ", "р°", "сѓ", "с‚", "с…", "с€", "ð", "ñ")
    return sum(low.count(token) for token in mojibake_tokens) >= 2


def _list_sounddevice_names(kind: str):
    if sd is None:
        return []
    result = []
    try:
        devices = sd.query_devices()
        for device in devices:
            try:
                max_in = int(float(device.get("max_input_channels", 0) or 0))
                max_out = int(float(device.get("max_output_channels", 0) or 0))
                if kind == "input" and max_in <= 0:
                    continue
                if kind == "output" and max_out <= 0:
                    continue
                name = str(device.get("name", "") or "").strip()
                if not name:
                    continue
                result.append(name)
            except Exception:
                continue
    except Exception:
        return []
    return _dedupe_names(result)


def list_microphone_names_safe(refresh: bool = False):
    now = time.monotonic()
    if not refresh and _MIC_DEVICE_CACHE["names"] and (now - _MIC_DEVICE_CACHE["ts"] < 5.0):
        return list(_MIC_DEVICE_CACHE["names"])

    entries = list_input_device_entries_safe(refresh=refresh)
    if entries:
        max_index = max(int(item.get("index", 0) or 0) for item in entries)
        indexed_names = [""] * (max_index + 1)
        for item in entries:
            try:
                idx = int(item.get("index", 0) or 0)
            except Exception:
                continue
            if 0 <= idx < len(indexed_names):
                indexed_names[idx] = str(item.get("name", "") or "").strip()
        _MIC_DEVICE_CACHE["names"] = indexed_names
        _MIC_DEVICE_CACHE["ts"] = now
        return list(indexed_names)

    names = []
    try:
        # Keep SR order/indexes to avoid device index mismatch during capture.
        names = sr.Microphone.list_microphone_names() or []
    except Exception:
        names = []

    if not names and sys.platform == "win32" and wintypes is not None:
        try:
            class WAVEINCAPSW(ctypes.Structure):
                _fields_ = [
                    ("wMid", wintypes.WORD),
                    ("wPid", wintypes.WORD),
                    ("vDriverVersion", wintypes.DWORD),
                    ("szPname", wintypes.WCHAR * 32),
                    ("dwFormats", wintypes.DWORD),
                    ("wChannels", wintypes.WORD),
                    ("wReserved1", wintypes.WORD),
                ]

            waveInGetNumDevs = ctypes.windll.winmm.waveInGetNumDevs
            waveInGetDevCapsW = ctypes.windll.winmm.waveInGetDevCapsW
            count = waveInGetNumDevs()
            for idx in range(count):
                caps = WAVEINCAPSW()
                res = waveInGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps))
                if res == 0 and caps.szPname:
                    names.append(str(caps.szPname).strip())
        except Exception as e:
            logger.warning(f"Microphone list error (winmm): {e}")

    if not names:
        names = _list_sounddevice_names("input")

    unique = []
    for raw in names or []:
        name = re.sub(r"\s+", " ", str(raw or "")).strip()
        if name:
            unique.append(name)
    _MIC_DEVICE_CACHE["names"] = unique
    _MIC_DEVICE_CACHE["ts"] = now
    return unique


def list_output_device_names_safe(refresh: bool = False):
    now = time.monotonic()
    if not refresh and _OUTPUT_DEVICE_CACHE["names"] and (now - _OUTPUT_DEVICE_CACHE["ts"] < 10.0):
        return list(_OUTPUT_DEVICE_CACHE["names"])

    entries = list_output_device_entries_safe(refresh=refresh)
    if entries:
        names = [str(item.get("name", "") or "").strip() for item in entries if str(item.get("name", "") or "").strip()]
        unique = _dedupe_names(names)
        _OUTPUT_DEVICE_CACHE["names"] = unique
        _OUTPUT_DEVICE_CACHE["ts"] = now
        return list(unique)

    names = _list_sounddevice_names("output")
    if not names and sys.platform == "win32" and wintypes is not None:
        try:
            class WAVEOUTCAPSW(ctypes.Structure):
                _fields_ = [
                    ("wMid", wintypes.WORD),
                    ("wPid", wintypes.WORD),
                    ("vDriverVersion", wintypes.DWORD),
                    ("szPname", wintypes.WCHAR * 32),
                    ("dwFormats", wintypes.DWORD),
                    ("wChannels", wintypes.WORD),
                    ("wReserved1", wintypes.WORD),
                    ("dwSupport", wintypes.DWORD),
                ]

            waveOutGetNumDevs = ctypes.windll.winmm.waveOutGetNumDevs
            waveOutGetDevCapsW = ctypes.windll.winmm.waveOutGetDevCapsW
            count = int(waveOutGetNumDevs())
            for idx in range(count):
                caps = WAVEOUTCAPSW()
                res = waveOutGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps))
                if res == 0 and caps.szPname:
                    names.append(str(caps.szPname).strip())
        except Exception as e:
            logger.debug(f"Output device enumeration error: {e}")

    unique = _dedupe_names(names)
    _OUTPUT_DEVICE_CACHE["names"] = unique
    _OUTPUT_DEVICE_CACHE["ts"] = now
    return list(unique)

# =========================================================
# МИКРОФОН (автоматический выбор)
# =========================================================
def pick_microphone_device():
    try:
        best = None
        best_score = -10**9
        for item in list_input_device_entries_safe(refresh=True):
            idx = int(item.get("index", 0) or 0)
            cleaned = _expand_audio_device_name(item.get("name"), "input")
            low = cleaned.lower().replace("ё", "е")
            if not cleaned or _is_audio_garbage_name(cleaned):
                continue
            score = 0
            if any(token in low for token in ("микрофон", "microphone", "mic")):
                score += 24
            if any(token in low for token in ("гарнитура", "headset", "wireless", "bluetooth", "logitech", "g435", "pro x", "realtek")):
                score += 10
            if any(token in low for token in ("line in", "line input", "стерео микшер", "stereo mix", "what u hear")):
                score -= 20
            if any(token in low for token in ("speaker", "speakers", "динамик", "output", "выход", "spdif", "hdmi", "digital output")):
                score -= 16
            if _is_secondary_audio_choice(cleaned, kind="input"):
                score -= 40
            if item.get("is_default_input"):
                score += 18
            score += int(item.get("host_api_priority", 0) or 0) // 12
            score += min(int(item.get("max_input_channels", 0) or 0), 2) * 2
            score += min(int(float(item.get("default_samplerate", 0) or 0) // 1000), 6)
            if score > best_score:
                best = (idx, cleaned)
                best_score = score
        if best is not None:
            return best

        names = list_microphone_names_safe(refresh=True)
        for i, name in enumerate(names):
            cleaned = _clean_audio_device_name(name)
            if cleaned and not _is_audio_garbage_name(cleaned):
                return i, cleaned
    except Exception as e:
        logger.warning(f"Microphone detection error: {e}")
    return None, None


def pick_output_device():
    try:
        best = None
        best_score = -10**9
        for item in list_output_device_entries_safe(refresh=True):
            idx = int(item.get("index", 0) or 0)
            cleaned = _expand_audio_device_name(item.get("name"), "output")
            low = cleaned.lower().replace("ё", "е")
            if not cleaned or _is_audio_garbage_name(cleaned):
                continue
            score = 0
            if any(token in low for token in ("динамик", "speaker", "speakers", "output", "выход", "headphones", "науш")):
                score += 18
            if any(token in low for token in ("bluetooth", "wireless", "гарнитура", "headset", "logitech", "g435", "pro x", "realtek", "станци")):
                score += 10
            if any(token in low for token in ("hands-free", "hf audio", "line in", "microphone", "mic", "input", "capture")):
                score -= 18
            if _is_secondary_audio_choice(cleaned, kind="output"):
                score -= 24
            if item.get("is_default_output"):
                score += 24
            score += int(item.get("host_api_priority", 0) or 0) // 12
            score += min(int(item.get("max_output_channels", 0) or 0), 2) * 2
            score += min(int(float(item.get("default_samplerate", 0) or 0) // 1000), 6)
            if score > best_score:
                best = (idx, cleaned)
                best_score = score
        if best is not None:
            return best

        names = list_output_device_names_safe(refresh=True)
        for i, name in enumerate(names):
            cleaned = _clean_audio_device_name(name)
            if cleaned and not _is_audio_garbage_name(cleaned):
                return i, cleaned
    except Exception as e:
        logger.warning(f"Output detection error: {e}")
    return None, None


audio_device_family_key = _audio_device_family_key
expand_audio_device_name = _expand_audio_device_name
find_audio_device_entry_by_name = _find_audio_device_entry_by_name
get_audio_device_entry = _get_audio_device_entry
host_api_short_label = _host_api_short_label
is_audio_garbage_name = _is_audio_garbage_name
is_secondary_audio_choice = _is_secondary_audio_choice

__all__ = [
    "_audio_device_family_key",
    "_expand_audio_device_name",
    "_find_audio_device_entry_by_name",
    "_get_audio_device_entry",
    "_host_api_short_label",
    "_is_audio_garbage_name",
    "_is_secondary_audio_choice",
    "audio_device_family_key",
    "expand_audio_device_name",
    "find_audio_device_entry_by_name",
    "get_audio_device_entry",
    "host_api_short_label",
    "is_audio_garbage_name",
    "is_secondary_audio_choice",
    "list_input_device_entries_safe",
    "list_microphone_names_safe",
    "list_output_device_entries_safe",
    "list_output_device_names_safe",
    "pick_microphone_device",
    "pick_output_device",
]

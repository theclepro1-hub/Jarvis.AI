from typing import Dict, List, Tuple


LISTENING_PROFILES = {
    "normal": {
        "label": "1 - Базовый",
        "energy_threshold": 1220,
        "pause_threshold": 0.38,
        "phrase_threshold": 0.15,
        "non_speaking_duration": 0.26,
        "dynamic_energy_adjustment_damping": 0.06,
        "dynamic_energy_ratio": 1.55,
    },
    "boost": {
        "label": "2 - Усиленный",
        "energy_threshold": 860,
        "pause_threshold": 0.28,
        "phrase_threshold": 0.11,
        "non_speaking_duration": 0.18,
        "dynamic_energy_adjustment_damping": 0.045,
        "dynamic_energy_ratio": 1.26,
    },
    "aggressive": {
        "label": "3 - Максимальный",
        "energy_threshold": 620,
        "pause_threshold": 0.20,
        "phrase_threshold": 0.08,
        "non_speaking_duration": 0.12,
        "dynamic_energy_adjustment_damping": 0.03,
        "dynamic_energy_ratio": 1.08,
    },
}


def profile_values(profile_name: str) -> Dict[str, float]:
    profile = str(profile_name or "normal").strip().lower()
    if profile not in LISTENING_PROFILES:
        profile = "normal"
    values = dict(LISTENING_PROFILES[profile])
    values["profile"] = profile
    return values


def device_profile_kind(device_name: str = "") -> str:
    name = str(device_name or "").strip().lower()
    if any(token in name for token in ("headset", "гарнитур", "g435", "logitech", "pro x", "hyperx", "steelseries", "razer")):
        return "headset"
    if any(token in name for token in ("usb", "blue yeti", "samson", "fifine", "shure", "elgato", "podmic")):
        return "usb_mic"
    if any(token in name for token in ("array", "realtek", "встроенн", "laptop", "notebook", "webcam", "камера")):
        return "built_in"
    return "default"


def resolved_device_profile_kind(device_name: str = "", override: str = "auto") -> str:
    forced = str(override or "auto").strip().lower()
    if forced in {"headset", "usb_mic", "built_in", "default"}:
        return forced
    return device_profile_kind(device_name)


def apply_device_listening_tuning(
    values: Dict[str, float],
    device_name: str = "",
    passive_mode: bool = False,
    device_kind_override: str = "auto",
) -> Dict[str, float]:
    tuned = dict(values or {})
    kind = resolved_device_profile_kind(device_name, device_kind_override)

    if kind in {"headset", "usb_mic"}:
        tuned["energy_threshold"] = int(max(300, float(tuned.get("energy_threshold", 1200)) * 0.78))
        tuned["dynamic_energy_ratio"] = max(1.01, float(tuned.get("dynamic_energy_ratio", 1.5)) - 0.16)
        tuned["pause_threshold"] = min(0.44, float(tuned.get("pause_threshold", 0.35)) + 0.02)
        tuned["phrase_threshold"] = max(0.05, float(tuned.get("phrase_threshold", 0.15)) - 0.03)
        tuned["non_speaking_duration"] = max(0.10, float(tuned.get("non_speaking_duration", 0.2)) - 0.03)
    elif kind == "built_in":
        tuned["energy_threshold"] = int(max(320, float(tuned.get("energy_threshold", 1200)) * 0.86))
        tuned["dynamic_energy_ratio"] = max(1.04, float(tuned.get("dynamic_energy_ratio", 1.5)) - 0.08)
        tuned["phrase_threshold"] = max(0.06, float(tuned.get("phrase_threshold", 0.15)) - 0.02)
        tuned["non_speaking_duration"] = max(0.10, float(tuned.get("non_speaking_duration", 0.2)) - 0.02)

    if passive_mode:
        tuned["energy_threshold"] = int(max(220, float(tuned.get("energy_threshold", 1200)) * 0.66))
        tuned["dynamic_energy_adjustment_damping"] = max(0.015, float(tuned.get("dynamic_energy_adjustment_damping", 0.05)) - 0.015)
        tuned["dynamic_energy_ratio"] = max(1.0, float(tuned.get("dynamic_energy_ratio", 1.5)) - 0.20)
        tuned["pause_threshold"] = min(0.38, float(tuned.get("pause_threshold", 0.35)) + 0.01)
        tuned["phrase_threshold"] = max(0.04, float(tuned.get("phrase_threshold", 0.15)) - 0.05)
        tuned["non_speaking_duration"] = max(0.08, float(tuned.get("non_speaking_duration", 0.2)) - 0.05)

    return tuned


def device_adaptation_tags(
    device_name: str = "",
    passive_mode: bool = False,
    proxy_detected: bool = False,
    safe_mode: bool = False,
    wake_word_boost: bool = False,
) -> List[str]:
    tags: List[str] = []
    kind = device_profile_kind(device_name)
    if kind == "headset":
        tags.append("гарнитура")
    elif kind == "usb_mic":
        tags.append("USB-микрофон")
    elif kind == "built_in":
        tags.append("встроенный микрофон")
    if passive_mode and wake_word_boost:
        tags.append("wake boost")
    elif passive_mode:
        tags.append("passive listen")
    if proxy_detected:
        tags.append("VPN/Proxy")
    if safe_mode:
        tags.append("safe mode")
    return tags or ["базовый профиль"]


def get_capture_timing(profile_name: str, manual_mode: bool = False) -> Tuple[float, float]:
    profile = str(profile_name or "normal").strip().lower()
    if manual_mode:
        manual_defaults = {
            "normal": (1.05, 6.4),
            "boost": (0.95, 6.0),
            "aggressive": (0.85, 5.6),
        }
        return manual_defaults.get(profile, manual_defaults["normal"])

    passive_defaults = {
        "normal": (1.18, 5.8),
        "boost": (0.98, 5.1),
        "aggressive": (0.82, 4.6),
    }
    return passive_defaults.get(profile, passive_defaults["normal"])


__all__ = [
    "LISTENING_PROFILES",
    "apply_device_listening_tuning",
    "device_adaptation_tags",
    "device_profile_kind",
    "get_capture_timing",
    "profile_values",
    "resolved_device_profile_kind",
]

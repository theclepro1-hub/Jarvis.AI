from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.ai.local_llm_service import LocalLLMService


SUPPORTED_ASSISTANT_MODES = ("fast", "standard", "smart", "private")
SUPPORTED_TEXT_BACKEND_OVERRIDES = ("auto", "groq", "cerebras", "gemini", "openrouter", "local_llama")
SUPPORTED_STT_BACKEND_OVERRIDES = ("auto", "groq_whisper", "local_faster_whisper", "local_vosk")

DEFAULT_ASSISTANT_MODE = "standard"
DEFAULT_LOCAL_LLM_BACKEND = "llama_cpp"

TEXT_ROUTES: dict[str, tuple[str, ...]] = {
    "fast": ("groq", "cerebras", "openrouter"),
    "standard": ("local_llama", "groq", "cerebras", "openrouter"),
    "smart": ("gemini", "groq", "cerebras", "openrouter"),
    "private": ("local_llama",),
}

STT_ROUTES: dict[str, tuple[str, ...]] = {
    "fast": ("groq_whisper", "local_faster_whisper", "local_vosk"),
    "standard": ("local_faster_whisper", "local_vosk", "groq_whisper"),
    "smart": ("groq_whisper", "local_faster_whisper", "local_vosk"),
    "private": ("local_faster_whisper", "local_vosk"),
}


@dataclass(frozen=True, slots=True)
class AssistantReadiness:
    local_llama_ready: bool = False
    local_faster_whisper_ready: bool = False
    local_vosk_ready: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedAssistantPolicy:
    mode: str
    text_route: tuple[str, ...]
    stt_route: tuple[str, ...]
    cloud_allowed: bool
    privacy_guarantee: str
    display_summary: str
    readiness_issues: tuple[str, ...]
    text_cloud_allowed: bool
    stt_cloud_allowed: bool


def resolve_assistant_mode(settings: Any) -> str:
    explicit = _normalize_mode(_setting(settings, "assistant_mode", ""))
    if explicit:
        return explicit
    return infer_assistant_mode_from_legacy(settings)


def infer_assistant_mode_from_legacy(settings: Any) -> str:
    voice_mode = str(_setting(settings, "voice_mode", "") or "").strip().casefold()
    if voice_mode == "private":
        return "private"
    if voice_mode == "balance":
        return "standard"
    if voice_mode == "quality":
        return "smart"

    ai_provider = str(_setting(settings, "ai_provider", "") or "").strip().casefold()
    ai_mode = str(_setting(settings, "ai_mode", "") or "").strip().casefold()
    if ai_mode == "local":
        return "private"
    if ai_provider == "gemini" or ai_mode == "quality":
        return "smart"
    if ai_mode == "fast" or ai_provider in {"groq", "cerebras"}:
        return "fast"
    return DEFAULT_ASSISTANT_MODE


def local_llama_ready(settings: Any) -> bool:
    try:
        return bool(LocalLLMService(settings).status().ready)
    except Exception:  # noqa: BLE001
        return False


def resolve_assistant_policy(
    settings: Any,
    readiness: AssistantReadiness | None = None,
) -> ResolvedAssistantPolicy:
    readiness = readiness or AssistantReadiness(local_llama_ready=local_llama_ready(settings))
    mode = resolve_assistant_mode(settings)

    text_override = _normalize_text_override(_setting(settings, "text_backend_override", "auto"))
    stt_override = _normalize_stt_override(_setting(settings, "stt_backend_override", "auto"))
    if mode == "private":
        if text_override not in {"auto", "local_llama"}:
            text_override = "local_llama"
        if stt_override == "groq_whisper":
            stt_override = "auto"

    text_cloud_allowed = _cloud_fallback_allowed(settings, key="allow_text_cloud_fallback", mode=mode)
    stt_cloud_allowed = _cloud_fallback_allowed(settings, key="allow_stt_cloud_fallback", mode=mode)
    cloud_allowed = text_cloud_allowed or stt_cloud_allowed

    text_route = (text_override,) if text_override != "auto" else TEXT_ROUTES[mode]
    stt_route = (stt_override,) if stt_override != "auto" else STT_ROUTES[mode]

    readiness_issues: list[str] = []
    if "local_llama" in text_route and not readiness.local_llama_ready:
        readiness_issues.append("local_llama_missing")
    if "local_faster_whisper" in stt_route and not readiness.local_faster_whisper_ready:
        readiness_issues.append("local_faster_whisper_missing")
    if "local_vosk" in stt_route and not readiness.local_vosk_ready:
        readiness_issues.append("local_vosk_missing")

    privacy_guarantee = {
        "fast": "cloud_first",
        "standard": "local_first_with_fallback",
        "smart": "quality_first",
        "private": "no_cloud_ever",
    }[mode]

    summary = _summary_for_mode(mode, readiness_issues, text_cloud_allowed, stt_cloud_allowed)
    return ResolvedAssistantPolicy(
        mode=mode,
        text_route=text_route,
        stt_route=stt_route,
        cloud_allowed=cloud_allowed,
        privacy_guarantee=privacy_guarantee,
        display_summary=summary,
        readiness_issues=tuple(readiness_issues),
        text_cloud_allowed=text_cloud_allowed,
        stt_cloud_allowed=stt_cloud_allowed,
    )


def _summary_for_mode(
    mode: str,
    readiness_issues: list[str],
    text_cloud_allowed: bool,
    stt_cloud_allowed: bool,
) -> str:
    if mode == "private":
        if readiness_issues:
            return "Приватный режим включён, но локальные модели ещё не готовы."
        return "Приватный режим: wake и распознавание локально, текст наружу не уходит."
    if mode == "standard" and readiness_issues:
        return "Стандартный режим: сначала локально, при нехватке моделей временно с cloud fallback."
    if mode == "fast":
        return "Быстрый режим: приоритет скорости, облачные маршруты используются первыми."
    if mode == "smart":
        return "Умный режим: приоритет качества, облачные quality-маршруты используются первыми."
    if text_cloud_allowed or stt_cloud_allowed:
        return "Режим ассистента активен."
    return "Режим ассистента активен без cloud fallback."


def _cloud_fallback_allowed(settings: Any, *, key: str, mode: str) -> bool:
    if mode == "private":
        return False
    value = _setting(settings, key, True)
    return bool(value)


def _normalize_mode(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered in SUPPORTED_ASSISTANT_MODES:
        return lowered
    return ""


def _normalize_text_override(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered in SUPPORTED_TEXT_BACKEND_OVERRIDES:
        return lowered
    return "auto"


def _normalize_stt_override(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered in SUPPORTED_STT_BACKEND_OVERRIDES:
        return lowered
    return "auto"


def _setting(settings: Any, key: str, default: Any) -> Any:
    if isinstance(settings, Mapping):
        return settings.get(key, default)
    getter = getattr(settings, "get", None)
    if callable(getter):
        return getter(key, default)
    return default

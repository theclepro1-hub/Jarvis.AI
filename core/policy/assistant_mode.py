from __future__ import annotations

from dataclasses import dataclass

from core.ai.local_llm_service import LocalLLMService


ASSISTANT_MODES = frozenset({"fast", "standard", "smart", "private"})
TEXT_OVERRIDES = frozenset({"auto", "groq", "cerebras", "gemini", "openrouter", "local_llama"})
STT_OVERRIDES = frozenset({"auto", "groq_whisper", "local_faster_whisper", "local_vosk"})


@dataclass(frozen=True, slots=True)
class AssistantReadiness:
    local_llama_ready: bool = False
    local_faster_whisper_ready: bool = False
    local_vosk_ready: bool = False


@dataclass(frozen=True, slots=True)
class AssistantPolicy:
    mode: str
    text_route: tuple[str, ...]
    stt_route: tuple[str, ...]
    text_cloud_allowed: bool
    stt_cloud_allowed: bool
    privacy_guarantee: str
    readiness_issues: tuple[str, ...]


def infer_assistant_mode_from_legacy(payload: dict[str, object]) -> str:
    voice_mode = str(payload.get("voice_mode", "")).strip().lower()
    ai_mode = str(payload.get("ai_mode", "")).strip().lower()
    ai_provider = str(payload.get("ai_provider", "")).strip().lower()

    if voice_mode == "private":
        return "private"
    if voice_mode == "quality" or (ai_provider == "gemini" and ai_mode == "quality"):
        return "smart"
    if voice_mode == "fast" or ai_mode == "fast":
        return "fast"
    return "standard"


def resolve_assistant_mode(settings_service) -> str:
    configured = str(settings_service.get("assistant_mode", "")).strip().lower()
    if configured in ASSISTANT_MODES:
        return configured
    payload = {
        "ai_mode": settings_service.get("ai_mode", "auto"),
        "ai_provider": settings_service.get("ai_provider", "auto"),
        "voice_mode": settings_service.get("voice_mode", "balance"),
    }
    return infer_assistant_mode_from_legacy(payload)


def local_llama_ready(settings_service) -> bool:
    return LocalLLMService(settings_service).status().ready


def resolve_assistant_policy(settings_service, readiness: AssistantReadiness | None = None) -> AssistantPolicy:
    mode = resolve_assistant_mode(settings_service)
    readiness = readiness or AssistantReadiness(local_llama_ready=local_llama_ready(settings_service))

    text_route: tuple[str, ...]
    stt_route: tuple[str, ...]
    text_cloud_allowed = True
    stt_cloud_allowed = True
    privacy = "local_first_with_fallback"

    if mode == "fast":
        text_route = ("groq", "cerebras", "openrouter")
        stt_route = ("groq_whisper", "local_faster_whisper", "local_vosk")
        privacy = "cloud_first"
    elif mode == "smart":
        text_route = ("gemini", "groq", "cerebras", "openrouter")
        stt_route = ("groq_whisper", "local_faster_whisper", "local_vosk")
        privacy = "quality_first"
    elif mode == "private":
        text_route = ("local_llama",)
        stt_route = ("local_faster_whisper", "local_vosk")
        text_cloud_allowed = False
        stt_cloud_allowed = False
        privacy = "no_cloud_ever"
    else:
        text_route = ("local_llama", "groq", "cerebras", "openrouter")
        stt_route = ("local_faster_whisper", "local_vosk", "groq_whisper")

    text_override = str(settings_service.get("text_backend_override", "auto")).strip().lower()
    if text_override in TEXT_OVERRIDES and text_override != "auto":
        text_route = ("local_llama",) if text_override == "local_llama" else (text_override,)

    stt_override = str(settings_service.get("stt_backend_override", "auto")).strip().lower()
    if stt_override in STT_OVERRIDES and stt_override != "auto":
        stt_route = (stt_override,)

    allow_text_cloud_fallback = bool(settings_service.get("allow_text_cloud_fallback", True))
    allow_stt_cloud_fallback = bool(settings_service.get("allow_stt_cloud_fallback", True))
    if mode == "private":
        allow_text_cloud_fallback = False
        allow_stt_cloud_fallback = False

    if not allow_text_cloud_fallback:
        text_route = tuple(step for step in text_route if step == "local_llama")
        text_cloud_allowed = False
    else:
        text_cloud_allowed = any(step != "local_llama" for step in text_route)

    if not allow_stt_cloud_fallback:
        stt_route = tuple(step for step in stt_route if step != "groq_whisper")
        stt_cloud_allowed = False
    else:
        stt_cloud_allowed = any(step == "groq_whisper" for step in stt_route)

    issues: list[str] = []
    if "local_llama" in text_route and not readiness.local_llama_ready:
        issues.append("local_llama_missing")
    if "local_faster_whisper" in stt_route and not readiness.local_faster_whisper_ready:
        issues.append("local_faster_whisper_missing")
    if "local_vosk" in stt_route and not readiness.local_vosk_ready:
        issues.append("local_vosk_missing")

    return AssistantPolicy(
        mode=mode,
        text_route=text_route,
        stt_route=stt_route,
        text_cloud_allowed=text_cloud_allowed,
        stt_cloud_allowed=stt_cloud_allowed,
        privacy_guarantee=privacy,
        readiness_issues=tuple(issues),
    )

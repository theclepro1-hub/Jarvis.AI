from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.policy.assistant_mode import AssistantReadiness, local_llama_ready, resolve_assistant_policy


SUPPORTED_ASSISTANT_MODES = ("fast", "standard", "smart", "private")
SUPPORTED_ASSISTANT_MODE_SET = frozenset(SUPPORTED_ASSISTANT_MODES)
SUPPORTED_LEGACY_AI_MODES = ("auto", "fast", "quality", "local")
SUPPORTED_LEGACY_AI_MODE_SET = frozenset(SUPPORTED_LEGACY_AI_MODES)
SUPPORTED_TEXT_PROVIDERS = ("groq", "cerebras", "gemini", "openrouter")
SUPPORTED_TEXT_PROVIDER_SET = frozenset(SUPPORTED_TEXT_PROVIDERS)

DEFAULT_ASSISTANT_MODE = "standard"
DEFAULT_LEGACY_AI_MODE = "auto"

ASSISTANT_MODE_TO_LEGACY_AI_MODE: dict[str, str] = {
    "fast": "fast",
    "standard": "auto",
    "smart": "quality",
    "private": "local",
}

LEGACY_AI_MODE_TO_ASSISTANT_MODE: dict[str, str] = {
    "auto": "standard",
    "fast": "fast",
    "quality": "smart",
    "local": "private",
}

ASSISTANT_MODE_TO_REQUEST_PROFILE: dict[str, str] = {
    "fast": "fast",
    "standard": "auto",
    "smart": "quality",
    "private": "auto",
}


@dataclass(frozen=True, slots=True)
class ResolvedTextAIRoute:
    assistant_mode: str
    legacy_mode: str
    source: str
    request_profile: str
    provider_route: tuple[str, ...]
    cloud_allowed: bool
    privacy_guarantee: str
    summary: str


def resolve_text_ai_route(
    settings: Any,
    *,
    mode_hint: str | None = None,
    provider_hint: str | None = None,
) -> ResolvedTextAIRoute:
    assistant_mode, legacy_mode, source = _resolve_mode(settings, mode_hint)
    policy = resolve_assistant_policy(
        settings,
        readiness=AssistantReadiness(
            local_llama_ready=local_llama_ready(settings),
            local_faster_whisper_ready=True,
            local_vosk_ready=True,
        ),
    )
    provider = _normalize_provider(provider_hint)
    legacy_provider = _normalize_provider(_setting(settings, "ai_provider", "auto"))
    if not provider:
        if assistant_mode == "smart" and not mode_hint:
            provider = ""
        else:
            provider = legacy_provider

    if assistant_mode == "private":
        provider_route = ("local_llama",)
    elif provider and provider != "auto":
        provider_route = (provider,)
    else:
        provider_route = policy.text_route

    return ResolvedTextAIRoute(
        assistant_mode=assistant_mode,
        legacy_mode=legacy_mode,
        source=source,
        request_profile=ASSISTANT_MODE_TO_REQUEST_PROFILE[assistant_mode],
        provider_route=provider_route,
        cloud_allowed=policy.text_cloud_allowed,
        privacy_guarantee=policy.privacy_guarantee,
        summary=policy.display_summary,
    )


def normalize_assistant_mode(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered in SUPPORTED_ASSISTANT_MODE_SET:
        return lowered
    return ""


def normalize_legacy_ai_mode(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered in SUPPORTED_LEGACY_AI_MODE_SET:
        return lowered
    return ""


def _resolve_mode(settings: Any, mode_hint: str | None) -> tuple[str, str, str]:
    assistant_mode = normalize_assistant_mode(mode_hint)
    if assistant_mode:
        return assistant_mode, ASSISTANT_MODE_TO_LEGACY_AI_MODE[assistant_mode], "requested_mode"

    legacy_mode = normalize_legacy_ai_mode(mode_hint)
    if legacy_mode:
        return LEGACY_AI_MODE_TO_ASSISTANT_MODE[legacy_mode], legacy_mode, "requested_mode"

    assistant_mode = normalize_assistant_mode(_setting(settings, "assistant_mode", ""))
    if assistant_mode:
        return assistant_mode, ASSISTANT_MODE_TO_LEGACY_AI_MODE[assistant_mode], "assistant_mode"

    raw_legacy_mode = _setting(settings, "ai_mode", DEFAULT_LEGACY_AI_MODE)
    legacy_mode = normalize_legacy_ai_mode(raw_legacy_mode)
    if legacy_mode:
        return LEGACY_AI_MODE_TO_ASSISTANT_MODE[legacy_mode], legacy_mode, "legacy_ai_mode"

    return DEFAULT_ASSISTANT_MODE, DEFAULT_LEGACY_AI_MODE, "default"


def _normalize_provider(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    if lowered == "auto":
        return lowered
    if lowered in SUPPORTED_TEXT_PROVIDER_SET:
        return lowered
    return ""


def _setting(settings: Any, key: str, default: Any) -> Any:
    if isinstance(settings, Mapping):
        return settings.get(key, default)
    getter = getattr(settings, "get", None)
    if callable(getter):
        return getter(key, default)
    return default

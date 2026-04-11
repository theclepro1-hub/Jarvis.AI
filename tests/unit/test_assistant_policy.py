from __future__ import annotations

import pytest

from core.policy.assistant_mode import (
    AssistantReadiness,
    infer_assistant_mode_from_legacy,
    local_llama_ready,
    resolve_assistant_mode,
    resolve_assistant_policy,
)


def _ready_policy_settings(**overrides):
    base = {
        "assistant_mode": "standard",
        "allow_text_cloud_fallback": True,
        "allow_stt_cloud_fallback": True,
    }
    base.update(overrides)
    return base


def test_private_policy_never_allows_cloud_routes() -> None:
    policy = resolve_assistant_policy(
        _ready_policy_settings(assistant_mode="private"),
        readiness=AssistantReadiness(
            local_llama_ready=True,
            local_faster_whisper_ready=True,
            local_vosk_ready=True,
        ),
    )

    assert policy.mode == "private"
    assert policy.privacy_guarantee == "no_cloud_ever"
    assert policy.text_route == ("local_llama",)
    assert policy.stt_route == ("local_faster_whisper", "local_vosk")
    assert policy.cloud_allowed is False
    assert policy.text_cloud_allowed is False
    assert policy.stt_cloud_allowed is False


def test_private_policy_ignores_cloud_override_hints() -> None:
    policy = resolve_assistant_policy(
        _ready_policy_settings(
            assistant_mode="private",
            text_backend_override="openrouter",
            stt_backend_override="groq_whisper",
        ),
        readiness=AssistantReadiness(
            local_llama_ready=True,
            local_faster_whisper_ready=True,
            local_vosk_ready=True,
        ),
    )

    assert policy.mode == "private"
    assert policy.text_route == ("local_llama",)
    assert policy.stt_route == ("local_faster_whisper", "local_vosk")
    assert policy.cloud_allowed is False
    assert policy.text_cloud_allowed is False
    assert policy.stt_cloud_allowed is False


def test_standard_policy_prefers_local_then_cloud() -> None:
    policy = resolve_assistant_policy(
        _ready_policy_settings(assistant_mode="standard"),
        readiness=AssistantReadiness(
            local_llama_ready=True,
            local_faster_whisper_ready=True,
            local_vosk_ready=True,
        ),
    )

    assert policy.mode == "standard"
    assert policy.privacy_guarantee == "local_first_with_fallback"
    assert policy.text_route == ("local_llama", "groq", "cerebras", "openrouter")
    assert policy.stt_route == ("local_faster_whisper", "local_vosk", "groq_whisper")
    assert policy.cloud_allowed is True


def test_fast_policy_uses_cloud_first_without_heavy_local_first() -> None:
    policy = resolve_assistant_policy(
        _ready_policy_settings(assistant_mode="fast"),
        readiness=AssistantReadiness(
            local_llama_ready=True,
            local_faster_whisper_ready=True,
            local_vosk_ready=True,
        ),
    )

    assert policy.mode == "fast"
    assert policy.privacy_guarantee == "cloud_first"
    assert policy.text_route == ("groq", "cerebras", "openrouter")
    assert policy.stt_route[0] == "groq_whisper"
    assert "local_llama" not in policy.text_route[:1]


def test_standard_policy_reports_local_degradation_when_models_are_missing() -> None:
    policy = resolve_assistant_policy(
        _ready_policy_settings(assistant_mode="standard"),
        readiness=AssistantReadiness(
            local_llama_ready=False,
            local_faster_whisper_ready=False,
            local_vosk_ready=False,
        ),
    )

    assert policy.mode == "standard"
    assert policy.readiness_issues == (
        "local_llama_missing",
        "local_faster_whisper_missing",
        "local_vosk_missing",
    )
    assert "fallback" in policy.display_summary.casefold()


def test_local_llama_ready_delegates_to_backend_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLocalLLMService:
        def __init__(self, settings) -> None:  # noqa: ANN001
            self.settings = settings

        def status(self):  # noqa: ANN201
            return type("Status", (), {"ready": bool(self.settings.get("ready", False))})()

    monkeypatch.setattr("core.policy.assistant_mode.LocalLLMService", FakeLocalLLMService)

    assert local_llama_ready({"ready": True, "local_llm_backend": "ollama"}) is True
    assert local_llama_ready({"ready": False, "local_llm_backend": "ollama"}) is False


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({"voice_mode": "private"}, "private"),
        ({"voice_mode": "balance"}, "standard"),
        ({"voice_mode": "quality"}, "smart"),
        ({"ai_mode": "local"}, "private"),
        ({"ai_mode": "quality"}, "smart"),
        ({"ai_provider": "gemini"}, "smart"),
        ({"ai_mode": "fast"}, "fast"),
        ({"ai_provider": "groq"}, "fast"),
        ({"ai_provider": "cerebras"}, "fast"),
        ({}, "standard"),
    ],
)
def test_legacy_settings_migrate_to_assistant_mode(settings: dict[str, str], expected: str) -> None:
    assert infer_assistant_mode_from_legacy(settings) == expected


def test_explicit_assistant_mode_wins_over_legacy_values() -> None:
    assert (
        resolve_assistant_mode(
            {
                "assistant_mode": "private",
                "voice_mode": "quality",
                "ai_mode": "fast",
                "ai_provider": "gemini",
            }
        )
        == "private"
    )

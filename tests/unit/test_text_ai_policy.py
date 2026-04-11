from __future__ import annotations

import pytest

from core.routing.text_ai_policy import resolve_text_ai_route


def _settings(**overrides):
    return {
        "ai_mode": "auto",
        "ai_provider": "auto",
        **overrides,
    }


def test_explicit_assistant_mode_wins_over_legacy_ai_mode() -> None:
    route = resolve_text_ai_route(_settings(ai_mode="fast", assistant_mode="smart"))

    assert route.assistant_mode == "smart"
    assert route.legacy_mode == "quality"
    assert route.source == "assistant_mode"
    assert route.request_profile == "quality"
    assert route.provider_route[:2] == ("gemini", "groq")


@pytest.mark.parametrize(
    ("legacy_mode", "assistant_mode"),
    [
        ("auto", "standard"),
        ("fast", "fast"),
        ("quality", "smart"),
        ("local", "private"),
    ],
)
def test_legacy_ai_modes_map_to_assistant_modes(legacy_mode: str, assistant_mode: str) -> None:
    route = resolve_text_ai_route(_settings(ai_mode=legacy_mode))

    assert route.assistant_mode == assistant_mode
    assert route.legacy_mode == legacy_mode
    assert route.source == "legacy_ai_mode"


def test_private_mode_disables_cloud_and_ignores_manual_provider() -> None:
    route = resolve_text_ai_route(
        _settings(assistant_mode="private", ai_provider="gemini"),
    )

    assert route.assistant_mode == "private"
    assert route.provider_route == ("local_llama",)
    assert route.cloud_allowed is False
    assert route.privacy_guarantee == "no_cloud_ever"
    assert route.summary


def test_manual_provider_override_is_kept_for_cloud_modes() -> None:
    route = resolve_text_ai_route(
        _settings(assistant_mode="standard", ai_provider="openrouter"),
    )

    assert route.assistant_mode == "standard"
    assert route.provider_route == ("openrouter",)
    assert route.request_profile == "auto"


def test_standard_mode_uses_local_llama_first_when_provider_is_auto() -> None:
    route = resolve_text_ai_route(
        _settings(assistant_mode="standard"),
    )

    assert route.assistant_mode == "standard"
    assert route.provider_route[:2] == ("local_llama", "groq")

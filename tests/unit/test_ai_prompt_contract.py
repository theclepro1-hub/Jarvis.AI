from __future__ import annotations

from core.ai.ai_service import SYSTEM_PROMPT


def test_ai_prompt_forbids_fake_action_claims():
    assert "не утверждай, что оно уже выполнено" in SYSTEM_PROMPT

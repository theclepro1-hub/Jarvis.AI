from __future__ import annotations

from core.ai.ai_service import SYSTEM_PROMPT


def test_ai_prompt_forbids_fake_action_claims():
    assert "не утверждай, что оно уже выполнено" in SYSTEM_PROMPT


def test_ai_prompt_discourages_tables_and_long_answers():
    assert "markdown-таблицы" in SYSTEM_PROMPT
    assert "один короткий вопрос" in SYSTEM_PROMPT

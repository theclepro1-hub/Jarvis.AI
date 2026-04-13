from __future__ import annotations

from core.ai.ai_service import SYSTEM_PROMPT


def test_ai_prompt_forbids_fake_action_claims():
    assert "не утверждай, что оно уже выполнено" in SYSTEM_PROMPT


def test_ai_prompt_discourages_tables_and_long_answers():
    assert "markdown-таблицы" in SYSTEM_PROMPT
    assert "Один короткий уточняющий вопрос" in SYSTEM_PROMPT


def test_ai_prompt_keeps_reply_language_and_discourages_unnecessary_clarification():
    assert "Отвечай на языке пользователя" in SYSTEM_PROMPT
    assert "не переходи на английский" in SYSTEM_PROMPT
    assert "не переводи такие запросы сразу в уточнение" in SYSTEM_PROMPT.casefold()

from jarvis_ai.commands import detect_passive_wake_word
from jarvis_ai.state import _is_learned_pattern_generic


def test_detect_passive_wake_word_accepts_clean_prefix():
    detected, matched = detect_passive_wake_word("джарвис открой ютуб")
    assert detected is True
    assert matched


def test_detect_passive_wake_word_accepts_polite_prefix():
    detected, matched = detect_passive_wake_word("эй джарвис открой музыку")
    assert detected is True
    assert matched


def test_detect_passive_wake_word_ignores_mid_sentence_mentions():
    detected, matched = detect_passive_wake_word("мы с другом обсуждали джарвис и dead by daylight")
    assert detected is False
    assert matched == ""


def test_detect_passive_wake_word_keeps_common_misheard_variant():
    detected, matched = detect_passive_wake_word("дарвис открой музыку")
    assert detected is True
    assert matched


def test_learned_pattern_guard_rejects_router_prompt_garbage():
    pattern = (
        "правило маршрутизации: если запрос можно понять как локальную команду windows, "
        "ответи json-командой. если это обычный разговор или нужна логика/объяснение, "
        "ответи json-чатом. запрос пользователя: то зайди в проект сомния."
    )
    assert _is_learned_pattern_generic(pattern) is True

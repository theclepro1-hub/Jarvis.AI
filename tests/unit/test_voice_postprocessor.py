from __future__ import annotations

from core.intent.voice_postprocessor import VoiceCommandPostProcessor


class _ActionRegistryStub:
    def split_open_target_sequence(self, chunk: str):
        return [], ""

    def resolve_open_command(self, text: str):
        return [], ""


def test_voice_postprocessor_normalizes_common_open_mishears():
    processor = VoiceCommandPostProcessor(_ActionRegistryStub())

    assert processor.normalize("откры ютуб").normalized == "открой ютуб"
    assert processor.normalize("откри браузер").normalized == "открой браузер"
    assert processor.normalize("сотру ютуб").normalized == "открой ютуб"
    assert processor.normalize("сорту ютуб").normalized == "открой ютуб"
    assert processor.normalize("сокрыт тупо").normalized == "открой ютуб"
    assert processor.normalize("вскрою ютуб").normalized == "открой ютуб"


def test_voice_postprocessor_strips_noise_before_trailing_action_token():
    processor = VoiceCommandPostProcessor(_ActionRegistryStub())

    assert processor.normalize("радость громче").normalized == "громче"
    assert processor.normalize("потом тише").normalized == "тише"

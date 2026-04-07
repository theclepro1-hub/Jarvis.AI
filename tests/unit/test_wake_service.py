from __future__ import annotations

import json
import sys

from core.settings.settings_service import SettingsService
from core.voice.voice_service import VoiceService
from core.voice.wake_service import WakeService


class FakeStore:
    def __init__(self) -> None:
        self.payload = {
            "theme_mode": "midnight",
            "startup_enabled": False,
            "privacy_mode": "balance",
            "ai_provider": "groq",
            "ai_model": "openai/gpt-oss-20b",
            "voice_mode": "balance",
            "command_style": "one_shot",
            "wake_word_enabled": True,
            "microphone_name": "Системный по умолчанию",
            "registration": {
                "groq_api_key": "",
                "telegram_user_id": "",
                "telegram_bot_token": "",
                "skipped": False,
            },
            "custom_apps": [],
        }

    def load(self):
        return self.payload.copy()

    def save(self, payload):
        self.payload = payload


def test_wake_service_detects_wake_word_in_partial_payload():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    payload = json.dumps({"partial": "джарвис открой steam"}, ensure_ascii=False)
    assert wake._contains_wake(payload, partial=True) is True  # noqa: SLF001


def test_wake_service_ignores_non_matching_payload():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    payload = json.dumps({"text": "просто разговор"}, ensure_ascii=False)
    assert wake._contains_wake(payload) is False  # noqa: SLF001


def test_wake_service_reports_missing_model_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    result = wake.start(lambda _pre_roll: None)

    assert wake.phase == "error"
    assert "wake-модель" in result
    assert "wake-модель" in wake.status()


def test_wake_service_prefers_bundled_model_path(tmp_path, monkeypatch):
    bundled_model = tmp_path / "assets" / "models" / "vosk-model-small-ru-0.22"
    bundled_model.mkdir(parents=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake.model_path == bundled_model


def test_wake_service_reports_transcribing_status_truthfully():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    wake._set_phase("transcribing", "Распознаю команду", ready=False)  # noqa: SLF001

    assert wake.phase == "transcribing"
    assert wake.status() == "Распознаю команду"
    assert voice.runtime_status()["wakeWord"] == "Распознаю команду"

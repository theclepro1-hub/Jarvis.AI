from __future__ import annotations

import json
import queue
import sys

from core.settings.settings_service import SettingsService
from core.voice.model_paths import MODEL_DIR_NAME
from core.voice.voice_service import VoiceService
from core.voice.wake_service import WakeService
from core.voice.vosk_runtime import clear_vosk_model_cache


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
            "microphone_name": "Системный микрофон",
            "voice_output_name": "Системный вывод",
            "voice_response_enabled": False,
            "tts_engine": "system",
            "tts_voice_name": "Голос по умолчанию",
            "tts_rate": 185,
            "tts_volume": 85,
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
    alias_payload = json.dumps({"partial": "жарвис открой steam"}, ensure_ascii=False)
    assert wake._contains_wake(alias_payload, partial=True) is True  # noqa: SLF001


def test_wake_service_accepts_common_wake_mishears_in_partial_payload():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    payload = json.dumps({"partial": "гарви с открой steam"}, ensure_ascii=False)
    assert wake._contains_wake(payload, partial=True) is True  # noqa: SLF001
    short_alias_payload = json.dumps({"partial": "гарви открой steam"}, ensure_ascii=False)
    assert wake._contains_wake(short_alias_payload, partial=True) is True  # noqa: SLF001
    clipped_alias_payload = json.dumps({"partial": "джарви открой steam"}, ensure_ascii=False)
    assert wake._contains_wake(clipped_alias_payload, partial=True) is True  # noqa: SLF001


def test_wake_service_ignores_non_matching_payload():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    payload = json.dumps({"text": "просто разговор"}, ensure_ascii=False)
    assert wake._contains_wake(payload) is False  # noqa: SLF001


def test_wake_service_reports_missing_model_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("core.voice.model_paths._repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr("core.voice.wake_service.is_vosk_model_ready", lambda _path: False)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    result = wake.start(lambda _pre_roll: None)

    assert wake.phase == "error"
    assert "модель слова активации" in result
    assert "модель слова активации" in wake.status()


def test_wake_service_prefers_bundled_model_path(tmp_path, monkeypatch):
    bundled_model = tmp_path / "assets" / "models" / "vosk-model-small-ru-0.22"
    bundled_model.mkdir(parents=True)
    for relative_path in ("am/final.mdl", "conf/model.conf", "graph/Gr.fst", "ivector/final.ie"):
        target = bundled_model / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake.model_path == bundled_model


def test_wake_service_prefers_repo_model_cache_before_user_fallback(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    cached_model = repo_root / "build" / "model_cache" / MODEL_DIR_NAME
    cached_model.mkdir(parents=True)
    for relative_path in ("am/final.mdl", "conf/model.conf", "graph/Gr.fst", "ivector/final.ie"):
        target = cached_model / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test")
    monkeypatch.setattr("core.voice.model_paths._repo_root", lambda: repo_root)
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake.model_path == cached_model


def test_wake_service_uses_local_appdata_for_user_model_path(monkeypatch, tmp_path):
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    assert wake.user_model_path == tmp_path / "JarvisAi_Unity" / "models" / "vosk-model-small-ru-0.22"


def test_wake_service_reports_transcribing_status_truthfully():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    wake._set_phase("transcribing", "Распознаю команду", ready=False)  # noqa: SLF001

    assert wake.phase == "transcribing"
    assert wake.status() == "Распознаю команду"
    assert voice.runtime_status()["wakeWord"] == "Распознаю команду"


def test_wake_service_collects_short_post_wake_bridge():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    audio_queue: queue.Queue[bytes] = queue.Queue()
    audio_queue.put(b"a")
    audio_queue.put(b"b")

    bridge = wake._collect_post_wake_bridge(audio_queue)  # noqa: SLF001

    assert bridge == b"ab"


def test_wake_service_marks_capture_phase_as_handoff():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)

    wake._phase = "capturing_command"  # noqa: SLF001
    assert wake._phase_in_handoff() is True  # noqa: SLF001

    wake._phase = "idle"  # noqa: SLF001
    assert wake._phase_in_handoff() is False  # noqa: SLF001


def test_wake_service_uses_shared_vosk_runtime_cache(tmp_path, monkeypatch):
    clear_vosk_model_cache()
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    wake.model_path = tmp_path / "vosk-model-small-ru-0.22"
    wake.model_path.mkdir(parents=True)

    calls: list[tuple[object, ...]] = []

    class DummyRecognizer:
        pass

    def fake_new_recognizer(path, sample_rate, grammar=None):  # noqa: ANN001, ANN202
        calls.append((path, sample_rate, tuple(grammar or ())))
        return DummyRecognizer()

    monkeypatch.setattr("core.voice.wake_service.new_vosk_recognizer", fake_new_recognizer)

    recognizer = wake._new_recognizer()  # noqa: SLF001

    assert isinstance(recognizer, DummyRecognizer)
    assert len(calls) == 1
    assert calls[0][0] == wake.model_path
    assert calls[0][1] == wake.SAMPLE_RATE
    assert "\u0434\u0436\u0430\u0440\u0432\u0438\u0441" in calls[0][2]


def test_voice_service_reports_handoff_honestly_after_wake_session():
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)

    voice.begin_wake_session(b"pcm", wake_backend="vosk")
    voice.mark_wake_stt_started()
    voice.mark_wake_route_handoff()

    metrics = voice.latest_wake_metrics()

    assert metrics["routeHookSeen"] is True
    assert metrics["finalStatus"] == "handoff"
    assert "handoff" in voice.latest_wake_metrics_summary()
    assert voice.wake_status_text() == "Команда распознана. Передаю в обработку"

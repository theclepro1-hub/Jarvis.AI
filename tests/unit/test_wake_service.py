from __future__ import annotations

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
            "microphone_name": "Системный микрофон",
            "voice_output_name": "Системный вывод",
            "voice_response_enabled": False,
            "tts_engine": "system",
            "tts_voice_name": "Голос по умолчанию",
            "tts_rate": 185,
            "tts_volume": 85,
            "stt_local_model": "small",
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


class FakeWakeRuntime:
    def __init__(self, *, package: bool = True, model: bool = True, load: bool = True) -> None:
        self.package = package
        self.model = model
        self.load_result = load
        self.load_calls = 0
        self.reset_calls = 0
        self.last_error = ""

    def package_available(self) -> bool:
        return self.package

    def has_model(self) -> bool:
        return self.model

    def load(self) -> bool:
        self.load_calls += 1
        if not self.load_result:
            self.last_error = "load failed"
        return self.load_result

    def reset(self) -> None:
        self.reset_calls += 1


def make_wake(runtime: FakeWakeRuntime | None = None) -> tuple[WakeService, VoiceService]:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    if runtime is not None:
        wake._runtime = runtime  # noqa: SLF001
    return wake, voice


def test_wake_service_uses_openwakeword_backend_name() -> None:
    wake, _voice = make_wake(FakeWakeRuntime())

    assert wake.backend_name == "openwakeword"


def test_wake_service_reports_missing_package() -> None:
    wake, _voice = make_wake(FakeWakeRuntime(package=False))

    result = wake.start(lambda _pre_roll: None)

    assert wake.phase == "error"
    assert "openWakeWord" in result
    assert wake.model_status() == "не установлен"


def test_wake_service_reports_missing_model() -> None:
    wake, _voice = make_wake(FakeWakeRuntime(model=False))

    result = wake.start(lambda _pre_roll: None)

    assert wake.phase == "error"
    assert "wake-модель" in result
    assert wake.model_status() == "не загружена"


def test_wake_service_warm_up_loads_openwakeword_runtime() -> None:
    runtime = FakeWakeRuntime()
    wake, _voice = make_wake(runtime)

    assert wake.warm_up_model() is True
    assert runtime.load_calls == 1


def test_wake_service_uses_local_appdata_for_user_model_path(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("JARVIS_UNITY_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    wake, _voice = make_wake(FakeWakeRuntime())

    assert wake.user_model_path == tmp_path / "JarvisAi_Unity" / "models" / "openwakeword"


def test_wake_service_model_path_setter_stores_custom_path(tmp_path) -> None:
    settings = SettingsService(FakeStore())
    voice = VoiceService(settings)
    wake = WakeService(settings, voice)
    custom = tmp_path / "jarvis.onnx"

    wake.model_path = custom

    assert settings.get("wake_model_path") == str(custom)
    assert wake._runtime is None  # noqa: SLF001


def test_wake_service_prediction_requires_patience_before_handoff(monkeypatch) -> None:
    wake, _voice = make_wake(FakeWakeRuntime())
    captured: list[bytes] = []
    wake._callback = captured.append  # noqa: SLF001
    wake._buffer.append(b"before")  # noqa: SLF001
    wake._buffer.append(b"wake")  # noqa: SLF001
    monkeypatch.setattr(wake, "_wake_threshold", lambda: 0.5)
    monkeypatch.setattr(wake, "_wake_patience_frames", lambda: 2)

    assert wake._handle_prediction({"hey_jarvis": 0.7}) is False  # noqa: SLF001
    assert captured == []

    assert wake._handle_prediction({"hey_jarvis": 0.8}) is True  # noqa: SLF001
    assert captured == [b"beforewake"]
    assert wake.phase == "capturing_command"


def test_wake_service_prediction_ignores_low_score(monkeypatch) -> None:
    wake, _voice = make_wake(FakeWakeRuntime())
    captured: list[bytes] = []
    wake._callback = captured.append  # noqa: SLF001
    monkeypatch.setattr(wake, "_wake_threshold", lambda: 0.5)
    monkeypatch.setattr(wake, "_wake_patience_frames", lambda: 1)

    assert wake._handle_prediction({"hey_jarvis": 0.2}) is False  # noqa: SLF001

    assert captured == []
    assert wake.phase == "idle"


def test_wake_service_stop_cancels_active_voice_pipeline() -> None:
    wake, voice = make_wake(FakeWakeRuntime())
    calls: list[str] = []

    voice.cancel_active_pipeline = lambda: calls.append("cancelled")  # type: ignore[method-assign]

    wake.stop()

    assert calls == ["cancelled"]


def test_wake_service_marks_capture_phase_as_handoff() -> None:
    wake, _voice = make_wake(FakeWakeRuntime())

    wake._phase = "capturing_command"  # noqa: SLF001
    assert wake._phase_in_handoff() is True  # noqa: SLF001

    wake._phase = "idle"  # noqa: SLF001
    assert wake._phase_in_handoff() is False  # noqa: SLF001

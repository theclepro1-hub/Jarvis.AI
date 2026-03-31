import jarvis_ai.environment_doctor as doctor


class DummyConfig:
    def __init__(self):
        self._api_key = "groq-test"
        self._telegram_token = "tg-token"
        self._telegram_user_id = 42
        self._output_device_name = "Headphones"
        self._tts_provider = "pyttsx3"

    def get_api_key(self):
        return self._api_key

    def get_telegram_token(self):
        return self._telegram_token

    def get_telegram_user_id(self):
        return self._telegram_user_id

    def get_output_device_name(self):
        return self._output_device_name

    def get_tts_provider(self):
        return self._tts_provider


class DummyApp:
    def __init__(self):
        self._cfg_obj = DummyConfig()
        self.proxy_detected = False

    def _cfg(self):
        return self._cfg_obj

    def get_selected_microphone_name(self):
        return "USB Mic"

    def _tts_provider_ready_details(self, provider):
        return True, provider

    def check_internet(self):
        return True


def test_environment_doctor_happy_path(monkeypatch):
    app = DummyApp()
    monkeypatch.setattr(doctor, "list_input_device_entries_safe", lambda: [{"name": "USB Mic"}])
    monkeypatch.setattr(doctor, "list_output_device_entries_safe", lambda: [{"name": "Headphones"}])
    monkeypatch.setattr(doctor, "load_custom_action_entries", lambda: [{"name": "Docs"}])
    monkeypatch.setattr(
        doctor,
        "ffmpeg_runtime_status",
        lambda: {"has_ffmpeg": True, "has_ffplay": True, "found": {"ffmpeg": "C:/tools/ffmpeg.exe", "ffplay": "C:/tools/ffplay.exe"}},
    )
    monkeypatch.setattr(doctor, "describe_ffmpeg_runtime", lambda _status=None: "ffmpeg, ffplay")

    items = doctor.run_environment_doctor(app)
    summary = doctor.doctor_summary(items)
    report = doctor.render_doctor_report(items)

    assert any(item["title"] == "Ключ Groq" and item["status"] == "ok" for item in items)
    assert any(item["title"] == "ffmpeg" and item["status"] == "ok" for item in items)
    assert summary.startswith("Проверка среды:")
    assert "Ключ Groq" in report


def test_environment_doctor_warns_without_ffmpeg(monkeypatch):
    app = DummyApp()
    monkeypatch.setattr(doctor, "list_input_device_entries_safe", lambda: [{"name": "USB Mic"}])
    monkeypatch.setattr(doctor, "list_output_device_entries_safe", lambda: [{"name": "Headphones"}])
    monkeypatch.setattr(doctor, "load_custom_action_entries", lambda: [])
    monkeypatch.setattr(
        doctor,
        "ffmpeg_runtime_status",
        lambda: {"has_ffmpeg": False, "has_ffplay": False, "found": {}},
    )
    monkeypatch.setattr(doctor, "describe_ffmpeg_runtime", lambda _status=None: "ffmpeg не найден")

    items = doctor.run_environment_doctor(app)

    ffmpeg_item = next(item for item in items if item["title"] == "ffmpeg")
    assert ffmpeg_item["status"] == "warn"

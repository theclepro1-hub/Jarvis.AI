from types import SimpleNamespace

import jarvis_ai.scenario_engine as scenario_engine


class DummyApp:
    def __init__(self, mic_name: str = "USB Mic"):
        self._mic_name = mic_name

    def get_selected_microphone_name(self):
        return self._mic_name


def _fake_strftime(fmt: str) -> str:
    if fmt == "%H:%M":
        return "23:30"
    return "2026-03-29 23:30:00"


def test_explain_scenario_conditions_reports_match(monkeypatch):
    monkeypatch.setattr(scenario_engine.time, "strftime", _fake_strftime)
    monkeypatch.setattr(
        scenario_engine,
        "psutil",
        SimpleNamespace(process_iter=lambda _attrs=None: [SimpleNamespace(info={"name": "steam.exe"})]),
    )

    report = scenario_engine.explain_scenario_conditions(
        DummyApp(),
        {
            "name": "Игровой режим",
            "summary": "Включается вечером при Steam.",
            "conditions": {
                "time_after": "22:00",
                "process_any": ["steam.exe"],
                "mic_contains": "usb",
            },
        },
    )

    assert "Игровой режим" in report
    assert "Процессы: найдено совпадение" in report
    assert "Итог: все условия выполнены" in report


def test_explain_scenario_conditions_reports_missing_match(monkeypatch):
    monkeypatch.setattr(scenario_engine.time, "strftime", _fake_strftime)
    monkeypatch.setattr(
        scenario_engine,
        "psutil",
        SimpleNamespace(process_iter=lambda _attrs=None: [SimpleNamespace(info={"name": "discord.exe"})]),
    )

    report = scenario_engine.explain_scenario_conditions(
        DummyApp("Встроенный микрофон"),
        {
            "name": "Гарнитура",
            "summary": "Должен включаться только при гарнитуре и игре.",
            "conditions": {
                "process_any": ["steam.exe"],
                "mic_contains": "headset",
            },
        },
    )

    assert "совпадений нет" in report
    assert "Микрофон содержит" in report
    assert "Итог: не все условия выполнены" in report

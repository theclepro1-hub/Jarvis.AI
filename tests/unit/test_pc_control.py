from __future__ import annotations

from core.pc_control.media_control import MediaControl
from core.pc_control.service import PcControlService


class FakeActions:
    def open_items(self, items):
        return []


def test_media_control_uses_send_input_contract(monkeypatch):
    calls: list[int] = []

    monkeypatch.setattr(MediaControl, "_change_endpoint_volume", lambda self, action: False)

    def fake_send_input(self, virtual_key: int) -> bool:  # noqa: ANN001
        calls.append(virtual_key)
        return True

    monkeypatch.setattr(MediaControl, "_send_input", fake_send_input)

    media = MediaControl()

    assert media.volume_up() is True
    assert media.volume_down() is True
    assert media.mute() is True
    assert media.play_pause() is True
    assert media.next_track() is True
    assert media.previous_track() is True
    assert calls == [
        *([MediaControl.VK_VOLUME_UP] * MediaControl.VOLUME_KEY_FALLBACK_STEPS),
        *([MediaControl.VK_VOLUME_DOWN] * MediaControl.VOLUME_KEY_FALLBACK_STEPS),
        MediaControl.VK_VOLUME_MUTE,
        MediaControl.VK_MEDIA_PLAY_PAUSE,
        MediaControl.VK_MEDIA_NEXT_TRACK,
        MediaControl.VK_MEDIA_PREV_TRACK,
    ]


def test_media_control_prefers_endpoint_volume_for_volume(monkeypatch):
    calls: list[str] = []

    def fake_endpoint_volume(self, action: str) -> bool:  # noqa: ANN001
        calls.append(action)
        return True

    monkeypatch.setattr(MediaControl, "_change_endpoint_volume", fake_endpoint_volume)
    monkeypatch.setattr(MediaControl, "_send_input", lambda self, virtual_key: False)

    media = MediaControl()

    assert media.volume_up() is True
    assert media.volume_down() is True
    assert media.mute() is True
    assert media.play_pause() is False
    assert calls == ["up", "down", "mute"]


def test_pc_control_search_and_open_url_use_browser(monkeypatch):
    opened: list[str] = []

    monkeypatch.setattr("core.pc_control.browser_control.webbrowser.open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(MediaControl, "_change_endpoint_volume", lambda self, action: False)
    monkeypatch.setattr(MediaControl, "_send_input", lambda self, virtual_key: True)

    service = PcControlService(FakeActions())

    assert service.volume_up().success is True
    assert service.volume_down().success is True
    assert service.volume_mute().success is True
    assert service.search_web("чизбургер").success is True
    assert service.open_url("https://eda.yandex.ru/", "Яндекс Еда").success is True
    assert opened == [
        "https://www.google.com/search?q=%D1%87%D0%B8%D0%B7%D0%B1%D1%83%D1%80%D0%B3%D0%B5%D1%80",
        "https://eda.yandex.ru/",
    ]


def test_pc_control_media_keys_are_marked_sent_but_unverified(monkeypatch):
    monkeypatch.setattr(MediaControl, "_send_input", lambda self, virtual_key: True)

    service = PcControlService(FakeActions())

    play_pause = service.play_pause()
    next_track = service.next_track()
    previous_track = service.previous_track()

    assert play_pause.status == "sent_unverified"
    assert next_track.status == "sent_unverified"
    assert previous_track.status == "sent_unverified"
    assert "не подтверждает" in play_pause.detail


def test_pc_control_power_action_returns_failed_outcome_when_registry_raises(monkeypatch):
    class BrokenActions(FakeActions):
        def run_power_action(self, action: str, title: str):  # noqa: ANN001
            raise OSError("boom")

    monkeypatch.setattr(MediaControl, "_send_input", lambda self, virtual_key: True)
    service = PcControlService(BrokenActions())

    outcome = service.power_action("lock", "Блокирую экран")

    assert outcome.success is False
    assert outcome.title == "Не удалось: Блокирую экран"
    assert outcome.detail == "boom"

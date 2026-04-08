from __future__ import annotations

from pathlib import Path

from core.updates.update_service import UpdateService


def test_update_service_reports_update_available_and_assets(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "tag_name": "v22.2.0",
                "html_url": "https://example.test/releases/v22.2.0",
                "name": "JarvisAi Unity 22.2.0",
                "assets": [
                    {
                        "name": "JarvisAi_Unity_22.2.0_windows_installer.exe",
                        "browser_download_url": "https://example.test/installer.exe",
                    }
                ],
            }

    def fake_get(url, timeout, headers):  # noqa: ANN001, ANN202
        captured["url"] = url
        captured["timeout"] = timeout
        captured["headers"] = headers
        return Response()

    monkeypatch.setattr("core.updates.update_service.httpx.get", fake_get)
    service = UpdateService(settings=None, current_version="22.0.0")

    result = service.check_now()

    assert result.ok is True
    assert result.update_available is True
    assert result.latest_version == "22.2.0"
    assert result.release_url == "https://example.test/releases/v22.2.0"
    assert result.assets[0].name == "JarvisAi_Unity_22.2.0_windows_installer.exe"
    assert service.update_available() is True
    assert service.latest_version() == "22.2.0"
    assert service.release_url() == "https://example.test/releases/v22.2.0"
    assert service.summary() == "Доступна версия 22.2.0 · текущая 22.0.0"
    assert "api.github.com" in str(captured["url"])
    status = service.status_snapshot()
    assert status["can_apply"] is True
    assert status["preferred_installer_asset"] == "JarvisAi_Unity_22.2.0_windows_installer.exe"


def test_update_service_reports_error_honestly(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):  # noqa: ANN001, ANN202
        raise RuntimeError("network down")

    monkeypatch.setattr("core.updates.update_service.httpx.get", fake_get)
    service = UpdateService(settings=None, current_version="22.2.0")

    result = service.check_now()

    assert result.ok is False
    assert result.update_available is False
    assert result.latest_version == ""
    assert result.last_error.startswith("RuntimeError:")
    assert service.last_error().startswith("RuntimeError:")
    assert service.summary().startswith("Проверка обновлений: ошибка")


def test_apply_update_downloads_and_launches_installer(monkeypatch, tmp_path: Path) -> None:
    service = UpdateService(settings=None, current_version="22.0.0")
    service.assets = [
        type("Asset", (), {"name": "JarvisAi_Unity_22.2.0_windows_installer.exe", "browser_download_url": "https://example.test/installer.exe"})()
    ]
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)

    class FakeStream:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):  # noqa: ANN202
            yield b"binary-installer"

    def fake_stream(*_args, **_kwargs):  # noqa: ANN001, ANN202
        return FakeStream()

    launched: dict[str, object] = {}

    class DummyProc:
        pass

    def fake_popen(command, close_fds):  # noqa: ANN001, ANN202
        launched["command"] = command
        launched["close_fds"] = close_fds
        return DummyProc()

    monkeypatch.setattr("core.updates.update_service.httpx.stream", fake_stream)
    monkeypatch.setattr("core.updates.update_service.subprocess.Popen", fake_popen)

    result = service.apply_update()

    assert result.ok is True
    assert result.started is True
    assert result.asset_name.endswith("windows_installer.exe")
    assert Path(result.installer_path).exists()
    assert launched["close_fds"] is True
    assert "/CLOSEAPPLICATIONS" in launched["command"]
    assert "/RESTARTAPPLICATIONS" in launched["command"]


def test_apply_update_reports_manual_only_when_no_installer_asset() -> None:
    service = UpdateService(settings=None, current_version="22.0.0")
    service.assets = [
        type("Asset", (), {"name": "JarvisAi_Unity_22.2.0_windows_portable.zip", "browser_download_url": "https://example.test/portable.zip"})()
    ]

    result = service.apply_update()

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "installer_asset_missing"

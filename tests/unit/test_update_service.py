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
                "tag_name": "v22.3.0",
                "html_url": "https://example.test/releases/v22.3.0",
                "name": "JarvisAi Unity 22.3.0",
                "assets": [
                    {
                        "name": "JarvisAi_Unity_22.3.0_windows_installer.exe",
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
    service = UpdateService(settings=None, current_version="22.2.0")

    result = service.check_now()

    assert result.ok is True
    assert result.update_available is True
    assert result.latest_version == "22.3.0"
    assert result.release_url == "https://example.test/releases/v22.3.0"
    assert result.assets[0].name == "JarvisAi_Unity_22.3.0_windows_installer.exe"
    assert service.update_available() is True
    assert service.latest_version() == "22.3.0"
    assert service.release_url() == "https://example.test/releases/v22.3.0"
    assert service.summary() == "Доступна версия 22.3.0 · текущая 22.2.0"
    assert "api.github.com" in str(captured["url"])
    status = service.status_snapshot()
    assert status["can_apply"] is True
    assert status["preferred_installer_asset"] == "JarvisAi_Unity_22.3.0_windows_installer.exe"


def test_update_service_reports_error_honestly(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):  # noqa: ANN001, ANN202
        raise RuntimeError("network down")

    monkeypatch.setattr("core.updates.update_service.httpx.get", fake_get)
    service = UpdateService(settings=None, current_version="22.3.0")

    result = service.check_now()

    assert result.ok is False
    assert result.update_available is False
    assert result.latest_version == ""
    assert result.last_error.startswith("RuntimeError:")
    assert service.last_error().startswith("RuntimeError:")
    assert service.summary().startswith("Проверка обновлений: ошибка")


def test_apply_update_downloads_and_launches_installer(monkeypatch, tmp_path: Path) -> None:
    service = UpdateService(settings=None, current_version="22.2.0")
    service.assets = [
        type(
            "Asset",
            (),
            {
                "name": "JarvisAi_Unity_22.3.0_windows_installer.exe",
                "browser_download_url": "https://example.test/installer.exe",
            },
        )()
    ]
    service.latest_version_value = "22.3.0"
    service.update_available_value = True
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)

    class FakeStream:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN204
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, _chunk_size=0):  # noqa: ANN001, ANN202
            yield b"binary-installer"

    def fake_stream(*_args, **_kwargs):  # noqa: ANN001, ANN202
        return FakeStream()

    launched: dict[str, object] = {}

    class DummyProc:
        pid = 4242

        @staticmethod
        def poll():  # noqa: ANN205
            return None

    def fake_popen(command, close_fds, creationflags):  # noqa: ANN001, ANN202
        launched["command"] = command
        launched["close_fds"] = close_fds
        launched["creationflags"] = creationflags
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
    assert service.status_snapshot()["active_installer_pid"] == 4242


def test_apply_update_reports_manual_only_when_no_installer_asset() -> None:
    service = UpdateService(settings=None, current_version="22.2.0")
    service.assets = [
        type(
            "Asset",
            (),
            {
                "name": "JarvisAi_Unity_22.3.0_windows_portable.zip",
                "browser_download_url": "https://example.test/portable.zip",
            },
        )()
    ]
    service.latest_version_value = "22.3.0"
    service.update_available_value = True

    result = service.apply_update()

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "installer_asset_missing"


def test_apply_update_refuses_when_already_in_progress() -> None:
    service = UpdateService(settings=None, current_version="22.2.0")
    acquired = service._apply_lock.acquire(blocking=False)  # noqa: SLF001
    assert acquired is True
    try:
        result = service.apply_update()
    finally:
        service._apply_lock.release()  # noqa: SLF001

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "apply_in_progress"


def test_apply_update_refuses_when_installer_process_is_alive() -> None:
    service = UpdateService(settings=None, current_version="22.2.0")

    class RunningProc:
        pid = 501

        @staticmethod
        def poll():  # noqa: ANN205
            return None

    service._installer_process = RunningProc()  # noqa: SLF001

    result = service.apply_update()

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "installer_already_running"

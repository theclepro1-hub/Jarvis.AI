from __future__ import annotations

from pathlib import Path

from core.updates.update_service import UpdateAsset, UpdateService


def test_update_service_reports_installer_ready_when_release_has_installer(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "tag_name": "v22.3.5",
                "html_url": "https://example.test/releases/v22.3.5",
                "name": "JarvisAi Unity 22.3.5",
                "assets": [
                    {
                        "name": "JarvisAi_Unity_22.3.5_windows_installer.exe",
                        "browser_download_url": "https://example.test/installer.exe",
                    },
                    {
                        "name": "JarvisAi_Unity_22.3.5_windows_onefile.exe",
                        "browser_download_url": "https://example.test/onefile.exe",
                    },
                ],
            }

    def fake_get(url, timeout, headers):  # noqa: ANN001, ANN202
        captured["url"] = url
        captured["timeout"] = timeout
        captured["headers"] = headers
        return Response()

    monkeypatch.setattr("core.updates.update_service.httpx.get", fake_get)
    service = UpdateService(settings=None, current_version="22.3.0")

    result = service.check_now()

    assert result.ok is True
    assert result.update_available is True
    assert result.latest_version == "22.3.5"
    assert result.status_code == "update_ready"
    assert result.message == "Доступна версия 22.3.5 · можно установить поверх текущей."
    assert result.preferred_installer_asset == "JarvisAi_Unity_22.3.5_windows_installer.exe"
    assert result.can_apply is True
    assert service.summary() == "Доступна версия 22.3.5 · можно установить поверх текущей."
    assert "api.github.com" in str(captured["url"])

    snapshot = service.status_snapshot()
    assert snapshot["can_apply"] is True
    assert snapshot["preferred_installer_asset"] == "JarvisAi_Unity_22.3.5_windows_installer.exe"
    assert snapshot["manual_download_required"] is False
    assert snapshot["apply_mode"] == "installer"


def test_update_service_is_honest_when_release_has_only_manual_assets(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "tag_name": "v22.3.5",
                "html_url": "https://example.test/releases/v22.3.5",
                "assets": [
                    {
                        "name": "JarvisAi_Unity_22.3.5_windows_onefile.exe",
                        "browser_download_url": "https://example.test/onefile.exe",
                    },
                    {
                        "name": "JarvisAi_Unity_22.3.5_windows_portable.zip",
                        "browser_download_url": "https://example.test/portable.zip",
                    },
                ],
            }

    monkeypatch.setattr("core.updates.update_service.httpx.get", lambda *args, **kwargs: Response())
    service = UpdateService(settings=None, current_version="22.3.0")

    result = service.check_now()

    assert result.ok is True
    assert result.update_available is True
    assert result.status_code == "manual_only"
    assert result.preferred_installer_asset == ""
    assert result.can_apply is False
    assert "автоустановка недоступна" in result.message

    snapshot = service.status_snapshot()
    assert snapshot["can_apply"] is False
    assert snapshot["manual_download_required"] is True
    assert snapshot["apply_mode"] == "manual"
    assert "installer-asset" in snapshot["apply_hint"]


def test_update_service_reports_error_honestly(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):  # noqa: ANN001, ANN202
        raise RuntimeError("network down")

    monkeypatch.setattr("core.updates.update_service.httpx.get", fake_get)
    service = UpdateService(settings=None, current_version="22.3.5")

    result = service.check_now()

    assert result.ok is False
    assert result.update_available is False
    assert result.latest_version == ""
    assert result.last_error.startswith("RuntimeError:")
    assert result.status_code == "check_failed"
    assert service.last_error().startswith("RuntimeError:")
    assert service.summary() == "Проверка обновлений: ошибка."


def test_update_service_check_is_single_flight() -> None:
    service = UpdateService(settings=None, current_version="22.3.5")
    acquired = service._check_lock.acquire(blocking=False)  # noqa: SLF001
    assert acquired is True
    try:
        result = service.check_now()
    finally:
        service._check_lock.release()  # noqa: SLF001

    assert result.ok is False
    assert result.status_code == "check_in_progress"
    assert result.last_error == "check_in_progress"
    assert result.message == "Проверка обновлений уже выполняется."


def test_apply_update_downloads_and_launches_installer(monkeypatch, tmp_path: Path) -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.3.5_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
        )
    ]
    service.latest_version_value = "22.3.5"
    service.release_url_value = "https://example.test/releases/v22.3.5"
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
    assert result.status_code == "installer_started"
    assert result.asset_name.endswith("windows_installer.exe")
    assert Path(result.installer_path).exists()
    assert result.release_url == "https://example.test/releases/v22.3.5"
    assert launched["close_fds"] is True
    assert launched["command"][1:] == ["/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]
    assert service.status_snapshot()["active_installer_pid"] == 4242


def test_apply_update_reuses_existing_download(monkeypatch, tmp_path: Path) -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.3.5_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
        )
    ]
    service.latest_version_value = "22.3.5"
    service.release_url_value = "https://example.test/releases/v22.3.5"
    service.update_available_value = True
    cached_installer = tmp_path / "JarvisAi_Unity_22.3.5_windows_installer.exe"
    cached_installer.write_bytes(b"already-downloaded")
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "core.updates.update_service.httpx.stream",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("download should not run")),
    )

    class DummyProc:
        pid = 777

        @staticmethod
        def poll():  # noqa: ANN205
            return None

    monkeypatch.setattr(
        "core.updates.update_service.subprocess.Popen",
        lambda command, close_fds, creationflags: DummyProc(),
    )

    result = service.apply_update()

    assert result.ok is True
    assert result.installer_path == str(cached_installer.resolve())


def test_apply_update_is_manual_only_when_no_installer_asset() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.3.5_windows_onefile.exe",
            browser_download_url="https://example.test/onefile.exe",
        )
    ]
    service.latest_version_value = "22.3.5"
    service.release_url_value = "https://example.test/releases/v22.3.5"
    service.update_available_value = True

    result = service.apply_update()

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "installer_asset_missing"
    assert result.status_code == "manual_only"
    assert result.requires_manual_step is True
    assert result.release_url == "https://example.test/releases/v22.3.5"


def test_apply_update_refuses_when_check_is_running() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    acquired = service._check_lock.acquire(blocking=False)  # noqa: SLF001
    assert acquired is True
    try:
        result = service.apply_update()
    finally:
        service._check_lock.release()  # noqa: SLF001

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "check_in_progress"
    assert result.status_code == "check_in_progress"


def test_apply_update_refuses_when_already_in_progress() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    acquired = service._apply_lock.acquire(blocking=False)  # noqa: SLF001
    assert acquired is True
    try:
        result = service.apply_update()
    finally:
        service._apply_lock.release()  # noqa: SLF001

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "apply_in_progress"
    assert result.status_code == "apply_in_progress"


def test_apply_update_refuses_when_installer_process_is_alive() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")

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
    assert result.status_code == "installer_running"
    assert service.summary() == "Установщик обновления уже запущен."

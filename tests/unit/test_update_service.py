from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

import httpx

from core.updates.update_service import UpdateAsset, UpdateService


class _FakeResponse:
    def __init__(self, payload: dict[str, object] | None = None, *, body: bytes = b"binary-installer") -> None:
        self._payload = payload or {}
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload

    def iter_bytes(self, _chunk_size=0):  # noqa: ANN001, ANN202
        yield self._body


class _FakeHttpClient:
    def __init__(self, *, response: _FakeResponse, error: Exception | None = None, calls: list[tuple[str, object]] | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = calls if calls is not None else []

    def __enter__(self) -> _FakeHttpClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ANN204
        return False

    def get(self, url: str):  # noqa: ANN001
        self.calls.append(("get", url))
        if self.error is not None:
            raise self.error
        return self.response

    @contextmanager
    def stream(self, method: str, url: str):  # noqa: ANN001
        self.calls.append(("stream", method, url))
        if self.error is not None:
            raise self.error
        yield self.response


def _connect_error(url: str) -> httpx.ConnectError:
    return httpx.ConnectError("SSL: UNEXPECTED_EOF_WHILE_READING", request=httpx.Request("GET", url))


def test_update_service_reports_installer_ready_when_release_has_installer(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    digest = hashlib.sha256(b"binary-installer").hexdigest()

    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        _ = proxy_url
        calls.append(("client", trust_env))
        return _FakeHttpClient(
            response=_FakeResponse(
                {
                    "tag_name": "v22.4.1",
                    "html_url": "https://example.test/releases/v22.4.1",
                    "name": "JarvisAi Unity 22.4.1",
                    "assets": [
                        {
                            "name": "JarvisAi_Unity_22.4.1_windows_installer.exe",
                            "browser_download_url": "https://example.test/installer.exe",
                            "size": len(b"binary-installer"),
                            "digest": f"sha256:{digest}",
                        },
                        {
                            "name": "JarvisAi_Unity_22.4.1_windows_onefile.exe",
                            "browser_download_url": "https://example.test/onefile.exe",
                        },
                    ],
                },
                body=b"",
            ),
            calls=calls,
        )

    service = UpdateService(settings=None, current_version="22.3.0")
    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)

    result = service.check_now()

    assert result.ok is True
    assert result.update_available is True
    assert result.latest_version == "22.4.1"
    assert result.status_code == "update_ready"
    assert result.message == "Доступна версия 22.4.1 · можно установить поверх текущей."
    assert result.preferred_installer_asset == "JarvisAi_Unity_22.4.1_windows_installer.exe"
    assert result.can_apply is True
    assert result.assets[0].size == len(b"binary-installer")
    assert service.summary() == "Доступна версия 22.4.1 · можно установить поверх текущей."
    assert calls[0] == ("client", True)

    snapshot = service.status_snapshot()
    assert snapshot["can_apply"] is True
    assert snapshot["preferred_installer_asset"] == "JarvisAi_Unity_22.4.1_windows_installer.exe"
    assert snapshot["manual_download_required"] is False
    assert snapshot["apply_mode"] == "installer"


def test_update_service_is_honest_when_release_has_only_manual_assets(monkeypatch) -> None:
    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        _ = proxy_url, trust_env
        return _FakeHttpClient(
            response=_FakeResponse(
                {
                    "tag_name": "v22.4.1",
                    "html_url": "https://example.test/releases/v22.4.1",
                    "assets": [
                        {
                            "name": "JarvisAi_Unity_22.4.1_windows_onefile.exe",
                            "browser_download_url": "https://example.test/onefile.exe",
                        },
                        {
                            "name": "JarvisAi_Unity_22.4.1_windows_portable.zip",
                            "browser_download_url": "https://example.test/portable.zip",
                        },
                    ],
                },
                body=b"",
            )
        )

    service = UpdateService(settings=None, current_version="22.3.0")
    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)

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
    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        _ = proxy_url, trust_env
        return _FakeHttpClient(
            response=_FakeResponse(body=b""),
            error=_connect_error("https://api.github.com/repos/theclepro1-hub/Jarvis.AI/releases/latest"),
        )

    service = UpdateService(settings=None, current_version="22.4.1")
    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)

    result = service.check_now()

    assert result.ok is False
    assert result.update_available is False
    assert result.latest_version == ""
    assert result.last_error.startswith("ConnectError:")
    assert result.status_code == "check_failed"
    assert service.last_error().startswith("ConnectError:")
    assert service.summary() == "Проверка обновлений: ошибка."


def test_update_service_prefers_release_name_version_over_bridge_tag(monkeypatch) -> None:
    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        _ = proxy_url, trust_env
        return _FakeHttpClient(
            response=_FakeResponse(
                {
                    "tag_name": "v22.5.2",
                    "name": "20.5.0",
                    "html_url": "https://example.test/releases/20.5.0",
                    "assets": [
                        {
                            "name": "JarvisAi_Unity_20.5.0_windows_installer.exe",
                            "browser_download_url": "https://example.test/installer.exe",
                        }
                    ],
                },
                body=b"",
            )
        )

    service = UpdateService(settings=None, current_version="20.5.0")
    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)

    result = service.check_now()

    assert result.ok is True
    assert result.latest_version == "20.5.0"
    assert result.update_available is False
    assert service.summary().startswith("Версия 20.5.0")


def test_update_service_retries_transport_failure_before_succeeding(monkeypatch) -> None:
    attempts: list[tuple[bool, str]] = []
    digest = hashlib.sha256(b"binary-installer").hexdigest()
    payload = {
        "tag_name": "v22.4.1",
        "html_url": "https://example.test/releases/v22.4.1",
        "assets": [
            {
                "name": "JarvisAi_Unity_22.4.1_windows_installer.exe",
                "browser_download_url": "https://example.test/installer.exe",
                "size": len(b"binary-installer"),
                "digest": f"sha256:{digest}",
            }
        ],
    }
    first_url = "https://api.github.com/repos/theclepro1-hub/Jarvis.AI/releases/latest"

    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        attempts.append((trust_env, proxy_url))
        if len(attempts) == 1:
            return _FakeHttpClient(
                response=_FakeResponse(payload),
                error=_connect_error(first_url),
                calls=[],
            )
        return _FakeHttpClient(response=_FakeResponse(payload), calls=[])

    service = UpdateService(settings=None, current_version="22.3.0")
    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)

    result = service.check_now()

    assert result.ok is True
    assert result.latest_version == "22.4.1"
    assert attempts[:2] == [(True, ""), (False, "")]
    assert service.last_error() == ""


def test_update_service_check_is_single_flight() -> None:
    service = UpdateService(settings=None, current_version="22.4.1")
    acquired = service._check_lock.acquire(blocking=False)  # noqa: SLF001
    assert acquired is True
    try:
        result = service.check_now()
    finally:
        service._check_lock.release()  # noqa: SLF001

    assert result.ok is False
    assert result.status_code == "check_in_progress"
    assert result.last_error == "check_in_progress"


def test_update_service_requires_integrity_metadata_for_auto_apply() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"binary-installer"),
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True

    snapshot = service.status_snapshot()

    assert service.can_apply_update() is False
    assert snapshot["can_apply"] is False
    assert snapshot["manual_download_required"] is True
    assert snapshot["apply_mode"] == "manual"
    assert "checksum/digest" in snapshot["apply_hint"]


def test_apply_update_downloads_and_launches_installer(monkeypatch, tmp_path: Path) -> None:
    digest = hashlib.sha256(b"binary-installer").hexdigest()
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"binary-installer"),
            digest=f"sha256:{digest}",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)
    attempts: list[tuple[bool, str]] = []

    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        attempts.append((trust_env, proxy_url))
        if len(attempts) == 1:
            return _FakeHttpClient(
                response=_FakeResponse(body=b"binary-installer"),
                error=_connect_error("https://example.test/installer.exe"),
                calls=[],
            )
        return _FakeHttpClient(response=_FakeResponse(body=b"binary-installer"), calls=[])

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

    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)
    monkeypatch.setattr("core.updates.update_service.subprocess.Popen", fake_popen)

    result = service.apply_update()

    assert result.ok is True
    assert result.started is True
    assert result.status_code == "installer_started"
    assert result.asset_name.endswith("windows_installer.exe")
    assert Path(result.installer_path).exists()
    assert result.release_url == "https://example.test/releases/v22.4.1"
    assert attempts[:2] == [(True, ""), (False, "")]
    assert launched["close_fds"] is True
    assert launched["command"][1:] == ["/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]
    assert service.status_snapshot()["active_installer_pid"] == 4242


def test_apply_update_reuses_existing_download(monkeypatch, tmp_path: Path) -> None:
    digest = hashlib.sha256(b"already-downloaded").hexdigest()
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"already-downloaded"),
            digest=f"sha256:{digest}",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True
    cached_installer = tmp_path / "JarvisAi_Unity_22.4.1_windows_installer.exe"
    cached_installer.write_bytes(b"already-downloaded")
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)
    monkeypatch.setattr(
        service,
        "_create_http_client",
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


def test_apply_update_redownloads_stale_cached_installer_when_size_mismatch(monkeypatch, tmp_path: Path) -> None:
    digest = hashlib.sha256(b"binary-installer").hexdigest()
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"binary-installer"),
            digest=f"sha256:{digest}",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True
    cached_installer = tmp_path / "JarvisAi_Unity_22.4.1_windows_installer.exe"
    cached_installer.write_bytes(b"broken")
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)

    download_calls: list[str] = []

    def fake_create_http_client(*, proxy_url: str = "", trust_env: bool = True) -> _FakeHttpClient:
        _ = proxy_url, trust_env
        download_calls.append("download")
        return _FakeHttpClient(response=_FakeResponse(body=b"binary-installer"), calls=[])

    class DummyProc:
        pid = 778

        @staticmethod
        def poll():  # noqa: ANN205
            return None

    monkeypatch.setattr(service, "_create_http_client", fake_create_http_client)
    monkeypatch.setattr(
        "core.updates.update_service.subprocess.Popen",
        lambda command, close_fds, creationflags: DummyProc(),
    )

    result = service.apply_update()

    assert result.ok is True
    assert download_calls == ["download"]
    assert cached_installer.read_bytes() == b"binary-installer"


def test_apply_update_reports_corrupted_download_when_size_mismatch(monkeypatch, tmp_path: Path) -> None:
    digest = hashlib.sha256(b"binary-installer").hexdigest()
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"binary-installer"),
            digest=f"sha256:{digest}",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)
    monkeypatch.setattr(
        service,
        "_create_http_client",
        lambda *args, **kwargs: _FakeHttpClient(response=_FakeResponse(body=b"tiny"), calls=[]),
    )

    result = service.apply_update()

    assert result.ok is False
    assert result.status_code == "download_failed"
    assert "download_size_mismatch" in result.last_error
    assert not any(tmp_path.glob("*.download"))


def test_apply_update_verifies_checksum_when_sidecar_is_available(monkeypatch, tmp_path: Path) -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"binary-installer"),
        ),
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe.sha256.txt",
            browser_download_url="https://example.test/installer.exe.sha256.txt",
        ),
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)
    monkeypatch.setattr(
        service,
        "_expected_asset_sha256",
        lambda _asset: hashlib.sha256(b"binary-installer").hexdigest(),
    )
    monkeypatch.setattr(
        service,
        "_create_http_client",
        lambda *args, **kwargs: _FakeHttpClient(response=_FakeResponse(body=b"binary-installer"), calls=[]),
    )

    class DummyProc:
        pid = 779

        @staticmethod
        def poll():  # noqa: ANN205
            return None

    monkeypatch.setattr(
        "core.updates.update_service.subprocess.Popen",
        lambda command, close_fds, creationflags: DummyProc(),
    )

    result = service.apply_update()

    assert result.ok is True
    assert result.started is True
    assert Path(result.installer_path).read_bytes() == b"binary-installer"


def test_apply_update_verifies_release_digest_when_available(monkeypatch, tmp_path: Path) -> None:
    digest = hashlib.sha256(b"binary-installer").hexdigest()
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            size=len(b"binary-installer"),
            digest=f"sha256:{digest}",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True
    monkeypatch.setattr(service, "_update_download_dir", lambda: tmp_path)
    monkeypatch.setattr(
        service,
        "_create_http_client",
        lambda *args, **kwargs: _FakeHttpClient(response=_FakeResponse(body=b"binary-installer"), calls=[]),
    )

    class DummyProc:
        pid = 780

        @staticmethod
        def poll():  # noqa: ANN205
            return None

    monkeypatch.setattr(
        "core.updates.update_service.subprocess.Popen",
        lambda command, close_fds, creationflags: DummyProc(),
    )

    result = service.apply_update()

    assert result.ok is True
    assert result.started is True
    assert Path(result.installer_path).read_bytes() == b"binary-installer"


def test_apply_update_is_manual_only_when_no_installer_asset() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_onefile.exe",
            browser_download_url="https://example.test/onefile.exe",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True

    result = service.apply_update()

    assert result.ok is False
    assert result.started is False
    assert result.last_error == "installer_asset_missing"
    assert result.status_code == "manual_only"
    assert result.requires_manual_step is True
    assert result.release_url == "https://example.test/releases/v22.4.1"


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

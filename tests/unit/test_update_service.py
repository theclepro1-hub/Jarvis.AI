from __future__ import annotations

from core.updates.update_service import UpdateService


def test_update_service_reports_update_available_and_assets(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "tag_name": "v22.1.1",
                "html_url": "https://example.test/releases/v22.1.1",
                "name": "JarvisAi Unity 22.1.1",
                "assets": [
                    {
                        "name": "JarvisAi_Unity_22.1.1_windows_installer.exe",
                        "browser_download_url": "https://example.test/installer.exe",
                        "size": 123,
                        "content_type": "application/x-msdownload",
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
    assert result.latest_version == "22.1.1"
    assert result.release_url == "https://example.test/releases/v22.1.1"
    assert result.assets[0].name == "JarvisAi_Unity_22.1.1_windows_installer.exe"
    assert service.update_available() is True
    assert service.latest_version() == "22.1.1"
    assert service.release_url() == "https://example.test/releases/v22.1.1"
    assert service.summary() == "Доступна версия 22.1.1 · текущая 22.0.0"
    assert "api.github.com" in str(captured["url"])


def test_update_service_reports_error_honestly(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):  # noqa: ANN001, ANN202
        raise RuntimeError("network down")

    monkeypatch.setattr("core.updates.update_service.httpx.get", fake_get)
    service = UpdateService(settings=None, current_version="22.1.1")

    result = service.check_now()

    assert result.ok is False
    assert result.update_available is False
    assert result.latest_version == ""
    assert result.last_error.startswith("RuntimeError:")
    assert service.last_error().startswith("RuntimeError:")
    assert service.summary().startswith("Проверка обновлений: ошибка")

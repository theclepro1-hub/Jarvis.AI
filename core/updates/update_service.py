from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

import httpx


DEFAULT_GITHUB_REPOSITORY = "theclepro1-hub/Jarvis.AI"
DEFAULT_VERSION = "22.2.0"
DEFAULT_HTTP_TIMEOUT_SECONDS = 20.0


@dataclass(slots=True)
class UpdateAsset:
    name: str
    browser_download_url: str


@dataclass(slots=True)
class UpdateCheckResult:
    ok: bool
    update_available: bool
    current_version: str
    latest_version: str
    release_url: str
    assets: list[UpdateAsset] = field(default_factory=list)
    last_error: str = ""
    checked_at_utc: datetime | None = None


@dataclass(slots=True)
class UpdateApplyResult:
    ok: bool
    started: bool
    message: str
    asset_name: str = ""
    installer_path: str = ""
    last_error: str = ""


class UpdateService:
    def __init__(
        self,
        settings: object | None = None,
        *,
        repository: str = DEFAULT_GITHUB_REPOSITORY,
        current_version: str = DEFAULT_VERSION,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.current_version_value = current_version
        self.channel = "stable"
        self.latest_version_value = ""
        self.release_url_value = ""
        self.last_error_value = ""
        self.last_checked_at_utc: datetime | None = None
        self.update_available_value = False
        self.assets: list[UpdateAsset] = []
        self.last_downloaded_installer = ""
        self.apply_supported_value = os.name == "nt"
        self.last_apply_message_value = ""

    @property
    def current_version(self) -> str:
        return self.current_version_value

    def summary(self) -> str:
        if self.last_error_value:
            return "Проверка обновлений: ошибка"
        if self.update_available_value and self.latest_version_value:
            return f"Доступна версия {self.latest_version_value} · текущая {self.current_version_value}"
        channel = "стабильный" if self.channel == "stable" else self.channel
        return f"Версия {self.current_version_value} · канал {channel}"

    def check_now(self) -> UpdateCheckResult:
        try:
            response = httpx.get(
                f"https://api.github.com/repos/{self.repository}/releases/latest",
                timeout=10.0,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "JarvisAi_Unity/1.0",
                },
            )
            response.raise_for_status()
            payload = response.json()
            latest_version = self._normalize_version(str(payload.get("tag_name") or payload.get("name") or "").strip())
            self.latest_version_value = latest_version or self.current_version_value
            self.release_url_value = str(payload.get("html_url") or "").strip()
            self.assets = [
                UpdateAsset(
                    name=str(asset.get("name") or ""),
                    browser_download_url=str(asset.get("browser_download_url") or ""),
                )
                for asset in payload.get("assets", [])
                if isinstance(asset, dict)
            ]
            self.update_available_value = self._is_newer_version(self.latest_version_value, self.current_version_value)
            self.last_error_value = ""
            self.last_checked_at_utc = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            self.last_error_value = self._format_error(exc)
            self.update_available_value = False
            self.latest_version_value = ""
            self.release_url_value = ""
            self.assets = []
            self.last_checked_at_utc = datetime.now(timezone.utc)
        return UpdateCheckResult(
            ok=not bool(self.last_error_value),
            update_available=self.update_available_value,
            current_version=self.current_version_value,
            latest_version=self.latest_version_value,
            release_url=self.release_url_value,
            assets=list(self.assets),
            last_error=self.last_error_value,
            checked_at_utc=self.last_checked_at_utc,
        )

    def can_apply_update(self) -> bool:
        if not self.apply_supported_value:
            return False
        return self._pick_preferred_installer_asset() is not None

    def apply_update(self) -> UpdateApplyResult:
        if not self.apply_supported_value:
            self.last_apply_message_value = "Автоустановка поддерживается только на Windows."
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=self.last_apply_message_value,
                last_error="unsupported_platform",
            )

        if not self.assets:
            self.check_now()

        asset = self._pick_preferred_installer_asset()
        if asset is None:
            self.last_apply_message_value = "В релизе нет установщика. Обновление доступно только вручную."
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=self.last_apply_message_value,
                last_error="installer_asset_missing",
            )

        try:
            installer_path = self._download_asset(asset)
            self.last_downloaded_installer = str(installer_path)
        except Exception as exc:  # noqa: BLE001
            self.last_error_value = self._format_error(exc)
            self.last_apply_message_value = "Не удалось скачать установщик обновления."
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=self.last_apply_message_value,
                asset_name=asset.name,
                last_error=self.last_error_value,
            )

        command = [
            str(installer_path),
            "/SP-",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]
        try:
            subprocess.Popen(command, close_fds=True)  # noqa: S603
        except Exception as exc:  # noqa: BLE001
            self.last_error_value = self._format_error(exc)
            self.last_apply_message_value = "Установщик скачан, но запуск не удался. Запустите его вручную."
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=self.last_apply_message_value,
                asset_name=asset.name,
                installer_path=str(installer_path),
                last_error=self.last_error_value,
            )

        self.last_error_value = ""
        self.last_apply_message_value = "Установщик обновления запущен."
        return UpdateApplyResult(
            ok=True,
            started=True,
            message=self.last_apply_message_value,
            asset_name=asset.name,
            installer_path=str(installer_path),
        )

    def update_available(self) -> bool:
        return self.update_available_value

    def latest_version(self) -> str:
        return self.latest_version_value

    def release_url(self) -> str:
        return self.release_url_value

    def last_error(self) -> str:
        return self.last_error_value

    def status_snapshot(self) -> dict[str, object]:
        preferred_asset = self._pick_preferred_installer_asset()
        apply_hint = (
            "Можно скачать и запустить установщик обновления."
            if preferred_asset is not None and self.apply_supported_value
            else "Доступна только ручная установка через страницу релиза."
        )
        return {
            "current_version": self.current_version_value,
            "latest_version": self.latest_version_value,
            "release_url": self.release_url_value,
            "update_available": self.update_available_value,
            "last_error": self.last_error_value,
            "last_checked_at_utc": self.last_checked_at_utc.isoformat() if self.last_checked_at_utc else "",
            "assets": [{"name": asset.name, "browser_download_url": asset.browser_download_url} for asset in self.assets],
            "apply_supported": self.apply_supported_value,
            "can_apply": self.can_apply_update(),
            "apply_hint": apply_hint,
            "preferred_installer_asset": preferred_asset.name if preferred_asset else "",
            "last_downloaded_installer": self.last_downloaded_installer,
            "last_apply_message": self.last_apply_message_value,
        }

    def _normalize_version(self, value: str) -> str:
        clean = value.strip()
        if clean.casefold().startswith("v"):
            clean = clean[1:]
        return clean

    def _is_newer_version(self, latest: str, current: str) -> bool:
        return self._version_parts(latest) > self._version_parts(current)

    def _version_parts(self, value: str) -> tuple[int, ...]:
        parts: list[int] = []
        for token in value.split("."):
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits:
                parts.append(int(digits))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _format_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return f"{type(exc).__name__}: {message}"
        return type(exc).__name__

    def _pick_preferred_installer_asset(self) -> UpdateAsset | None:
        if not self.assets:
            return None
        installer_candidates = [
            asset
            for asset in self.assets
            if asset.name.lower().endswith(".exe") and "installer" in asset.name.lower()
        ]
        if installer_candidates:
            return installer_candidates[0]
        exe_candidates = [asset for asset in self.assets if asset.name.lower().endswith(".exe")]
        if exe_candidates:
            return exe_candidates[0]
        return None

    def _update_download_dir(self) -> Path:
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        path = local_app_data / "JarvisAi_Unity" / "updates"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _download_asset(self, asset: UpdateAsset) -> Path:
        if not asset.browser_download_url:
            raise RuntimeError("asset_url_missing")
        destination = self._update_download_dir() / asset.name
        tmp_path = destination.with_suffix(destination.suffix + ".download")
        headers = {"User-Agent": "JarvisAi_Unity/1.0"}
        with httpx.stream(
            "GET",
            asset.browser_download_url,
            follow_redirects=True,
            timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
            headers=headers,
        ) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        handle.write(chunk)
        tmp_path.replace(destination)
        return destination.resolve()

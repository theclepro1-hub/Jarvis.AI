from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx


DEFAULT_GITHUB_REPOSITORY = "theclepro1-hub/Jarvis.AI"
DEFAULT_VERSION = "22.2.0"


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

    def update_available(self) -> bool:
        return self.update_available_value

    def latest_version(self) -> str:
        return self.latest_version_value

    def release_url(self) -> str:
        return self.release_url_value

    def last_error(self) -> str:
        return self.last_error_value

    def status_snapshot(self) -> dict[str, object]:
        return {
            "current_version": self.current_version_value,
            "latest_version": self.latest_version_value,
            "release_url": self.release_url_value,
            "update_available": self.update_available_value,
            "last_error": self.last_error_value,
            "last_checked_at_utc": self.last_checked_at_utc.isoformat() if self.last_checked_at_utc else "",
            "assets": [{"name": asset.name, "browser_download_url": asset.browser_download_url} for asset in self.assets],
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

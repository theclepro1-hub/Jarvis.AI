from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import threading
from typing import Callable, TypeVar

import httpx


DEFAULT_GITHUB_REPOSITORY = "theclepro1-hub/Jarvis.AI"
DEFAULT_VERSION = "22.4.0"
DEFAULT_HTTP_TIMEOUT_SECONDS = 20.0
USER_AGENT = "JarvisAi_Unity/1.0"
INSTALLER_LAUNCH_ARGUMENTS = ("/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS")
HTTP_RETRY_COUNT = 2
T = TypeVar("T")


@dataclass(slots=True)
class UpdateAsset:
    name: str
    browser_download_url: str
    size: int = 0


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
    status_code: str = ""
    message: str = ""
    preferred_installer_asset: str = ""
    can_apply: bool = False


@dataclass(slots=True)
class UpdateApplyResult:
    ok: bool
    started: bool
    message: str
    asset_name: str = ""
    installer_path: str = ""
    last_error: str = ""
    status_code: str = ""
    release_url: str = ""
    requires_manual_step: bool = False


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
        self.last_status_code_value = "idle"
        self.last_status_message_value = ""
        self._check_lock = threading.Lock()
        self._apply_lock = threading.Lock()
        self._installer_process: subprocess.Popen | None = None

    @property
    def current_version(self) -> str:
        return self.current_version_value

    def summary(self) -> str:
        if self._is_installer_running():
            return "Установщик обновления уже запущен."
        if self._is_apply_in_progress():
            return "Подготавливаю установщик обновления..."
        if self._is_check_in_progress():
            return "Проверяю обновления..."
        if self.last_status_message_value:
            return self.last_status_message_value
        return self._default_summary()

    def check_now(self) -> UpdateCheckResult:
        if not self._check_lock.acquire(blocking=False):
            return self._build_check_result(
                ok=False,
                status_code="check_in_progress",
                message="Проверка обновлений уже выполняется.",
                last_error="check_in_progress",
            )

        self._set_status("checking", "Проверяю обновления...")
        try:
            payload = self._fetch_latest_release_payload()
            latest_version = self._normalize_version(str(payload.get("tag_name") or payload.get("name") or "").strip())
            self.latest_version_value = latest_version or self.current_version_value
            self.release_url_value = str(payload.get("html_url") or "").strip()
            self.assets = [
                UpdateAsset(
                    name=str(asset.get("name") or "").strip(),
                    browser_download_url=str(asset.get("browser_download_url") or "").strip(),
                    size=max(0, int(asset.get("size") or 0)),
                )
                for asset in payload.get("assets", [])
                if isinstance(asset, dict)
            ]
            self.update_available_value = self._is_newer_version(self.latest_version_value, self.current_version_value)
            self.last_error_value = ""
            self.last_checked_at_utc = datetime.now(timezone.utc)

            preferred_asset = self._pick_preferred_installer_asset()
            if self.update_available_value and preferred_asset is not None and self.apply_supported_value:
                self._set_status(
                    "update_ready",
                    f"Доступна версия {self.latest_version_value} · можно установить поверх текущей.",
                )
            elif self.update_available_value:
                self._set_status(
                    "manual_only",
                    f"Доступна версия {self.latest_version_value} · автоустановка недоступна, нужен installer-релиз.",
                )
            else:
                self._set_status("up_to_date", self._default_summary())

            return self._build_check_result(
                ok=True,
                status_code=self.last_status_code_value,
                message=self.last_status_message_value,
                can_apply=self._can_apply_with_asset(preferred_asset),
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error_value = self._format_error(exc)
            self.update_available_value = False
            self.latest_version_value = ""
            self.release_url_value = ""
            self.assets = []
            self.last_checked_at_utc = datetime.now(timezone.utc)
            self._set_status("check_failed", "Проверка обновлений: ошибка.")
            return self._build_check_result(
                ok=False,
                status_code="check_failed",
                message=self.last_status_message_value,
                last_error=self.last_error_value,
                can_apply=False,
            )
        finally:
            self._check_lock.release()

    def can_apply_update(self) -> bool:
        if not self.apply_supported_value:
            return False
        if self._is_check_in_progress() or self._is_apply_in_progress() or self._is_installer_running():
            return False
        if not self.update_available_value:
            return False
        return self._pick_preferred_installer_asset() is not None

    def apply_update(self) -> UpdateApplyResult:
        if not self.apply_supported_value:
            message = "Автоустановка доступна только для Windows installer-версии."
            self.last_apply_message_value = message
            self._set_status("unsupported_platform", message)
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=message,
                last_error="unsupported_platform",
                status_code="unsupported_platform",
                release_url=self.release_url_value,
                requires_manual_step=True,
            )

        if self._is_installer_running():
            message = "Установщик обновления уже запущен."
            self.last_apply_message_value = message
            self._set_status("installer_running", message)
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=message,
                installer_path=self.last_downloaded_installer,
                last_error="installer_already_running",
                status_code="installer_running",
                release_url=self.release_url_value,
            )

        if self._is_check_in_progress():
            message = "Дождитесь завершения проверки обновлений."
            self.last_apply_message_value = message
            self._set_status("check_in_progress", message)
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=message,
                installer_path=self.last_downloaded_installer,
                last_error="check_in_progress",
                status_code="check_in_progress",
                release_url=self.release_url_value,
            )

        if not self._apply_lock.acquire(blocking=False):
            message = "Обновление уже подготавливается."
            self.last_apply_message_value = message
            self._set_status("apply_in_progress", message)
            return UpdateApplyResult(
                ok=False,
                started=False,
                message=message,
                installer_path=self.last_downloaded_installer,
                last_error="apply_in_progress",
                status_code="apply_in_progress",
                release_url=self.release_url_value,
            )

        self._set_status("applying", "Подготавливаю установщик обновления...")
        try:
            if not self.assets:
                check_result = self.check_now()
                if not check_result.ok:
                    message = "Не удалось проверить релиз перед установкой."
                    self.last_apply_message_value = message
                    self._set_status("check_failed", message)
                    return UpdateApplyResult(
                        ok=False,
                        started=False,
                        message=message,
                        last_error=self.last_error_value or check_result.last_error or "check_failed",
                        status_code="check_failed",
                        release_url=self.release_url_value,
                    )

            if not self.update_available_value:
                message = "Новых обновлений нет."
                self.last_apply_message_value = message
                self._set_status("up_to_date", self._default_summary())
                return UpdateApplyResult(
                    ok=False,
                    started=False,
                    message=message,
                    last_error="no_update_available",
                    status_code="no_update_available",
                    release_url=self.release_url_value,
                )

            asset = self._pick_preferred_installer_asset()
            if asset is None:
                message = "В этом релизе нет installer-asset. Скачайте обновление вручную со страницы релиза."
                self.last_apply_message_value = message
                self._set_status("manual_only", message)
                return UpdateApplyResult(
                    ok=False,
                    started=False,
                    message=message,
                    last_error="installer_asset_missing",
                    status_code="manual_only",
                    release_url=self.release_url_value,
                    requires_manual_step=True,
                )

            try:
                installer_path = self._download_asset(asset)
                self.last_downloaded_installer = str(installer_path)
            except Exception as exc:  # noqa: BLE001
                self.last_error_value = self._format_error(exc)
                message = "Не удалось скачать установщик обновления."
                self.last_apply_message_value = message
                self._set_status("download_failed", message)
                return UpdateApplyResult(
                    ok=False,
                    started=False,
                    message=message,
                    asset_name=asset.name,
                    installer_path=self.last_downloaded_installer,
                    last_error=self.last_error_value,
                    status_code="download_failed",
                    release_url=self.release_url_value,
                )

            command = [str(installer_path), *INSTALLER_LAUNCH_ARGUMENTS]
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(
                getattr(subprocess, "DETACHED_PROCESS", 0)
            )
            try:
                self._installer_process = subprocess.Popen(  # noqa: S603
                    command,
                    close_fds=True,
                    creationflags=creationflags,
                )
            except Exception as exc:  # noqa: BLE001
                self.last_error_value = self._format_error(exc)
                message = "Установщик скачан, но запуск не удался. Запустите его вручную."
                self.last_apply_message_value = message
                self._set_status("launch_failed", message)
                return UpdateApplyResult(
                    ok=False,
                    started=False,
                    message=message,
                    asset_name=asset.name,
                    installer_path=str(installer_path),
                    last_error=self.last_error_value,
                    status_code="launch_failed",
                    release_url=self.release_url_value,
                    requires_manual_step=True,
                )

            self.last_error_value = ""
            message = "Установщик обновления запущен."
            self.last_apply_message_value = message
            self._set_status("installer_started", message)
            return UpdateApplyResult(
                ok=True,
                started=True,
                message=message,
                asset_name=asset.name,
                installer_path=str(installer_path),
                status_code="installer_started",
                release_url=self.release_url_value,
            )
        finally:
            self._apply_lock.release()

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
        installer_running = self._is_installer_running()
        apply_hint = self._apply_hint(preferred_asset)
        return {
            "current_version": self.current_version_value,
            "latest_version": self.latest_version_value,
            "release_url": self.release_url_value,
            "update_available": self.update_available_value,
            "last_error": self.last_error_value,
            "last_checked_at_utc": self.last_checked_at_utc.isoformat() if self.last_checked_at_utc else "",
            "assets": [
                {
                    "name": asset.name,
                    "browser_download_url": asset.browser_download_url,
                    "size": asset.size,
                }
                for asset in self.assets
            ],
            "apply_supported": self.apply_supported_value,
            "can_apply": self.can_apply_update(),
            "apply_hint": apply_hint,
            "preferred_installer_asset": preferred_asset.name if preferred_asset else "",
            "last_downloaded_installer": self.last_downloaded_installer,
            "last_apply_message": self.last_apply_message_value,
            "apply_in_progress": self._is_apply_in_progress(),
            "check_in_progress": self._is_check_in_progress(),
            "installer_running": installer_running,
            "active_installer_pid": self._active_installer_pid(),
            "status_code": self.last_status_code_value,
            "status_message": self.summary(),
            "manual_download_required": bool(self.update_available_value and preferred_asset is None),
            "apply_mode": "installer" if preferred_asset is not None else "manual",
            "installer_launch_arguments": list(INSTALLER_LAUNCH_ARGUMENTS),
        }

    def _build_check_result(
        self,
        *,
        ok: bool,
        status_code: str,
        message: str,
        last_error: str = "",
        can_apply: bool | None = None,
    ) -> UpdateCheckResult:
        preferred_asset = self._pick_preferred_installer_asset()
        return UpdateCheckResult(
            ok=ok,
            update_available=self.update_available_value,
            current_version=self.current_version_value,
            latest_version=self.latest_version_value,
            release_url=self.release_url_value,
            assets=list(self.assets),
            last_error=last_error,
            checked_at_utc=self.last_checked_at_utc,
            status_code=status_code,
            message=message,
            preferred_installer_asset=preferred_asset.name if preferred_asset else "",
            can_apply=self.can_apply_update() if can_apply is None else can_apply,
        )

    def _default_summary(self) -> str:
        channel = "стабильный" if self.channel == "stable" else self.channel
        return f"Версия {self.current_version_value} · канал {channel}"

    def _apply_hint(self, preferred_asset: UpdateAsset | None) -> str:
        if not self.apply_supported_value:
            return "Автоустановка поддерживается только на Windows."
        if self._is_installer_running():
            return "Установщик уже запущен. Дождитесь завершения установки."
        if self._is_apply_in_progress():
            return "Идёт подготовка установщика обновления."
        if self._is_check_in_progress():
            return "Сначала дождитесь завершения проверки обновлений."
        if not self.update_available_value:
            return "Сначала проверьте наличие новой версии."
        if preferred_asset is not None:
            return "Будет скачан installer-релиз и запущен поверх текущей версии. Portable и onefile обновляются вручную."
        return "В релизе нет installer-asset. Обновление доступно только вручную через страницу релиза."

    def _can_apply_with_asset(self, preferred_asset: UpdateAsset | None) -> bool:
        if not self.apply_supported_value:
            return False
        if not self.update_available_value:
            return False
        if preferred_asset is None:
            return False
        if self._is_apply_in_progress() or self._is_installer_running():
            return False
        return True

    def _set_status(self, code: str, message: str) -> None:
        self.last_status_code_value = code
        self.last_status_message_value = message

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

        candidates: list[tuple[int, UpdateAsset]] = []
        for asset in self.assets:
            name = asset.name.casefold()
            if not asset.browser_download_url:
                continue
            if "portable" in name or "onefile" in name:
                continue
            if name.endswith(".msi"):
                candidates.append((0, asset))
                continue
            if name.endswith(".exe") and ("installer" in name or "setup" in name):
                priority = 0 if "installer" in name else 1
                candidates.append((priority, asset))

        if not candidates:
            return None
        candidates.sort(key=lambda entry: (entry[0], entry[1].name.casefold()))
        return candidates[0][1]

    def _network_settings(self) -> tuple[str, str, float]:
        network = {}
        if self.settings is not None and hasattr(self.settings, "get"):
            raw = self.settings.get("network", {})
            if isinstance(raw, dict):
                network = raw

        proxy_mode = str(network.get("proxy_mode", "system")).strip().lower()
        if proxy_mode not in {"system", "manual", "off"}:
            proxy_mode = "system"

        proxy_url = str(network.get("proxy_url", "")).strip()
        timeout_value = network.get("timeout_seconds", DEFAULT_HTTP_TIMEOUT_SECONDS)
        try:
            timeout = float(timeout_value)
        except (TypeError, ValueError):
            timeout = DEFAULT_HTTP_TIMEOUT_SECONDS
        timeout = max(3.0, timeout)
        return proxy_mode, proxy_url, timeout

    def _http_attempts(self) -> list[tuple[str, bool, str]]:
        proxy_mode, proxy_url, _timeout = self._network_settings()
        if proxy_mode == "manual" and proxy_url:
            return [("manual_proxy", False, proxy_url), ("direct_fallback", False, "")]
        if proxy_mode == "off":
            return [("direct", False, "")]
        return [("system_proxy", True, ""), ("direct_fallback", False, "")]

    def _create_http_client(self, *, proxy_url: str = "", trust_env: bool = True) -> httpx.Client:
        timeout = self._network_settings()[2]
        transport = httpx.HTTPTransport(retries=HTTP_RETRY_COUNT)
        client_kwargs: dict[str, object] = {
            "transport": transport,
            "timeout": timeout,
            "follow_redirects": True,
            "headers": {
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
            "trust_env": trust_env,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        return httpx.Client(**client_kwargs)

    def _request_with_fallback(self, request: Callable[[httpx.Client], T]) -> T:
        last_transport_error: httpx.TransportError | None = None
        for label, trust_env, proxy_url in self._http_attempts():
            try:
                with self._create_http_client(proxy_url=proxy_url, trust_env=trust_env) as client:
                    return request(client)
            except httpx.TransportError as exc:
                last_transport_error = exc
                self.last_error_value = self._format_error(exc)
                if label == "direct_fallback":
                    break
        if last_transport_error is not None:
            raise last_transport_error
        raise RuntimeError("http_request_failed")

    def _fetch_latest_release_payload(self) -> dict[str, object]:
        url = f"https://api.github.com/repos/{self.repository}/releases/latest"

        def request(client: httpx.Client) -> dict[str, object]:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("invalid_release_payload")
            return payload

        return self._request_with_fallback(request)

    def _update_download_dir(self) -> Path:
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        path = local_app_data / "JarvisAi_Unity" / "updates"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _download_asset(self, asset: UpdateAsset) -> Path:
        if not asset.browser_download_url:
            raise RuntimeError("asset_url_missing")

        destination = self._update_download_dir() / asset.name
        if destination.exists():
            if self._has_valid_asset_size(destination, asset):
                return destination.resolve()
            destination.unlink(missing_ok=True)

        tmp_path = destination.with_suffix(destination.suffix + ".download")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

        def request(client: httpx.Client) -> None:
            try:
                with client.stream("GET", asset.browser_download_url) as response:
                    response.raise_for_status()
                    with tmp_path.open("wb") as handle:
                        for chunk in response.iter_bytes(64 * 1024):
                            if chunk:
                                handle.write(chunk)
                if not self._has_valid_asset_size(tmp_path, asset):
                    raise RuntimeError(
                        f"download_size_mismatch: expected {asset.size} bytes, got {tmp_path.stat().st_size} bytes"
                    )
                tmp_path.replace(destination)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

        self._request_with_fallback(request)
        return destination.resolve()

    def _has_valid_asset_size(self, path: Path, asset: UpdateAsset) -> bool:
        if not path.exists():
            return False
        actual_size = path.stat().st_size
        if actual_size <= 0:
            return False
        if asset.size > 0 and actual_size != asset.size:
            return False
        return True

    def _is_check_in_progress(self) -> bool:
        return self._check_lock.locked()

    def _is_apply_in_progress(self) -> bool:
        return self._apply_lock.locked()

    def _is_installer_running(self) -> bool:
        process = self._installer_process
        if process is None:
            return False
        return process.poll() is None

    def _active_installer_pid(self) -> int:
        process = self._installer_process
        if process is None:
            return 0
        if process.poll() is not None:
            return 0
        return int(getattr(process, "pid", 0) or 0)

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import zipfile

import httpx

from core.ai.local_llm_service import DEFAULT_OLLAMA_MODEL, OLLAMA_URL, LocalLLMService


PORTABLE_OLLAMA_ZIP_URL = "https://ollama.com/download/ollama-windows-amd64.zip"
OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
PORTABLE_BOOT_TIMEOUT_SECONDS = 20.0
MODEL_PULL_TIMEOUT_SECONDS = 1800.0


@dataclass(frozen=True, slots=True)
class LocalRuntimeProvisionResult:
    ok: bool
    ready: bool
    status_code: str
    message: str
    backend: str = "ollama"
    model_name: str = ""
    installer_path: str = ""
    portable_root: str = ""
    action_required: bool = False


class LocalRuntimeService:
    def __init__(self, settings_service) -> None:
        self.settings = settings_service
        self._lock = threading.RLock()
        self._portable_process: subprocess.Popen | None = None

    def default_model_name(self, requested: str = "") -> str:
        candidate = str(requested or self.settings.get("local_llm_model", "")).strip()
        if not candidate:
            return DEFAULT_OLLAMA_MODEL
        lowered = candidate.casefold()
        if lowered.endswith(".gguf"):
            return DEFAULT_OLLAMA_MODEL
        if self._looks_like_filesystem_path(candidate):
            return DEFAULT_OLLAMA_MODEL
        return candidate

    def ensure_ready(self, requested_model: str = "") -> LocalRuntimeProvisionResult:
        with self._lock:
            model_name = self.default_model_name(requested_model)
            existing = LocalLLMService(self.settings).status()

            if existing.ready:
                return LocalRuntimeProvisionResult(
                    ok=True,
                    ready=True,
                    status_code="ready",
                    message="Локальный режим уже готов.",
                    backend=existing.backend,
                    model_name=existing.model_path or model_name,
                    portable_root=str(self._portable_root()),
                )

            if self._model_is_available(model_name):
                self._persist_ready_runtime(model_name)
                return LocalRuntimeProvisionResult(
                    ok=True,
                    ready=True,
                    status_code="ready",
                    message=f"Локальная модель {model_name} готова.",
                    model_name=model_name,
                    portable_root=str(self._portable_root()),
                )

            if self._ensure_portable_server():
                if self._pull_model(model_name):
                    self._persist_ready_runtime(model_name)
                    return LocalRuntimeProvisionResult(
                        ok=True,
                        ready=True,
                        status_code="portable_ready",
                        message=f"Локальная модель {model_name} скачана и готова.",
                        model_name=model_name,
                        portable_root=str(self._portable_root()),
                    )
                return LocalRuntimeProvisionResult(
                    ok=False,
                    ready=False,
                    status_code="model_pull_failed",
                    message=f"Не удалось догрузить локальную модель {model_name}.",
                    model_name=model_name,
                    portable_root=str(self._portable_root()),
                )

            installer_path = self._download_installer()
            self._launch_installer(installer_path)
            return LocalRuntimeProvisionResult(
                ok=True,
                ready=False,
                status_code="installer_started",
                message="Открыл установщик Ollama. Завершите установку и нажмите ещё раз, чтобы догрузить модель.",
                model_name=model_name,
                installer_path=str(installer_path),
                portable_root=str(self._portable_root()),
                action_required=True,
            )

    def _persist_ready_runtime(self, model_name: str) -> None:
        self.settings.bulk_update(
            {
                "local_llm_backend": "ollama",
                "local_llm_model": model_name,
            }
        )

    def _ensure_portable_server(self) -> bool:
        if self._ollama_api_ready():
            return True

        executable = self._portable_executable()
        if executable is None:
            extracted = self._download_and_extract_portable()
            executable = self._find_portable_executable(extracted)
            if executable is None:
                return False

        if self._start_portable_serve(executable) and self._wait_for_api():
            return True
        return False

    def _portable_root(self) -> Path:
        return self._runtime_root() / "ollama-portable"

    def _models_root(self) -> Path:
        return self._runtime_root() / "ollama-models"

    def _downloads_root(self) -> Path:
        return self._runtime_root() / "downloads"

    def _runtime_root(self) -> Path:
        store = getattr(self.settings, "store", None)
        base_dir = getattr(store, "base_dir", None)
        if isinstance(base_dir, Path):
            root = base_dir
        else:
            appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home())
            root = appdata / "JarvisAi_Unity"
        return root / "runtime"

    def _portable_executable(self) -> Path | None:
        return self._find_portable_executable(self._portable_root())

    def _find_portable_executable(self, root: Path) -> Path | None:
        if not root.exists():
            return None
        direct = root / "ollama.exe"
        if direct.exists():
            return direct
        for candidate in root.rglob("ollama.exe"):
            if candidate.is_file():
                return candidate
        return None

    def _download_and_extract_portable(self) -> Path:
        downloads_root = self._downloads_root()
        downloads_root.mkdir(parents=True, exist_ok=True)
        portable_root = self._portable_root()
        portable_root.mkdir(parents=True, exist_ok=True)
        archive_path = downloads_root / "ollama-windows-amd64.zip"
        tmp_path = archive_path.with_suffix(".zip.download")

        with httpx.stream("GET", PORTABLE_OLLAMA_ZIP_URL, timeout=120.0, follow_redirects=True) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        handle.write(chunk)

        if archive_path.exists():
            archive_path.unlink()
        tmp_path.replace(archive_path)

        extracted_root = portable_root / "current"
        if extracted_root.exists():
            shutil.rmtree(extracted_root, ignore_errors=True)
        extracted_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extracted_root)
        return extracted_root

    def _start_portable_serve(self, executable: Path) -> bool:
        if self._portable_process is not None and self._portable_process.poll() is None:
            return True

        env = os.environ.copy()
        env["OLLAMA_HOST"] = "127.0.0.1:11434"
        env["OLLAMA_MODELS"] = str(self._models_root())
        self._models_root().mkdir(parents=True, exist_ok=True)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._portable_process = subprocess.Popen(  # noqa: S603
            [str(executable), "serve"],
            cwd=str(executable.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        return True

    def _wait_for_api(self) -> bool:
        deadline = time.monotonic() + PORTABLE_BOOT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._ollama_api_ready():
                return True
            time.sleep(0.5)
        return False

    def _ollama_api_ready(self) -> bool:
        try:
            response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.5)
            response.raise_for_status()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _model_is_available(self, model_name: str) -> bool:
        try:
            response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=4.0)
            response.raise_for_status()
            payload = response.json()
        except Exception:  # noqa: BLE001
            return False

        models = payload.get("models", []) if isinstance(payload, dict) else []
        installed = {str(item.get("name", "")).strip() for item in models if isinstance(item, dict)}
        return model_name in installed

    def _pull_model(self, model_name: str) -> bool:
        try:
            response = httpx.post(
                f"{OLLAMA_URL}/api/pull",
                json={"model": model_name, "stream": False},
                timeout=MODEL_PULL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Exception:  # noqa: BLE001
            return False
        return self._model_is_available(model_name)

    def _download_installer(self) -> Path:
        downloads_root = self._downloads_root()
        downloads_root.mkdir(parents=True, exist_ok=True)
        installer_path = downloads_root / "OllamaSetup.exe"
        tmp_path = installer_path.with_suffix(".exe.download")

        with httpx.stream("GET", OLLAMA_INSTALLER_URL, timeout=120.0, follow_redirects=True) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        handle.write(chunk)

        if installer_path.exists():
            installer_path.unlink()
        tmp_path.replace(installer_path)
        return installer_path

    def _launch_installer(self, installer_path: Path) -> None:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(  # noqa: S603
            [str(installer_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )

    def _looks_like_filesystem_path(self, value: str) -> bool:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or normalized.startswith("./") or normalized.startswith("../"):
            return True
        if len(normalized) >= 3 and normalized[1:3] == ":/":
            return True
        return False

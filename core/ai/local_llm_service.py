from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2:1b"
OLLAMA_DIAGNOSTIC_TIMEOUT = httpx.Timeout(connect=0.2, read=0.35, write=0.35, pool=0.35)


@dataclass(frozen=True, slots=True)
class LocalLLMStatus:
    ready: bool
    backend: str
    model_path: str
    detail: str


@dataclass(frozen=True, slots=True)
class LocalLLMDiagnostics:
    ready: bool
    backend: str
    model_path: str
    detail: str
    user_status: str
    action_label: str
    action_url: str


class LocalLLMService:
    def __init__(self, settings_service) -> None:
        self.settings = settings_service

    def status(self) -> LocalLLMStatus:
        backend = self._configured_backend()
        if backend == "auto":
            llama_status = self._llama_cpp_status()
            if llama_status.ready:
                return llama_status

            ollama_status = self._ollama_status(allow_first_model=True)
            if ollama_status.ready:
                return ollama_status

            if self._configured_model():
                return llama_status

            if ollama_status.detail and "недоступен" not in ollama_status.detail.casefold():
                return ollama_status

            return LocalLLMStatus(
                ready=False,
                backend="auto",
                model_path="",
                detail="Нужна локальная .gguf-модель или запущенный Ollama.",
            )

        if backend == "ollama":
            return self._ollama_status(allow_first_model=True)
        return self._llama_cpp_status()

    def diagnostics(self) -> LocalLLMDiagnostics:
        status = self.status()
        if status.ready:
            label = "Открыть Ollama" if status.backend == "ollama" else "Открыть llama.cpp"
            url = "https://docs.ollama.com/" if status.backend == "ollama" else "https://github.com/abetlen/llama-cpp-python"
            return LocalLLMDiagnostics(
                ready=True,
                backend=status.backend,
                model_path=status.model_path,
                detail=status.detail,
                user_status="Локальная модель готова.",
                action_label=label,
                action_url=url,
            )

        if status.backend == "auto":
            return LocalLLMDiagnostics(
                ready=False,
                backend=status.backend,
                model_path=status.model_path,
                detail=status.detail,
                user_status="Нужна локальная .gguf-модель или Ollama.",
                action_label="Открыть Ollama",
                action_url="https://docs.ollama.com/",
            )

        if status.backend == "ollama":
            if status.model_path:
                user_status = "Укажите модель Ollama или скачайте её."
            else:
                user_status = "Установите Ollama и скачайте локальную модель."
            return LocalLLMDiagnostics(
                ready=False,
                backend=status.backend,
                model_path=status.model_path,
                detail=status.detail,
                user_status=user_status,
                action_label="Открыть Ollama",
                action_url="https://docs.ollama.com/",
            )

        return LocalLLMDiagnostics(
            ready=False,
            backend=status.backend,
            model_path=status.model_path,
            detail=status.detail,
            user_status="Нужен пакет llama-cpp-python и файл .gguf.",
            action_label="Открыть llama.cpp",
            action_url="https://github.com/abetlen/llama-cpp-python",
        )

    def generate(self, messages: list[dict[str, str]]) -> str:
        status = self.status()
        if not status.ready:
            raise RuntimeError(status.detail or "Локальная модель не готова.")
        if status.backend == "ollama":
            return self._generate_with_ollama(status.model_path, messages)
        return self._generate_with_llama_cpp(status.model_path, messages)

    def _configured_backend(self) -> str:
        backend = str(self.settings.get("local_llm_backend", "auto")).strip().lower()
        if backend in {"auto", "ollama", "llama_cpp"}:
            return backend
        return "auto"

    def _configured_model(self) -> str:
        return str(self.settings.get("local_llm_model", "")).strip()

    def _ollama_status(self, *, allow_first_model: bool) -> LocalLLMStatus:
        try:
            response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=OLLAMA_DIAGNOSTIC_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            return LocalLLMStatus(
                ready=False,
                backend="ollama",
                model_path=self._configured_model(),
                detail=f"Ollama недоступен: {exc}",
            )

        models = payload.get("models", []) if isinstance(payload, dict) else []
        installed = [str(item.get("name", "")).strip() for item in models if isinstance(item, dict)]
        configured = self._configured_model()
        if configured:
            if configured in installed:
                return LocalLLMStatus(
                    ready=True,
                    backend="ollama",
                    model_path=configured,
                    detail="Ollama-модель готова.",
                )
            return LocalLLMStatus(
                ready=False,
                backend="ollama",
                model_path=configured,
                detail="Указанная Ollama-модель не установлена на этом компьютере.",
            )

        if allow_first_model and installed:
            return LocalLLMStatus(
                ready=True,
                backend="ollama",
                model_path=installed[0],
                detail="Ollama-модель готова.",
            )

        return LocalLLMStatus(
            ready=False,
            backend="ollama",
            model_path="",
            detail="В Ollama пока нет установленной модели.",
        )

    def _llama_cpp_status(self) -> LocalLLMStatus:
        model_path = self._configured_model()
        if not model_path:
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path="",
                detail="Не указан путь к .gguf-модели.",
            )

        path = Path(model_path)
        if path.suffix.lower() != ".gguf":
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path=model_path,
                detail="Нужен путь к файлу .gguf.",
            )
        if not path.exists():
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path=model_path,
                detail="Файл .gguf не найден.",
            )

        try:
            import llama_cpp  # noqa: F401
        except Exception:  # noqa: BLE001
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path=model_path,
                detail="Пакет llama-cpp-python не установлен.",
            )

        return LocalLLMStatus(
            ready=True,
            backend="llama_cpp",
            model_path=model_path,
            detail="Локальная .gguf-модель готова.",
        )

    def _generate_with_ollama(self, model_name: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": model_name or DEFAULT_OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
        }
        response = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {}) if isinstance(data, dict) else {}
        content = str(message.get("content", "")).strip()
        if not content:
            raise RuntimeError("Ollama вернул пустой ответ.")
        return content

    def _generate_with_llama_cpp(self, model_path: str, messages: list[dict[str, str]]) -> str:
        from llama_cpp import Llama

        llm = Llama(model_path=model_path, n_ctx=4096, verbose=False)
        response: dict[str, Any] = llm.create_chat_completion(messages=messages, temperature=0.35, max_tokens=384)
        choices = response.get("choices", []) if isinstance(response, dict) else []
        if not choices:
            raise RuntimeError("Локальная модель вернула пустой ответ.")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = str(message.get("content", "")).strip()
        if not content:
            raise RuntimeError("Локальная модель вернула пустой ответ.")
        return content

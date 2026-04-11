from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import httpx


DEFAULT_LOCAL_LLM_CONTEXT = 4096
DEFAULT_LOCAL_LLM_MAX_TOKENS = 384
DEFAULT_LOCAL_LLM_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_LOCAL_LLM_TIMEOUT_SECONDS = 30.0


class LocalLLMUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LocalLLMStatus:
    ready: bool
    backend: str
    model_path: str
    detail: str


@dataclass(frozen=True, slots=True)
class LocalLLMDiagnostics:
    status: LocalLLMStatus
    summary: str
    next_step: str


class LocalLLMService:
    def __init__(self, settings_service) -> None:
        self.settings = settings_service
        self._client = None
        self._client_signature: tuple[str, str, str] | None = None

    def backend(self) -> str:
        backend = str(self.settings.get("local_llm_backend", "llama_cpp") or "").strip().casefold()
        if backend in {"llama_cpp", "ollama"}:
            return backend
        return backend or "llama_cpp"

    def model_path(self) -> str:
        return str(self.settings.get("local_llm_model", "") or "").strip()

    def backend_label(self) -> str:
        backend = self.backend()
        if backend == "llama_cpp":
            return "Local Llama"
        if backend == "ollama":
            return "Ollama"
        return backend

    def model_label(self) -> str:
        model_ref = self.model_path()
        if not model_ref:
            return self.backend_label()
        if self.backend() == "llama_cpp":
            resolved = Path(model_ref).expanduser()
            return resolved.name or str(resolved)
        return model_ref

    def is_ready(self) -> bool:
        status = self.status()
        return status.ready

    def diagnostics(self) -> LocalLLMDiagnostics:
        status = self.status()
        summary, next_step = self._diagnostic_messages(status)
        return LocalLLMDiagnostics(status=status, summary=summary, next_step=next_step)

    def status(self) -> LocalLLMStatus:
        candidates = self._candidate_statuses()
        for candidate in candidates:
            if candidate.ready:
                return candidate
        return candidates[0] if candidates else LocalLLMStatus(
            ready=False,
            backend=self.backend(),
            model_path=self.model_path(),
            detail="Local LLM backend is not configured.",
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.35,
        max_tokens: int = DEFAULT_LOCAL_LLM_MAX_TOKENS,
    ) -> str:
        status = self.status()
        if not status.ready:
            raise LocalLLMUnavailableError(status.detail)

        client = self._client_for(status.backend, status.model_path)
        if status.backend == "ollama":
            return self._generate_with_ollama(client, status.model_path, messages, temperature=temperature, max_tokens=max_tokens)
        return self._generate_with_llama_cpp(client, messages, temperature=temperature, max_tokens=max_tokens)

    def _client_for(self, backend: str, model_path: str):  # noqa: ANN202
        signature = (backend, model_path, self._ollama_base_url())
        if self._client is not None and self._client_signature == signature:
            return self._client

        if backend == "ollama":
            self._client = httpx.Client(
                base_url=self._ollama_base_url(),
                timeout=httpx.Timeout(self._timeout_seconds()),
                trust_env=False,
            )
            self._client_signature = signature
            return self._client

        from llama_cpp import Llama

        self._client = Llama(
            model_path=model_path,
            n_ctx=int(self.settings.get("local_llm_context", DEFAULT_LOCAL_LLM_CONTEXT) or DEFAULT_LOCAL_LLM_CONTEXT),
            verbose=False,
        )
        self._client_signature = signature
        return self._client

    def _candidate_statuses(self) -> list[LocalLLMStatus]:
        backend = self.backend()
        model_ref = self.model_path()
        if backend == "ollama":
            return [self._ollama_status(model_ref), self._llama_cpp_status(model_ref)]
        if backend == "auto":
            return [self._ollama_status(model_ref), self._llama_cpp_status(model_ref)]
        return [self._llama_cpp_status(model_ref), self._ollama_status(model_ref)]

    def _llama_cpp_status(self, model_ref: str) -> LocalLLMStatus:
        if not model_ref:
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path="",
                detail="Local Llama model is not configured.",
            )
        resolved = Path(model_ref).expanduser()
        if resolved.suffix.casefold() != ".gguf":
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path=str(resolved),
                detail="Local Llama model must be a .gguf file.",
            )
        if not resolved.is_file():
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path=str(resolved),
                detail="Local Llama model file was not found.",
            )
        if importlib.util.find_spec("llama_cpp") is None:
            return LocalLLMStatus(
                ready=False,
                backend="llama_cpp",
                model_path=str(resolved),
                detail="llama_cpp is not installed.",
            )
        return LocalLLMStatus(
            ready=True,
            backend="llama_cpp",
            model_path=str(resolved),
            detail="Local Llama backend ready.",
        )

    def _ollama_status(self, model_ref: str) -> LocalLLMStatus:
        try:
            client = self._client_for("ollama", model_ref)
            response = client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise LocalLLMUnavailableError("Ollama API returned an invalid payload.")
            installed_models = self._ollama_models(payload)
            selected_model = self._resolve_ollama_model(model_ref, installed_models)
            if not selected_model:
                return LocalLLMStatus(
                    ready=False,
                    backend="ollama",
                    model_path=model_ref,
                    detail="Ollama model is not configured.",
                )
            if selected_model not in installed_models:
                return LocalLLMStatus(
                    ready=False,
                    backend="ollama",
                    model_path=selected_model,
                    detail="Ollama model is not installed on this machine.",
                )
        except Exception as exc:  # noqa: BLE001
            return LocalLLMStatus(
                ready=False,
                backend="ollama",
                model_path=model_ref,
                detail=f"Ollama backend is not reachable: {self._describe_error(exc)}",
            )
        return LocalLLMStatus(
            ready=True,
            backend="ollama",
            model_path=selected_model,
            detail="Ollama backend ready.",
        )

    def _generate_with_llama_cpp(
        self,
        client,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = client.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choices = response.get("choices") or []
        if not choices:
            raise LocalLLMUnavailableError("Local Llama returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        text = str(content or "").strip()
        if not text:
            raise LocalLLMUnavailableError("Local Llama returned an empty reply.")
        return text

    def _generate_with_ollama(
        self,
        client,
        model_name: str,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            response = client.post(
                "/api/chat",
                json={
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise LocalLLMUnavailableError(self._describe_error(exc)) from exc

        if not isinstance(payload, dict):
            raise LocalLLMUnavailableError("Ollama returned an invalid response.")

        message = payload.get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        text = str(content or "").strip()
        if not text:
            text = str(payload.get("response", "") or "").strip()
        if not text:
            raise LocalLLMUnavailableError("Ollama returned an empty reply.")
        return text

    def _ollama_base_url(self) -> str:
        url = str(
            self.settings.get("local_llm_ollama_url", DEFAULT_LOCAL_LLM_OLLAMA_BASE_URL) or DEFAULT_LOCAL_LLM_OLLAMA_BASE_URL
        ).strip()
        return url.rstrip("/") or DEFAULT_LOCAL_LLM_OLLAMA_BASE_URL

    def _timeout_seconds(self) -> float:
        raw = self.settings.get("local_llm_timeout_seconds", DEFAULT_LOCAL_LLM_TIMEOUT_SECONDS)
        try:
            timeout = float(raw)
        except (TypeError, ValueError):
            timeout = DEFAULT_LOCAL_LLM_TIMEOUT_SECONDS
        return max(1.0, min(timeout, 120.0))

    def _describe_error(self, exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        if status_code:
            return f"HTTP {status_code}"
        if isinstance(exc, httpx.HTTPError):
            return exc.__class__.__name__
        return exc.__class__.__name__

    def _diagnostic_messages(self, status: LocalLLMStatus) -> tuple[str, str]:
        backend = status.backend
        model_ref = status.model_path
        detail = status.detail.casefold()
        model_label = self._status_model_label(status)

        if status.ready:
            if backend == "ollama":
                return f"Ollama готова: {model_label}.", "Можно включать приватный режим."
            return f"Local Llama готова: {model_label}.", "Можно включать приватный режим."

        if backend == "ollama":
            if not model_ref:
                return "Ollama не настроена.", "Укажите модель, например llama3.2:1b."
            if "not installed" in detail:
                return f"Ollama запущена, но модели {model_label} нет.", f"Выполните `ollama pull {model_ref}`."
            if "not reachable" in detail:
                return "Ollama сейчас недоступна.", "Запустите Ollama Desktop или `ollama serve`."
            return "Ollama не готова.", "Проверьте `ollama list` и состояние daemon."

        if backend == "llama_cpp":
            if not model_ref:
                return "Local Llama не настроена.", "Укажите путь к .gguf-модели."
            if "must be a .gguf file" in detail:
                return "Нужен файл .gguf.", "Выберите локальную GGUF-модель."
            if "not found" in detail:
                return "Файл .gguf не найден.", "Проверьте путь к модели или скопируйте GGUF-файл на диск."
            if "llama_cpp is not installed" in detail:
                return "llama-cpp-python не установлен.", "Установите пакет llama-cpp-python и укажите .gguf-модель."
            return "Local Llama не готова.", "Проверьте путь к .gguf-модели и пакет llama-cpp-python."

        return "Локальный LLM-бэкенд не готов.", "Выберите llama_cpp или ollama."

    def _status_model_label(self, status: LocalLLMStatus) -> str:
        model_ref = str(status.model_path or "").strip()
        if not model_ref:
            return self.backend_label()
        if status.backend == "llama_cpp":
            resolved = Path(model_ref).expanduser()
            return resolved.name or str(resolved)
        return model_ref

    def _ollama_model_is_installed(self, payload: dict[str, object], model_name: str) -> bool:
        return self._normalize_ollama_model_name(model_name) in self._ollama_models(payload)

    def _ollama_models(self, payload: dict[str, object]) -> list[str]:
        models = payload.get("models")
        if not isinstance(models, list):
            return []

        resolved: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            for key in ("name", "model", "model_name"):
                candidate = self._normalize_ollama_model_name(item.get(key))
                if candidate:
                    resolved.append(candidate)
                    break
        return resolved

    def _resolve_ollama_model(self, model_ref: str, installed_models: list[str]) -> str:
        target = self._normalize_ollama_model_name(model_ref)
        if target:
            return target
        return installed_models[0] if installed_models else ""

    def _normalize_ollama_model_name(self, value: object) -> str:
        name = str(value or "").strip().casefold()
        if not name:
            return ""
        return name.split()[0]

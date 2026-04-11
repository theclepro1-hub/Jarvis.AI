from __future__ import annotations

from core.ai.local_llm_service import LocalLLMDiagnostics, LocalLLMStatus, LocalLLMService


class FakeSettings:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self._payload = {
            "local_llm_backend": "auto",
            "local_llm_model": "",
            **(payload or {}),
        }

    def get(self, key: str, default=None):  # noqa: ANN001
        return self._payload.get(key, default)


def test_auto_status_prefers_llama_cpp_when_it_is_ready(monkeypatch) -> None:
    service = LocalLLMService(FakeSettings({"local_llm_model": "C:/models/local.gguf"}))
    monkeypatch.setattr(
        service,
        "_llama_cpp_status",
        lambda: LocalLLMStatus(True, "llama_cpp", "C:/models/local.gguf", "Локальная .gguf-модель готова."),
    )
    monkeypatch.setattr(
        service,
        "_ollama_status",
        lambda allow_first_model: LocalLLMStatus(False, "ollama", "", "В Ollama пока нет установленной модели."),
    )

    status = service.status()

    assert status.ready is True
    assert status.backend == "llama_cpp"
    assert status.model_path == "C:/models/local.gguf"


def test_auto_status_uses_ollama_when_it_is_ready(monkeypatch) -> None:
    service = LocalLLMService(FakeSettings())
    monkeypatch.setattr(
        service,
        "_llama_cpp_status",
        lambda: LocalLLMStatus(False, "llama_cpp", "", "Не указан путь к .gguf-модели."),
    )
    monkeypatch.setattr(
        service,
        "_ollama_status",
        lambda allow_first_model: LocalLLMStatus(True, "ollama", "llama3.2:1b", "Ollama-модель готова."),
    )

    status = service.status()

    assert status.ready is True
    assert status.backend == "ollama"
    assert status.model_path == "llama3.2:1b"


def test_auto_diagnostics_are_honest_when_nothing_is_ready(monkeypatch) -> None:
    service = LocalLLMService(FakeSettings())
    monkeypatch.setattr(
        service,
        "_llama_cpp_status",
        lambda: LocalLLMStatus(False, "llama_cpp", "", "Не указан путь к .gguf-модели."),
    )
    monkeypatch.setattr(
        service,
        "_ollama_status",
        lambda allow_first_model: LocalLLMStatus(False, "ollama", "", "Ollama недоступен: connection error"),
    )

    status = service.status()
    diagnostics = service.diagnostics()

    assert status.ready is False
    assert status.backend == "auto"
    assert isinstance(diagnostics, LocalLLMDiagnostics)
    assert diagnostics.ready is False
    assert diagnostics.user_status == "Нужна локальная .gguf-модель или Ollama."

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.ai.local_llm_service import LocalLLMService, LocalLLMUnavailableError


class FakeSettings:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = dict(payload)

    def get(self, key: str, default: object = None) -> object:
        return self._payload.get(key, default)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_llama_cpp_status_reports_not_ready_when_package_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("core.ai.local_llm_service.importlib.util.find_spec", lambda _name: None)
    model_path = tmp_path / "model.gguf"
    model_path.write_text("placeholder", encoding="utf-8")

    service = LocalLLMService(FakeSettings({"local_llm_backend": "llama_cpp", "local_llm_model": model_path}))
    status = service.status()

    assert status.ready is False
    assert status.backend == "llama_cpp"
    assert "llama_cpp is not installed" in status.detail


def test_llama_cpp_status_reports_not_ready_when_model_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("core.ai.local_llm_service.importlib.util.find_spec", lambda _name: SimpleNamespace())

    service = LocalLLMService(FakeSettings({"local_llm_backend": "llama_cpp", "local_llm_model": str(tmp_path / "missing.gguf")}))
    status = service.status()

    assert status.ready is False
    assert status.backend == "llama_cpp"
    assert "model file was not found" in status.detail


def test_llama_cpp_status_requires_gguf_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("core.ai.local_llm_service.importlib.util.find_spec", lambda _name: SimpleNamespace())
    model_path = tmp_path / "model.txt"
    model_path.write_text("placeholder", encoding="utf-8")

    service = LocalLLMService(FakeSettings({"local_llm_backend": "llama_cpp", "local_llm_model": str(model_path)}))
    status = service.status()

    assert status.ready is False
    assert status.backend == "llama_cpp"
    assert ".gguf file" in status.detail


def test_ollama_status_reports_missing_model_when_daemon_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            return None

        def get(self, path: str, **_kwargs):
            calls.append(("get", path))
            return FakeResponse({"models": [{"name": "llama3.2:1b"}]})

    monkeypatch.setattr("core.ai.local_llm_service.httpx.Client", FakeClient)

    service = LocalLLMService(FakeSettings({"local_llm_backend": "ollama", "local_llm_model": "mistral:7b"}))
    status = service.status()

    assert status.ready is False
    assert status.backend == "ollama"
    assert "not installed" in status.detail.casefold()
    assert calls == [("get", "/api/tags")]


def test_ollama_generate_uses_chat_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            return None

        def get(self, path: str, **_kwargs):
            calls.append(("get", path, None))
            return FakeResponse({"models": [{"name": "llama3.2:1b"}]})

        def post(self, path: str, *, json: dict[str, object] | None = None, **_kwargs):
            calls.append(("post", path, json))
            return FakeResponse({"message": {"content": "ollama reply"}})

    monkeypatch.setattr("core.ai.local_llm_service.httpx.Client", FakeClient)

    service = LocalLLMService(
        FakeSettings(
            {
                "local_llm_backend": "ollama",
                "local_llm_model": "llama3.2:1b",
            }
        )
    )

    text = service.generate([{"role": "user", "content": "hello"}])

    assert text == "ollama reply"
    assert calls[0] == ("get", "/api/tags", None)
    assert calls[1][0] == "post"
    assert calls[1][1] == "/api/chat"


def test_generate_refuses_when_service_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    service = LocalLLMService(FakeSettings({"local_llm_backend": "ollama", "local_llm_model": ""}))

    with pytest.raises(LocalLLMUnavailableError, match="not configured"):
        service.generate([{"role": "user", "content": "hello"}])

from __future__ import annotations

from pathlib import Path

from core.ai.local_llm_service import DEFAULT_OLLAMA_MODEL, LocalLLMStatus
from core.ai.local_runtime_service import LocalRuntimeService


class FakeStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


class FakeSettings:
    def __init__(self, base_dir: Path, payload: dict[str, object] | None = None) -> None:
        self.store = FakeStore(base_dir)
        self._payload = {
            "local_llm_backend": "auto",
            "local_llm_model": "",
            **(payload or {}),
        }

    def get(self, key: str, default=None):  # noqa: ANN001, ANN201
        return self._payload.get(key, default)

    def bulk_update(self, payload: dict[str, object]) -> None:
        self._payload.update(payload)


def test_default_model_name_ignores_manual_gguf_path(tmp_path: Path) -> None:
    service = LocalRuntimeService(FakeSettings(tmp_path, {"local_llm_model": "C:/models/private.gguf"}))

    assert service.default_model_name() == DEFAULT_OLLAMA_MODEL


def test_ensure_ready_reuses_existing_model(monkeypatch, tmp_path: Path) -> None:
    settings = FakeSettings(tmp_path, {"local_llm_model": "llama3.2:1b"})
    service = LocalRuntimeService(settings)

    monkeypatch.setattr(
        "core.ai.local_runtime_service.LocalLLMService",
        lambda _settings: type("FakeLocalLLM", (), {"status": lambda self: LocalLLMStatus(False, "ollama", "", "")})(),
    )
    monkeypatch.setattr(service, "_model_is_available", lambda model_name: model_name == "llama3.2:1b")

    result = service.ensure_ready()

    assert result.ok is True
    assert result.ready is True
    assert result.status_code == "ready"
    assert settings.get("local_llm_backend") == "ollama"
    assert settings.get("local_llm_model") == "llama3.2:1b"


def test_ensure_ready_downloads_portable_runtime_and_model(monkeypatch, tmp_path: Path) -> None:
    settings = FakeSettings(tmp_path)
    service = LocalRuntimeService(settings)

    calls: list[str] = []

    monkeypatch.setattr(
        "core.ai.local_runtime_service.LocalLLMService",
        lambda _settings: type("FakeLocalLLM", (), {"status": lambda self: LocalLLMStatus(False, "ollama", "", "")})(),
    )
    monkeypatch.setattr(service, "_model_is_available", lambda _model_name: False)
    monkeypatch.setattr(service, "_ensure_portable_server", lambda: calls.append("portable") or True)
    monkeypatch.setattr(service, "_pull_model", lambda model_name: calls.append(f"pull:{model_name}") or True)

    result = service.ensure_ready("llama3.2:1b")

    assert result.ok is True
    assert result.ready is True
    assert result.status_code == "portable_ready"
    assert calls == ["portable", "pull:llama3.2:1b"]
    assert settings.get("local_llm_backend") == "ollama"
    assert settings.get("local_llm_model") == "llama3.2:1b"


def test_ensure_ready_falls_back_to_installer(monkeypatch, tmp_path: Path) -> None:
    settings = FakeSettings(tmp_path)
    service = LocalRuntimeService(settings)
    installer_path = tmp_path / "runtime" / "downloads" / "OllamaSetup.exe"
    installer_path.parent.mkdir(parents=True, exist_ok=True)
    installer_path.write_bytes(b"stub")
    launched: list[Path] = []

    monkeypatch.setattr(
        "core.ai.local_runtime_service.LocalLLMService",
        lambda _settings: type("FakeLocalLLM", (), {"status": lambda self: LocalLLMStatus(False, "ollama", "", "")})(),
    )
    monkeypatch.setattr(service, "_model_is_available", lambda _model_name: False)
    monkeypatch.setattr(service, "_ensure_portable_server", lambda: False)
    monkeypatch.setattr(service, "_download_installer", lambda: installer_path)
    monkeypatch.setattr(service, "_launch_installer", lambda path: launched.append(path))

    result = service.ensure_ready()

    assert result.ok is True
    assert result.ready is False
    assert result.status_code == "installer_started"
    assert launched == [installer_path]

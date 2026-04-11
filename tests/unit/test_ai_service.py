from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.ai.ai_service import AIService, PRIVATE_TEXT_BACKEND_ERROR


class FakeSettings:
    def __init__(self, settings: dict | None = None, registration: dict | None = None) -> None:
        self._settings = {
            "ai_mode": "auto",
            "ai_provider": "auto",
            "ai_max_attempts": 1,
            "network": {
                "proxy_mode": "system",
                "proxy_url": "",
                "no_proxy": "localhost,127.0.0.1,::1",
                "timeout_seconds": 20,
            },
            **(settings or {}),
        }
        self._registration = {
            "groq_api_key": "groq-key",
            "cerebras_api_key": "cerebras-key",
            "gemini_api_key": "gemini-key",
            "openrouter_api_key": "openrouter-key",
            **(registration or {}),
        }

    def get(self, key: str, default=None):
        return self._settings.get(key, default)

    def get_registration(self) -> dict:
        return dict(self._registration)


class FakeCompletions:
    def __init__(self, calls: list[dict], base_url: str, behavior: dict[str, object]) -> None:
        self.calls = calls
        self.base_url = base_url
        self.behavior = behavior

    def create(self, **payload):
        self.calls.append({"base_url": self.base_url, **payload})
        result = self.behavior.get(self.base_url)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, str):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=result))]
            )
        return SimpleNamespace(choices=[])


class FakeClient:
    def __init__(self, calls: list[dict], behavior: dict[str, object], **kwargs) -> None:
        self.chat = SimpleNamespace(
            completions=FakeCompletions(calls, str(kwargs["base_url"]).rstrip("/"), behavior)
        )


class ProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeHttpxResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ProviderError(self.status_code)

    def json(self) -> dict:
        return dict(self._payload)


def test_auto_mode_falls_back_after_rate_limit() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": ProviderError(429),
        "https://api.cerebras.ai/v1": "резервный ответ",
    }

    service = AIService(
        FakeSettings(),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    assert service.generate_reply("расскажи коротко") == "резервный ответ"
    assert [call["base_url"] for call in calls] == [
        "https://api.groq.com/openai/v1",
        "https://api.cerebras.ai/v1",
    ]


def test_auto_mode_falls_back_after_timeout() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": TimeoutError("network timeout"),
        "https://api.cerebras.ai/v1": "резервный ответ после timeout",
    }

    service = AIService(
        FakeSettings(),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    assert service.generate_reply("коротко проверь fallback") == "резервный ответ после timeout"
    assert [call["base_url"] for call in calls] == [
        "https://api.groq.com/openai/v1",
        "https://api.cerebras.ai/v1",
    ]


def test_generate_reply_result_reports_stage_and_timing_hint() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": "чёткий ответ",
    }
    service = AIService(
        FakeSettings({"ai_mode": "fast"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    stages: list[str] = []
    result = service.generate_reply_result("расскажи", status_callback=stages.append)

    assert result.text == "чёткий ответ"
    assert result.mode == "fast"
    assert result.assistant_mode == "fast"
    assert result.provider == "groq"
    assert result.provider_label == "Groq"
    assert result.elapsed_ms >= 0
    assert result.fallback_used is False
    assert stages and stages[0].startswith("Быстрый режим: Groq")


def test_quality_mode_prioritizes_quality_plan() -> None:
    service = AIService(FakeSettings({"ai_mode": "quality"}))

    plan = service.provider_plan()

    assert [attempt.provider for attempt in plan][:3] == ["gemini", "groq", "cerebras"]
    assert plan[0].model == "gemini-3-flash-preview"


def test_fast_mode_prefers_low_latency_provider_order() -> None:
    service = AIService(FakeSettings({"ai_mode": "fast"}))

    plan = service.provider_plan()

    assert [attempt.provider for attempt in plan] == ["groq", "cerebras", "openrouter"]


def test_assistant_mode_takes_priority_over_legacy_ai_mode() -> None:
    service = AIService(FakeSettings({"assistant_mode": "smart", "ai_mode": "fast"}))

    plan = service.provider_plan()

    assert [attempt.provider for attempt in plan][:3] == ["gemini", "groq", "cerebras"]


def test_smart_assistant_mode_ignores_legacy_ai_provider() -> None:
    service = AIService(FakeSettings({"assistant_mode": "smart", "ai_provider": "groq"}))

    plan = service.provider_plan()

    assert [attempt.provider for attempt in plan][:3] == ["gemini", "groq", "cerebras"]


def test_standard_assistant_mode_uses_balanced_route_and_reports_assistant_mode() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": "standard-route",
    }
    service = AIService(
        FakeSettings({"assistant_mode": "standard", "ai_mode": "quality"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("hello")

    assert result.mode == "auto"
    assert result.assistant_mode == "standard"
    assert result.privacy_guarantee == "local_first_with_fallback"
    assert calls[0]["model"] == "openai/gpt-oss-20b"


def test_ai_mode_request_options_are_distinct() -> None:
    service = AIService(FakeSettings())

    fast = service._mode_request_options("fast")
    auto = service._mode_request_options("auto")
    standard = service._mode_request_options("standard")
    quality = service._mode_request_options("quality")
    smart = service._mode_request_options("smart")

    assert fast["max_tokens"] < auto["max_tokens"] < quality["max_tokens"]
    assert fast["temperature"] != quality["temperature"]
    assert standard == auto
    assert smart == quality


def test_manual_provider_selection_is_not_silent_auto_fallback() -> None:
    service = AIService(FakeSettings({"ai_mode": "auto", "ai_provider": "gemini"}))

    plan = service.provider_plan()

    assert [attempt.provider for attempt in plan] == ["gemini"]


def test_retryable_error_can_retry_same_provider_when_attempts_enabled() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": ProviderError(429),
        "https://api.cerebras.ai/v1": "fallback",
    }
    service = AIService(
        FakeSettings({"ai_mode": "auto", "ai_max_attempts": 2, "ai_provider": "groq"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    # Manual provider "groq" means retries should stay on the same provider.
    reply = service.generate_reply("test")

    assert reply
    assert [call["base_url"] for call in calls].count("https://api.groq.com/openai/v1") == 2


def test_legacy_local_mode_maps_to_private_without_cloud_calls() -> None:
    def fail_factory(**_kwargs):
        raise AssertionError("cloud provider must not be called for a legacy local mode value")

    service = AIService(
        FakeSettings(
            {"ai_mode": "local"},
        ),
        client_factory=fail_factory,
    )

    result = service.generate_reply_result("привет")

    assert result.mode == "local"
    assert result.assistant_mode == "private"
    assert result.error == PRIVATE_TEXT_BACKEND_ERROR
    assert result.provider == ""
    assert result.fallback_used is False


def test_private_assistant_mode_refuses_cloud_without_fallback() -> None:
    def fail_factory(**_kwargs):
        raise AssertionError("cloud provider must not be called for private text mode")

    service = AIService(
        FakeSettings({"assistant_mode": "private", "ai_mode": "quality", "ai_provider": "gemini"}),
        client_factory=fail_factory,
    )

    result = service.generate_reply_result("hello")

    assert result.mode == "local"
    assert result.assistant_mode == "private"
    assert result.error == PRIVATE_TEXT_BACKEND_ERROR
    assert result.provider == ""
    assert result.fallback_used is False
    assert "локальная Llama" in result.text


def test_private_assistant_mode_uses_local_llama_when_ready(tmp_path) -> None:
    class ReadyLocalLLM:
        def model_path(self) -> str:
            return str(tmp_path / "llama.gguf")

        def status(self):
            return SimpleNamespace(ready=True, detail="Local Llama backend ready.")

        def generate(self, _messages, *, temperature=0.35, max_tokens=300):
            _ = (temperature, max_tokens)
            return "локальный ответ"

    def fail_factory(**_kwargs):
        raise AssertionError("cloud provider must not be called for private text mode")

    service = AIService(
        FakeSettings({"assistant_mode": "private"}),
        client_factory=fail_factory,
    )
    service.local_llm = ReadyLocalLLM()

    result = service.generate_reply_result("hello")

    assert result.text == "локальный ответ"
    assert result.provider == "local_llama"
    assert result.provider_label == "Local Llama"
    assert result.assistant_mode == "private"
    assert result.error == ""


def test_standard_assistant_mode_prefers_local_llama_before_cloud(tmp_path) -> None:
    calls: list[dict] = []

    class ReadyLocalLLM:
        def model_path(self) -> str:
            return str(tmp_path / "llama.gguf")

        def status(self):
            return SimpleNamespace(ready=True, detail="Local Llama backend ready.")

        def generate(self, _messages, *, temperature=0.35, max_tokens=300):
            _ = (temperature, max_tokens)
            return "локальный стандартный ответ"

    service = AIService(
        FakeSettings({"assistant_mode": "standard"}),
        client_factory=lambda **kwargs: FakeClient(calls, {}, **kwargs),
        sleep=lambda _: None,
    )
    service.local_llm = ReadyLocalLLM()

    result = service.generate_reply_result("hello")

    assert result.text == "локальный стандартный ответ"
    assert result.provider == "local_llama"
    assert calls == []


def test_ollama_backend_prefers_local_response_without_cloud_calls(monkeypatch) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    class FakeOllamaClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def get(self, path: str, **_kwargs):
            calls.append(("get", path, None))
            return FakeHttpxResponse({"models": [{"name": "llama3.2"}]})

        def post(self, path: str, *, json: dict | None = None, **_kwargs):
            calls.append(("post", path, json))
            return FakeHttpxResponse({"message": {"content": "ollama reply"}})

        def close(self) -> None:
            pass

    monkeypatch.setattr("core.ai.local_llm_service.httpx.Client", FakeOllamaClient)

    service = AIService(
        FakeSettings(
            {
                "assistant_mode": "standard",
                "local_llm_backend": "ollama",
                "local_llm_model": "llama3.2",
            }
        ),
        client_factory=lambda **kwargs: FakeClient([], {}, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("hello")

    assert result.text == "ollama reply"
    assert result.provider == "local_llama"
    assert result.provider_label == "Ollama"
    assert result.assistant_mode == "standard"
    assert result.privacy_guarantee == "local_first_with_fallback"
    assert result.fallback_used is False
    assert [call[0] for call in calls] == ["get", "get", "post"]
    assert calls[-1][1] == "/api/chat"
    assert calls[-1][2]["model"] == "llama3.2"
    assert calls[-1][2]["stream"] is False
    assert calls[-1][2]["messages"][0]["role"] == "system"
    assert calls[-1][2]["messages"][-1] == {"role": "user", "content": "hello"}


def test_ollama_private_mode_stays_cloud_free(monkeypatch) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    class FakeOllamaClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def get(self, path: str, **_kwargs):
            calls.append(("get", path, None))
            return FakeHttpxResponse({"models": [{"name": "llama3.2"}]})

        def post(self, path: str, *, json: dict | None = None, **_kwargs):
            calls.append(("post", path, json))
            return FakeHttpxResponse({"message": {"content": "private ollama reply"}})

        def close(self) -> None:
            pass

    monkeypatch.setattr("core.ai.local_llm_service.httpx.Client", FakeOllamaClient)

    service = AIService(
        FakeSettings(
            {
                "assistant_mode": "private",
                "local_llm_backend": "ollama",
                "local_llm_model": "llama3.2",
            }
        ),
        client_factory=lambda **kwargs: FakeClient([], {}, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("hello")

    assert result.text == "private ollama reply"
    assert result.provider == "local_llama"
    assert result.provider_label == "Ollama"
    assert result.assistant_mode == "private"
    assert result.error == ""
    assert [call[0] for call in calls] == ["get", "get", "post"]
    assert calls[-1][1] == "/api/chat"
    assert calls[-1][2]["model"] == "llama3.2"
    assert calls[-1][2]["messages"][-1] == {"role": "user", "content": "hello"}


def test_missing_provider_keys_uses_fallback(monkeypatch) -> None:
    for key in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    service = AIService(
        FakeSettings(
            registration={
                "groq_api_key": "",
                "cerebras_api_key": "",
                "gemini_api_key": "",
                "openrouter_api_key": "",
            }
        )
    )

    reply = service.generate_reply("привет")

    assert "ИИ сейчас недоступен" in reply
    assert "Local Llama model is not configured." in reply
    assert "Локальные команды продолжают работать." in reply


def test_network_settings_sanitizes_proxy_mode_and_timeout() -> None:
    service = AIService(
        FakeSettings(
            {
                "network": {
                    "proxy_mode": "bad-value",
                    "proxy_url": "http://proxy.local:8080",
                    "no_proxy": "",
                    "timeout_seconds": 999,
                }
            }
        )
    )

    network = service.network_settings()

    assert network.proxy_mode == "system"
    assert network.no_proxy == "localhost,127.0.0.1,::1"
    assert network.timeout_seconds == 12.0


def test_manual_proxy_constructs_explicit_httpx_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeHttpxClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def close(self) -> None:
            pass

    monkeypatch.setattr("core.ai.ai_service.httpx.Client", FakeHttpxClient)

    service = AIService(
        FakeSettings(
            {
                "network": {
                    "proxy_mode": "manual",
                    "proxy_url": "http://proxy.local:8080",
                    "no_proxy": "localhost,127.0.0.1,::1",
                    "timeout_seconds": 30,
                }
            }
        )
    )

    client = service._make_http_client()
    client.close()

    assert captured["proxy"] == "http://proxy.local:8080"
    assert captured["trust_env"] is False


@pytest.mark.parametrize("mode", ["auto", "fast", "quality"])
def test_every_public_cloud_mode_has_a_provider_plan(mode: str) -> None:
    service = AIService(FakeSettings({"ai_mode": mode}))

    assert service.provider_plan()



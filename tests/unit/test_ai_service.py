from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.ai.ai_service import AIService


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

    assert [attempt.provider for attempt in plan] == ["groq", "cerebras"]


def test_ai_mode_request_options_are_distinct() -> None:
    service = AIService(FakeSettings())

    fast = service._mode_request_options("fast")
    auto = service._mode_request_options("auto")
    quality = service._mode_request_options("quality")

    assert fast["max_tokens"] < auto["max_tokens"] < quality["max_tokens"]
    assert fast["temperature"] != quality["temperature"]


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


def test_local_mode_does_not_call_cloud_provider() -> None:
    def fail_factory(**_kwargs):
        raise AssertionError("cloud provider must not be called in local mode")

    service = AIService(
        FakeSettings({"ai_mode": "local"}),
        client_factory=fail_factory,
    )

    assert "Локальный ИИ пока не подключён" in service.generate_reply("привет")


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

    assert "базовом режиме" in service.generate_reply("привет")


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

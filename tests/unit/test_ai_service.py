from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.ai.ai_service import AIService, sanitize_ai_reply_text


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
        result = self.behavior.get((self.base_url, str(payload.get("model") or "").strip()))
        if result is None:
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


def test_generate_reply_result_sanitizes_markdown_tables_and_long_lists() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": (
            "**Сводка**\n"
            "| Пункт | Значение |\n"
            "|---|---|\n"
            "| Один | Да |\n\n"
            "- Первый\n- Второй\n- Третий\n- Четвертый\n- Пятый\n- Шестой"
        )
    }
    service = AIService(
        FakeSettings({"ai_mode": "fast", "ai_provider": "groq"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("сделай кратко")

    assert result.provider == "groq"
    assert result.text.startswith("Сводка")
    assert "|" not in result.text
    assert "**" not in result.text
    assert len(result.text.splitlines()) <= 5


def test_sanitize_ai_reply_text_removes_tables_and_markdown() -> None:
    raw = "**Сводка**\n| A | B |\n|---|---|\n1. Первый\n2. Второй\n3. Третий\n4. Четвертый\n5. Пятый\n6. Шестой"

    clean = sanitize_ai_reply_text(raw)

    assert clean.startswith("Сводка")
    assert "|" not in clean
    assert "**" not in clean
    assert len(clean.splitlines()) <= 5


def test_quality_mode_prioritizes_quality_plan() -> None:
    service = AIService(FakeSettings({"ai_mode": "quality"}))

    plan = service.provider_plan()

    assert [attempt.provider for attempt in plan][:3] == ["gemini", "groq", "cerebras"]
    assert plan[0].model == "gemini-3-flash-preview"


def test_fast_mode_prefers_low_latency_provider_order() -> None:
    service = AIService(FakeSettings({"ai_mode": "fast"}))

    plan = service.provider_plan()

    assert [(attempt.provider, attempt.model) for attempt in plan[:2]] == [
        ("groq", "openai/gpt-oss-20b"),
        ("cerebras", "llama3.1-8b"),
    ]
    assert ("groq", "openai/gpt-oss-120b") in [(attempt.provider, attempt.model) for attempt in plan]


def test_ai_mode_request_options_are_distinct() -> None:
    service = AIService(FakeSettings())

    fast = service._mode_request_options("fast")
    auto = service._mode_request_options("auto")
    quality = service._mode_request_options("quality")

    assert fast["max_tokens"] < auto["max_tokens"] < quality["max_tokens"]
    assert fast["temperature"] != quality["temperature"]


def test_build_messages_uses_mode_specific_context_windows() -> None:
    service = AIService(FakeSettings())
    history = []
    for index in range(1, 6):
        history.extend(
            [
                {"role": "user", "text": f"вопрос {index}"},
                {"role": "assistant", "text": f"ответ {index}"},
            ]
        )

    fast_messages = service._build_messages("как дела", history, mode="fast")
    standard_messages = service._build_messages("как дела", history, mode="standard")
    smart_messages = service._build_messages("как дела", history, mode="smart")

    assert len(fast_messages) < len(standard_messages) < len(smart_messages)
    assert "Режим fast" in fast_messages[0]["content"]
    assert "Режим standard" in standard_messages[0]["content"]
    assert "Режим smart" in smart_messages[0]["content"]
    assert "Отвечай на языке пользователя" in standard_messages[0]["content"]
    assert "не переводи такие запросы сразу в уточнение" in standard_messages[0]["content"].casefold()
    assert "Ответь полностью по-русски." in standard_messages[-1]["content"]
    assert "Не начинай с вопроса-уточнения." in standard_messages[-1]["content"]
    assert "Уложись в 2-4 коротких предложения без воды." in fast_messages[-1]["content"]
    assert "самые полезные детали" in smart_messages[-1]["content"]


def test_build_messages_keeps_plain_prompt_when_no_extra_hints_are_needed() -> None:
    service = AIService(FakeSettings())

    messages = service._build_messages("open youtube", [], mode="auto")

    assert messages[-1]["content"] == "open youtube"


def test_build_messages_discourages_english_game_titles_on_russian_prompts() -> None:
    service = AIService(FakeSettings())

    messages = service._build_messages("как пройти FNAF 4", [], mode="fast")

    assert "Ответь полностью по-русски." in messages[-1]["content"]
    assert "не начинай с английского заголовка" in messages[-1]["content"].casefold()


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


def test_fast_mode_can_fallback_to_same_provider_quality_model_after_empty_response() -> None:
    calls: list[dict] = []
    behavior = {
        ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b"): "",
        ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"): "быстрый резервный ответ",
    }
    service = AIService(
        FakeSettings({"ai_mode": "fast", "ai_provider": "groq"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("как пройти FNAF 4")

    assert result.text == "быстрый резервный ответ"
    assert result.provider == "groq"
    assert result.model == "openai/gpt-oss-120b"
    assert result.fallback_used is True
    assert [call["model"] for call in calls] == [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ]


def test_standard_assistant_mode_prefers_cloud_when_local_llama_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: False)

    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": "балансный ответ",
    }
    service = AIService(
        FakeSettings({"assistant_mode": "standard"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    stages: list[str] = []
    result = service.generate_reply_result("как дела", status_callback=stages.append)

    assert result.mode == "standard"
    assert result.provider == "groq"
    assert result.text == "балансный ответ"
    assert stages and stages[0].startswith("Стандартный режим")
    assert [call["base_url"] for call in calls] == ["https://api.groq.com/openai/v1"]


def test_standard_assistant_mode_prefers_cloud_even_when_local_llama_is_ready(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: True)

    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": "стандартный облачный ответ",
    }
    service = AIService(
        FakeSettings({"assistant_mode": "standard"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("как дела")

    assert result.mode == "standard"
    assert result.provider == "groq"
    assert result.text == "стандартный облачный ответ"
    assert [call["base_url"] for call in calls] == ["https://api.groq.com/openai/v1"]


def test_standard_assistant_mode_ignores_stale_local_override_when_cloud_fallback_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: True)

    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": "стандартный ответ без локальной деградации",
    }
    service = AIService(
        FakeSettings(
            {
                "assistant_mode": "standard",
                "text_backend_override": "local_llama",
                "allow_text_cloud_fallback": True,
            }
        ),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("как дела")

    assert result.mode == "standard"
    assert result.provider == "groq"
    assert result.text == "стандартный ответ без локальной деградации"
    assert [call["base_url"] for call in calls] == ["https://api.groq.com/openai/v1"]


def test_standard_assistant_mode_keeps_explicit_local_override_when_cloud_fallback_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: True)

    service = AIService(
        FakeSettings(
            {
                "assistant_mode": "standard",
                "text_backend_override": "local_llama",
                "allow_text_cloud_fallback": False,
            }
        ),
        client_factory=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("cloud provider should not be used")),
        sleep=lambda _: None,
    )
    service._try_local_llama = lambda _messages: ("локальный ответ", None)  # type: ignore[method-assign]

    result = service.generate_reply_result("как дела")

    assert result.mode == "standard"
    assert result.provider == "local_llama"
    assert result.text == "локальный ответ"


def test_standard_assistant_mode_uses_balanced_request_options(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: False)

    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": "сбалансированный ответ",
    }
    service = AIService(
        FakeSettings({"assistant_mode": "standard"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("как пройти FNAF 4")

    assert result.provider == "groq"
    assert calls[0]["temperature"] == 0.35
    assert calls[0]["max_tokens"] == 300


def test_standard_and_smart_modes_use_different_request_modes(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: False)

    standard_service = AIService(
        FakeSettings({"assistant_mode": "standard"}),
        client_factory=lambda **kwargs: FakeClient([], {"https://api.groq.com/openai/v1": "standard"}, **kwargs),
        sleep=lambda _: None,
    )
    smart_service = AIService(
        FakeSettings({"assistant_mode": "smart"}),
        client_factory=lambda **kwargs: FakeClient([], {"https://generativelanguage.googleapis.com/v1beta/openai": "smart"}, **kwargs),
        sleep=lambda _: None,
    )

    assert standard_service._assistant_mode_request_mode("standard") == "auto"
    assert smart_service._assistant_mode_request_mode("smart") == "quality"


def test_smart_assistant_mode_uses_quality_route_and_request_mode(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: False)

    calls: list[dict] = []
    behavior = {
        "https://generativelanguage.googleapis.com/v1beta/openai": "умный ответ",
    }
    service = AIService(
        FakeSettings({"assistant_mode": "smart"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    stages: list[str] = []
    result = service.generate_reply_result("как пройти FNAF 4", status_callback=stages.append)

    assert result.mode == "smart"
    assert result.provider == "gemini"
    assert result.text == "умный ответ"
    assert stages and stages[0].startswith("Умный режим")
    assert calls[0]["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert calls[0]["temperature"] == 0.55
    assert calls[0]["max_tokens"] == 560


def test_fast_assistant_mode_can_fallback_to_same_provider_quality_model(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: False)

    calls: list[dict] = []
    behavior = {
        ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b"): "",
        ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"): "резервный быстрый ответ",
    }
    service = AIService(
        FakeSettings({"assistant_mode": "fast"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("как пройти FNAF 4")

    assert result.mode == "fast"
    assert result.provider == "groq"
    assert result.model == "openai/gpt-oss-120b"
    assert result.text == "резервный быстрый ответ"
    assert result.fallback_used is True
    assert [call["model"] for call in calls] == [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ]


def test_private_assistant_mode_refuses_cloud_without_fallback(monkeypatch) -> None:
    monkeypatch.setattr("core.policy.assistant_mode.local_llama_ready", lambda _settings: False)

    def fail_factory(**_kwargs):
        raise AssertionError("private mode must not reach cloud providers")

    service = AIService(
        FakeSettings(
            {"assistant_mode": "private"},
            registration={
                "groq_api_key": "groq-key",
                "cerebras_api_key": "cerebras-key",
                "gemini_api_key": "gemini-key",
                "openrouter_api_key": "openrouter-key",
            },
        ),
        client_factory=fail_factory,
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("привет")

    assert result.mode == "private"
    assert result.error == "local_llama_missing"
    assert "локальная модель" in result.text.lower()


def test_legacy_local_mode_is_normalized_to_auto_without_cloud_calls(monkeypatch) -> None:
    for key in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    def fail_factory(**_kwargs):
        raise AssertionError("cloud provider must not be called for a legacy local mode value")

    service = AIService(
        FakeSettings(
            {"ai_mode": "local"},
            registration={
                "groq_api_key": "",
                "cerebras_api_key": "",
                "gemini_api_key": "",
                "openrouter_api_key": "",
            },
        ),
        client_factory=fail_factory,
    )

    result = service.generate_reply_result("привет")

    assert result.mode == "auto"
    assert result.error == ""
    assert "local" not in result.text.lower()


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


def test_ai_fallback_does_not_expose_provider_details() -> None:
    calls: list[dict] = []
    behavior = {
        "https://api.groq.com/openai/v1": ProviderError(500),
    }
    service = AIService(
        FakeSettings({"ai_mode": "fast", "ai_provider": "groq"}),
        client_factory=lambda **kwargs: FakeClient(calls, behavior, **kwargs),
        sleep=lambda _: None,
    )

    result = service.generate_reply_result("что-то сломалось")

    assert "Groq" not in result.text
    assert "HTTP" not in result.text
    assert result.text == "Сейчас ответ не получился. Попробуйте ещё раз."


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



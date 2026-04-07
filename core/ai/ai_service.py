from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

import httpx
from openai import OpenAI


SYSTEM_PROMPT = """
Ты JARVIS Unity.
Отвечай быстро, умно и по делу.
Если пользователь просит бытовое действие или компьютерную команду, не болтай лишнего.
Если запрос касается действия на ПК, не утверждай, что оно уже выполнено, пока не получил реальный локальный результат.
Если данных не хватает, задай короткий вопрос.
Тон: спокойный, взрослый, уверенный.
""".strip()

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
AI_MODES = {"auto", "fast", "quality", "local"}
DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    api_key_field: str
    env_var: str
    models: dict[str, str]
    notes: str


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class NetworkSettings:
    proxy_mode: str
    proxy_url: str
    no_proxy: str
    timeout_seconds: float


PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        key="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_field="groq_api_key",
        env_var="GROQ_API_KEY",
        models={
            "auto": "openai/gpt-oss-20b",
            "fast": "openai/gpt-oss-20b",
            "quality": "openai/gpt-oss-120b",
        },
        notes="Fast OpenAI-compatible path; free/developer limits are provider-controlled.",
    ),
    "cerebras": ProviderSpec(
        key="cerebras",
        label="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_field="cerebras_api_key",
        env_var="CEREBRAS_API_KEY",
        models={
            "auto": "llama3.1-8b",
            "fast": "llama3.1-8b",
            "quality": "gpt-oss-120b",
        },
        notes="Fast OpenAI-compatible inference; free-tier model access is provider-controlled.",
    ),
    "gemini": ProviderSpec(
        key="gemini",
        label="Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_field="gemini_api_key",
        env_var="GEMINI_API_KEY",
        models={
            "auto": "gemini-3-flash-preview",
            "fast": "gemini-3-flash-preview",
            "quality": "gemini-3-flash-preview",
        },
        notes="Google AI Studio OpenAI-compatible endpoint; free-tier limits are provider-controlled.",
    ),
    "openrouter": ProviderSpec(
        key="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_field="openrouter_api_key",
        env_var="OPENROUTER_API_KEY",
        models={
            "auto": "openrouter/free",
            "fast": "openrouter/free",
            "quality": "openrouter/free",
        },
        notes="Last-resort free-model aggregator; daily limits and available models are dynamic.",
    ),
}

PROVIDER_PLANS: dict[str, tuple[str, ...]] = {
    "auto": ("groq", "cerebras", "gemini", "openrouter"),
    "fast": ("groq", "cerebras", "gemini", "openrouter"),
    "quality": ("gemini", "cerebras", "groq", "openrouter"),
    "local": (),
}


class AIService:
    def __init__(
        self,
        settings_service,
        *,
        client_factory: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings_service
        self._client_factory = client_factory or OpenAI
        self._sleep = sleep

    def generate_reply(self, user_text: str, history: list[dict[str, str]] | None = None) -> str:
        ai_mode = self._ai_mode()
        if ai_mode == "local":
            return self._local_unavailable_reply()

        messages = self._build_messages(user_text, history or [])
        attempts = self.provider_plan(ai_mode)
        if not attempts:
            return self._fallback_reply(user_text)

        last_error: str | None = None
        for attempt in attempts:
            spec = PROVIDERS[attempt.provider]
            api_key = self._provider_api_key(spec)
            if not api_key:
                continue

            reply, error = self._try_provider(spec, attempt.model, api_key, messages)
            if reply:
                return reply
            last_error = error or last_error

        return self._fallback_reply(user_text, last_error)

    def provider_plan(self, ai_mode: str | None = None) -> list[ProviderAttempt]:
        mode = self._normalize_mode(ai_mode or self._ai_mode())
        configured_provider = str(self.settings.get("ai_provider", "auto")).strip().lower()
        if mode == "local":
            return []
        if configured_provider in PROVIDERS:
            provider_keys = (configured_provider,)
        else:
            provider_keys = PROVIDER_PLANS[mode]

        seen: set[str] = set()
        attempts: list[ProviderAttempt] = []
        for provider_key in provider_keys:
            if provider_key in seen:
                continue
            seen.add(provider_key)
            spec = PROVIDERS[provider_key]
            attempts.append(ProviderAttempt(provider=provider_key, model=spec.models[mode]))
        return attempts

    def network_settings(self) -> NetworkSettings:
        raw = self.settings.get("network", {})
        if not isinstance(raw, dict):
            raw = {}

        proxy_mode = str(raw.get("proxy_mode", "system")).strip().lower()
        if proxy_mode not in {"system", "manual", "off"}:
            proxy_mode = "system"

        timeout_seconds = raw.get("timeout_seconds", 12.0)
        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            timeout = 12.0
        timeout = min(max(timeout, 3.0), 12.0)

        return NetworkSettings(
            proxy_mode=proxy_mode,
            proxy_url=str(raw.get("proxy_url", "")).strip(),
            no_proxy=str(raw.get("no_proxy", DEFAULT_NO_PROXY)).strip() or DEFAULT_NO_PROXY,
            timeout_seconds=timeout,
        )

    def _try_provider(
        self,
        spec: ProviderSpec,
        model: str,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> tuple[str | None, str | None]:
        max_attempts = int(self.settings.get("ai_max_attempts", 1) or 1)
        max_attempts = min(max(max_attempts, 1), 1)
        last_error: str | None = None

        for attempt_index in range(max_attempts):
            http_client: httpx.Client | None = None
            try:
                http_client = self._make_http_client()
                client = self._client_factory(
                    api_key=api_key,
                    base_url=spec.base_url,
                    http_client=http_client,
                    default_headers=self._default_headers(spec),
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.4,
                    timeout=self.network_settings().timeout_seconds,
                )
                text = self._extract_text(response)
                if text:
                    return text, None
                last_error = f"{spec.label}: empty response"
            except Exception as exc:  # noqa: BLE001 - provider SDKs wrap transport errors differently.
                last_error = f"{spec.label}: {self._describe_error(exc)}"
                if not self._is_retryable(exc):
                    break
                if attempt_index < max_attempts - 1:
                    self._sleep(0.2 * (2**attempt_index))
            finally:
                if http_client is not None:
                    http_client.close()
        return None, last_error

    def _make_http_client(self) -> httpx.Client:
        network = self.network_settings()
        timeout = httpx.Timeout(network.timeout_seconds)
        if network.proxy_mode == "manual" and network.proxy_url:
            return httpx.Client(proxy=network.proxy_url, timeout=timeout, trust_env=False)
        if network.proxy_mode == "off":
            return httpx.Client(timeout=timeout, trust_env=False)
        return httpx.Client(timeout=timeout, trust_env=True)

    def _default_headers(self, spec: ProviderSpec) -> dict[str, str]:
        if spec.key != "openrouter":
            return {}
        return {
            "HTTP-Referer": "https://github.com/theclepro1-hub/Jarvis.AI",
            "X-Title": "JarvisAi Unity",
        }

    def _provider_api_key(self, spec: ProviderSpec) -> str:
        registration = self.settings.get_registration()
        configured = str(registration.get(spec.api_key_field, "")).strip()
        if configured:
            return configured

        # Environment fallback keeps advanced/dev provider keys out of the UI.
        import os

        return os.environ.get(spec.env_var, "").strip()

    def _ai_mode(self) -> str:
        return self._normalize_mode(str(self.settings.get("ai_mode", "auto")).strip().lower())

    def _normalize_mode(self, value: str) -> str:
        if value in AI_MODES:
            return value
        return "auto"

    def _build_messages(self, user_text: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in history[-6:]:
            role = str(item.get("role", "")).strip()
            if role not in {"user", "assistant"}:
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": user_text})
        return messages

    def _extract_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", "")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content or "").strip()

    def _is_retryable(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code in RETRYABLE_STATUS_CODES:
            return True
        name = exc.__class__.__name__.lower()
        return any(marker in name for marker in ("timeout", "ratelimit", "connection"))

    def _describe_error(self, exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        if status_code:
            return f"HTTP {status_code}"
        return exc.__class__.__name__

    def _fallback_reply(self, user_text: str, last_error: str | None = None) -> str:
        lower = user_text.lower()
        if "кто ты" in lower:
            return (
                "Я JARVIS Unity. Быстрый desktop-ассистент для диалога, голоса "
                "и локальных действий."
            )
        if "настрой" in lower or "регистрац" in lower:
            return "Откройте настройки подключения: там можно изменить ключи Groq и Telegram."
        if last_error:
            return f"ИИ сейчас недоступен ({last_error}). Локальные команды продолжают работать."
        return (
            "Понял. Сейчас я работаю в базовом режиме без доступного AI-провайдера, "
            "но локальные команды продолжают работать."
        )

    def _local_unavailable_reply(self) -> str:
        return (
            "Локальный ИИ пока не подключён в этой сборке. Переключите режим ИИ на "
            "«Авто», «Быстро» или «Качество»."
        )

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
SUPPORTED_AI_MODES = ("auto", "fast", "quality", "local")
SUPPORTED_AI_MODE_SET = frozenset(SUPPORTED_AI_MODES)
SUPPORTED_AI_PROFILES = ("auto", "local", "groq_fast", "cerebras_fast", "gemini_quality", "openrouter_free")
AI_MODES = SUPPORTED_AI_MODE_SET
DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"
AI_MODE_BUDGET_SECONDS: dict[str, float] = {
    "auto": 5.0,
    "fast": 2.5,
    "quality": 9.0,
    "local": 2.0,
}


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


@dataclass(frozen=True, slots=True)
class AIReplyResult:
    text: str
    mode: str
    provider: str = ""
    provider_label: str = ""
    model: str = ""
    elapsed_ms: int = 0
    fallback_used: bool = False
    error: str = ""


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
    "fast": ("groq", "cerebras"),
    "quality": ("gemini", "groq", "cerebras", "openrouter"),
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
        return self.generate_reply_result(user_text, history).text

    def generate_reply_result(
        self,
        user_text: str,
        history: list[dict[str, str]] | None = None,
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> AIReplyResult:
        ai_mode = self._ai_mode()
        started_at = time.perf_counter()
        messages = self._build_messages(user_text, history or [])
        attempts = self.provider_plan(ai_mode)
        if not attempts:
            reply = self._fallback_reply(user_text)
            error = "" if ai_mode == "local" else "no_provider_attempts"
            return AIReplyResult(
                text=reply,
                mode=ai_mode,
                elapsed_ms=self._elapsed_ms(started_at),
                error=error,
            )

        budget_seconds = self._mode_budget_seconds(ai_mode)
        last_error: str | None = None
        for index, attempt in enumerate(attempts):
            elapsed = time.perf_counter() - started_at
            remaining_budget = budget_seconds - elapsed
            if remaining_budget <= 0:
                last_error = f"latency budget exceeded ({ai_mode})"
                break
            spec = PROVIDERS[attempt.provider]
            api_key = self._provider_api_key(spec)
            if not api_key:
                continue
            self._report_stage(
                status_callback,
                self._attempt_stage_label(
                    ai_mode=ai_mode,
                    spec=spec,
                    model=attempt.model,
                    attempt_index=index,
                    attempts_total=len(attempts),
                ),
            )

            reply, error = self._try_provider(
                spec,
                attempt.model,
                api_key,
                messages,
                ai_mode=ai_mode,
                budget_seconds=remaining_budget,
            )
            if reply:
                return AIReplyResult(
                    text=reply,
                    mode=ai_mode,
                    provider=spec.key,
                    provider_label=spec.label,
                    model=attempt.model,
                    elapsed_ms=self._elapsed_ms(started_at),
                    fallback_used=index > 0,
                )
            last_error = error or last_error
            if index < len(attempts) - 1:
                next_spec = PROVIDERS[attempts[index + 1].provider]
                self._report_stage(
                    status_callback,
                    self._fallback_stage_label(spec, next_spec),
                )

        return AIReplyResult(
            text=self._fallback_reply(user_text, last_error),
            mode=ai_mode,
            elapsed_ms=self._elapsed_ms(started_at),
            fallback_used=len(attempts) > 1,
            error=last_error or "",
        )

    def provider_plan(self, ai_mode: str | None = None) -> list[ProviderAttempt]:
        mode = self._normalize_mode(ai_mode or self._ai_mode())
        if mode == "local":
            return []
        configured_provider = str(self.settings.get("ai_provider", "auto")).strip().lower()
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
        *,
        ai_mode: str,
        budget_seconds: float,
    ) -> tuple[str | None, str | None]:
        max_attempts = int(self.settings.get("ai_max_attempts", 1) or 1)
        max_attempts = min(max(max_attempts, 1), 3)
        last_error: str | None = None
        started_at = time.perf_counter()
        request_options = self._mode_request_options(ai_mode)

        for attempt_index in range(max_attempts):
            http_client: httpx.Client | None = None
            try:
                elapsed = time.perf_counter() - started_at
                remaining_budget = budget_seconds - elapsed
                if remaining_budget <= 0:
                    break
                http_client = self._make_http_client()
                client = self._client_factory(
                    api_key=api_key,
                    base_url=spec.base_url,
                    http_client=http_client,
                    default_headers=self._default_headers(spec),
                )
                request_timeout = max(0.8, min(self.network_settings().timeout_seconds, remaining_budget))
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=request_timeout,
                    **request_options,
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

    def _mode_budget_seconds(self, mode: str) -> float:
        if mode in AI_MODE_BUDGET_SECONDS:
            return AI_MODE_BUDGET_SECONDS[mode]
        return AI_MODE_BUDGET_SECONDS["auto"]

    def _mode_request_options(self, mode: str) -> dict[str, float | int]:
        if mode == "fast":
            return {
                "temperature": 0.2,
                "max_tokens": 160,
            }
        if mode == "quality":
            return {
                "temperature": 0.55,
                "max_tokens": 560,
            }
        if mode == "local":
            return {
                "temperature": 0.0,
                "max_tokens": 120,
            }
        return {
            "temperature": 0.35,
            "max_tokens": 300,
        }

    def _attempt_stage_label(
        self,
        *,
        ai_mode: str,
        spec: ProviderSpec,
        model: str,
        attempt_index: int,
        attempts_total: int,
    ) -> str:
        mode_label = {
            "fast": "Быстрый режим",
            "quality": "Качество",
            "auto": "Авто-режим",
        }.get(ai_mode, "ИИ")
        if attempts_total <= 1:
            return f"{mode_label}: {spec.label}..."
        return f"{mode_label}: {spec.label} ({attempt_index + 1}/{attempts_total})..."

    def _fallback_stage_label(self, current: ProviderSpec, next_spec: ProviderSpec) -> str:
        return f"{current.label} не ответил, переключаюсь на {next_spec.label}..."

    def _report_stage(self, callback: Callable[[str], None] | None, text: str) -> None:
        if callback is None:
            return
        clean = str(text or "").strip()
        if clean:
            callback(clean)

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))

    def _normalize_mode(self, value: str) -> str:
        if value in AI_MODES:
            return value
        return "auto"

    def available_modes(self) -> tuple[str, ...]:
        return SUPPORTED_AI_MODES

    def available_profiles(self) -> tuple[str, ...]:
        return SUPPORTED_AI_PROFILES

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



from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable

import httpx
from openai import OpenAI

from core.ai.local_llm_service import LocalLLMService, LocalLLMUnavailableError
from core.routing.text_ai_policy import ResolvedTextAIRoute, resolve_text_ai_route


SYSTEM_PROMPT = """
Ты JARVIS Unity.
Отвечай быстро, умно и по делу.
Если пользователь просит бытовое действие или компьютерную команду, не болтай лишнего.
Если запрос касается действия на ПК, не утверждай, что оно уже выполнено, пока не получил реальный локальный результат.
Если данных не хватает, задай короткий вопрос.
Тон: спокойный, взрослый, уверенный.
""".strip()

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
SUPPORTED_AI_MODES = ("auto", "fast", "quality")
SUPPORTED_AI_MODE_SET = frozenset(SUPPORTED_AI_MODES)
SUPPORTED_AI_PROFILES = ("auto", "groq_fast", "cerebras_fast", "gemini_quality", "openrouter_free")
AI_MODES = SUPPORTED_AI_MODE_SET
DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"
PRIVATE_TEXT_BACKEND_ERROR = "private_text_backend_unavailable"
AI_MODE_BUDGET_SECONDS: dict[str, float] = {
    "auto": 5.0,
    "fast": 2.5,
    "quality": 9.0,
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
    assistant_mode: str = ""
    privacy_guarantee: str = ""
    route_summary: str = ""


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
        self.local_llm = LocalLLMService(settings_service)

    def generate_reply(self, user_text: str, history: list[dict[str, str]] | None = None) -> str:
        return self.generate_reply_result(user_text, history).text

    def generate_reply_result(
        self,
        user_text: str,
        history: list[dict[str, str]] | None = None,
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> AIReplyResult:
        route = self._resolved_text_route()
        ai_mode = route.legacy_mode
        started_at = time.perf_counter()
        messages = self._build_messages(user_text, history or [])
        attempts = self.provider_plan(route=route)
        if not attempts:
            if route.assistant_mode == "private":
                detail = self.local_llm.status().detail
                return AIReplyResult(
                    text=self._private_text_backend_reply(detail),
                    mode=ai_mode,
                    elapsed_ms=self._elapsed_ms(started_at),
                    error=PRIVATE_TEXT_BACKEND_ERROR,
                    assistant_mode=route.assistant_mode,
                    privacy_guarantee=route.privacy_guarantee,
                    route_summary=route.summary,
                )
            reply = self._fallback_reply(user_text)
            return AIReplyResult(
                text=reply,
                mode=ai_mode,
                elapsed_ms=self._elapsed_ms(started_at),
                error="no_provider_attempts",
                assistant_mode=route.assistant_mode,
                privacy_guarantee=route.privacy_guarantee,
                route_summary=route.summary,
            )

        budget_seconds = self._mode_budget_seconds(route.request_profile)
        last_error: str | None = None
        for index, attempt in enumerate(attempts):
            elapsed = time.perf_counter() - started_at
            remaining_budget = budget_seconds - elapsed
            if remaining_budget <= 0:
                last_error = f"latency budget exceeded ({route.assistant_mode})"
                break
            self._report_stage(
                status_callback,
                self._attempt_stage_label(
                    ai_mode=self._stage_mode_key(route),
                    provider_label=self._provider_label(attempt.provider),
                    model=attempt.model,
                    attempt_index=index,
                    attempts_total=len(attempts),
                ),
            )

            if attempt.provider == "local_llama":
                reply, error = self._try_local_llama(messages, ai_mode=route.request_profile)
            else:
                spec = PROVIDERS[attempt.provider]
                api_key = self._provider_api_key(spec)
                if not api_key:
                    continue
                reply, error = self._try_provider(
                    spec,
                    attempt.model,
                    api_key,
                    messages,
                    ai_mode=route.request_profile,
                    budget_seconds=remaining_budget,
                )
            if reply:
                return AIReplyResult(
                    text=reply,
                    mode=ai_mode,
                    provider=attempt.provider,
                    provider_label=self._provider_label(attempt.provider),
                    model=attempt.model,
                    elapsed_ms=self._elapsed_ms(started_at),
                    fallback_used=index > 0,
                    assistant_mode=route.assistant_mode,
                    privacy_guarantee=route.privacy_guarantee,
                    route_summary=route.summary,
                )
            last_error = error or last_error
            if index < len(attempts) - 1:
                self._report_stage(
                    status_callback,
                    self._fallback_stage_label(attempt.provider, attempts[index + 1].provider),
                )

        if route.assistant_mode == "private":
            return AIReplyResult(
                text=self._private_text_backend_reply(last_error),
                mode=ai_mode,
                elapsed_ms=self._elapsed_ms(started_at),
                error=PRIVATE_TEXT_BACKEND_ERROR,
                assistant_mode=route.assistant_mode,
                privacy_guarantee=route.privacy_guarantee,
                route_summary=route.summary,
            )

        return AIReplyResult(
            text=self._fallback_reply(user_text, last_error),
            mode=ai_mode,
            elapsed_ms=self._elapsed_ms(started_at),
            fallback_used=len(attempts) > 1,
            error=last_error or "",
            assistant_mode=route.assistant_mode,
            privacy_guarantee=route.privacy_guarantee,
            route_summary=route.summary,
        )

    def provider_plan(
        self,
        ai_mode: str | None = None,
        *,
        route: ResolvedTextAIRoute | None = None,
    ) -> list[ProviderAttempt]:
        route = route or self._resolved_text_route(ai_mode)
        if not route.provider_route:
            return []

        seen: set[str] = set()
        attempts: list[ProviderAttempt] = []
        for provider_key in route.provider_route:
            if provider_key in seen:
                continue
            seen.add(provider_key)
            if provider_key == "local_llama":
                attempts.append(
                    ProviderAttempt(
                        provider=provider_key,
                        model=self._local_model_label(),
                    )
                )
                continue
            spec = PROVIDERS[provider_key]
            attempts.append(
                ProviderAttempt(
                    provider=provider_key,
                    model=spec.models[route.request_profile],
                )
            )
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

    def _resolved_text_route(self, mode_hint: str | None = None) -> ResolvedTextAIRoute:
        return resolve_text_ai_route(self.settings, mode_hint=mode_hint)

    def _mode_budget_seconds(self, mode: str) -> float:
        if mode == "standard":
            mode = "auto"
        elif mode == "smart":
            mode = "quality"
        elif mode == "private":
            mode = "auto"
        if mode in AI_MODE_BUDGET_SECONDS:
            return AI_MODE_BUDGET_SECONDS[mode]
        return AI_MODE_BUDGET_SECONDS["auto"]

    def _mode_request_options(self, mode: str) -> dict[str, float | int]:
        if mode == "standard":
            mode = "auto"
        elif mode == "smart":
            mode = "quality"
        elif mode == "private":
            mode = "auto"
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
        return {
            "temperature": 0.35,
            "max_tokens": 300,
        }

    def _attempt_stage_label(
        self,
        *,
        ai_mode: str,
        provider_label: str,
        model: str,
        attempt_index: int,
        attempts_total: int,
    ) -> str:
        mode_label = {
            "fast": "Быстрый режим",
            "standard": "Стандартный режим",
            "smart": "Умный режим",
            "private": "Приватный режим",
            "quality": "Умный режим",
            "auto": "Стандартный режим",
        }.get(ai_mode, "ИИ")
        if attempts_total <= 1:
            return f"{mode_label}: {provider_label}…"
        return f"{mode_label}: {provider_label} ({attempt_index + 1}/{attempts_total})…"

    def _fallback_stage_label(self, current_provider: str, next_provider: str) -> str:
        current_label = self._provider_label(current_provider)
        next_label = self._provider_label(next_provider)
        return f"{current_label} не ответил, переключаюсь на {next_label}…"

    def _report_stage(self, callback: Callable[[str], None] | None, text: str) -> None:
        if callback is None:
            return
        clean = str(text or "").strip()
        if clean:
            callback(clean)

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))

    def _stage_mode_key(self, route: ResolvedTextAIRoute) -> str:
        return route.assistant_mode or route.legacy_mode

    def _provider_label(self, provider_key: str) -> str:
        if provider_key == "local_llama":
            backend_label = getattr(self.local_llm, "backend_label", None)
            if callable(backend_label):
                label = str(backend_label() or "").strip()
                if label:
                    return label
            return "Local Llama"
        spec = PROVIDERS.get(provider_key)
        if spec is not None:
            return spec.label
        return provider_key

    def _local_model_label(self) -> str:
        model_label = getattr(self.local_llm, "model_label", None)
        if callable(model_label):
            label = str(model_label() or "").strip()
            if label:
                return label

        model_path = str(getattr(self.local_llm, "model_path", lambda: "")() or "").strip()
        if not model_path:
            return "llama.cpp"
        return Path(model_path).name or model_path

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

    def _try_local_llama(
        self,
        messages: list[dict[str, str]],
        *,
        ai_mode: str,
    ) -> tuple[str | None, str | None]:
        options = self._mode_request_options(ai_mode)
        try:
            reply = self.local_llm.generate(
                messages,
                temperature=float(options["temperature"]),
                max_tokens=int(options["max_tokens"]),
            )
        except LocalLLMUnavailableError as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001
            return None, self._describe_error(exc)
        return reply, None

    def _private_text_backend_reply(self, detail: str | None = None) -> str:
        detail_text = str(detail or "").strip()
        if detail_text:
            return (
                "Приватный режим для текста включён, но локальная Llama не готова "
                f"({detail_text}). Облачные провайдеры для текста не использовались."
            )
        return (
            "Приватный режим для текста включён, но локальная Llama не готова. "
            "Облачные провайдеры для текста не использовались."
        )

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



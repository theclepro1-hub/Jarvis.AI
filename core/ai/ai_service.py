from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any, Callable

import httpx
from openai import OpenAI

from core.policy.assistant_mode import resolve_assistant_mode, resolve_assistant_policy
from core.ai.reply_text import SUPPORTED_AI_MODES, sanitize_ai_reply_text


SYSTEM_PROMPT = """
Ты JARVIS Unity.
Отвечай быстро, коротко и по делу.
Отвечай на языке пользователя. Если пользователь пишет по-русски, не переходи на английский без явной причины.
Не используй markdown-таблицы, длинные списки и простыни.
Если запрос касается действия на ПК, не утверждай, что оно уже выполнено, пока не получил реальный локальный результат.
На общие вопросы вроде "как", "что", "почему" или "как пройти" сначала дай короткий полезный ответ по существу; не переводи такие запросы сразу в уточнение.
Один короткий уточняющий вопрос задавай только если без него ответ будет пустым, нечестным или рискованным.
Тон: спокойный, взрослый, уверенный.
""".strip()

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
SUPPORTED_AI_MODE_SET = frozenset(SUPPORTED_AI_MODES)
SUPPORTED_AI_PROFILES = ("auto", "groq_fast", "cerebras_fast", "gemini_quality", "openrouter_free")
AI_MODES = SUPPORTED_AI_MODE_SET
DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"
AI_MODE_BUDGET_SECONDS: dict[str, float] = {
    "auto": 5.0,
    "fast": 4.5,
    "quality": 9.0,
}
MODE_CONTEXT_WINDOWS: dict[str, int] = {
    "auto": 6,
    "fast": 4,
    "quality": 8,
    "standard": 6,
    "smart": 8,
    "private": 6,
}
_CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
_DIRECT_ANSWER_PREFIXES = (
    "как ",
    "что ",
    "почему ",
    "зачем ",
    "когда ",
    "где ",
    "кто ",
    "сколько ",
    "расскажи",
    "объясни",
    "подскажи",
    "посоветуй",
    "как пройти",
    "как настроить",
    "как сделать",
)


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
        if self._assistant_mode_enabled():
            return self._generate_assistant_mode_reply(user_text, history or [], status_callback=status_callback)

        ai_mode = self._ai_mode()
        started_at = time.perf_counter()
        messages = self._build_messages(user_text, history or [], mode=ai_mode)
        attempts = self.provider_plan(ai_mode)
        if not attempts:
            reply = self._fallback_reply(user_text)
            return AIReplyResult(
                text=reply,
                mode=ai_mode,
                elapsed_ms=self._elapsed_ms(started_at),
                error="no_provider_attempts",
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
                next_attempt = attempts[index + 1]
                next_spec = PROVIDERS[next_attempt.provider]
                self._report_stage(
                    status_callback,
                    self._fallback_stage_label(spec, attempt.model, next_spec, next_attempt.model),
                )

        return AIReplyResult(
            text=self._fallback_reply(user_text, last_error),
            mode=ai_mode,
            elapsed_ms=self._elapsed_ms(started_at),
            fallback_used=len(attempts) > 1,
            error=last_error or "",
        )

    def _generate_assistant_mode_reply(
        self,
        user_text: str,
        history: list[dict[str, str]],
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> AIReplyResult:
        mode = resolve_assistant_mode(self.settings)
        policy = resolve_assistant_policy(self.settings)
        started_at = time.perf_counter()
        messages = self._build_messages(user_text, history, mode=mode)
        budget_seconds = self._mode_budget_seconds(self._assistant_mode_request_mode(mode))
        last_error: str | None = None

        for index, backend in enumerate(policy.text_route):
            elapsed = time.perf_counter() - started_at
            remaining_budget = budget_seconds - elapsed
            if remaining_budget <= 0:
                last_error = f"latency budget exceeded ({mode})"
                break

            if backend == "local_llama":
                if "local_llama_missing" in policy.readiness_issues:
                    last_error = "local_llama_missing"
                    continue
                self._report_stage(status_callback, self._assistant_stage_label(mode, "Локальная Llama", index, len(policy.text_route)))
                reply, error = self._try_local_llama(messages)
                if reply:
                    return AIReplyResult(
                        text=reply,
                        mode=mode,
                        provider="local_llama",
                        provider_label="Local Llama",
                        model=str(self.settings.get("local_llm_model", "")).strip(),
                        elapsed_ms=self._elapsed_ms(started_at),
                        fallback_used=index > 0,
                    )
                last_error = error or last_error
                continue

            spec = PROVIDERS.get(backend)
            if spec is None:
                continue
            api_key = self._provider_api_key(spec)
            if not api_key:
                continue
            model_mode = self._assistant_mode_request_mode(mode)
            self._report_stage(status_callback, self._assistant_stage_label(mode, spec.label, index, len(policy.text_route)))
            model_candidates = self._provider_model_candidates(spec, model_mode)
            for model_index, model_name in enumerate(model_candidates):
                if model_index > 0:
                    self._report_stage(
                        status_callback,
                        self._assistant_stage_label(mode, f"{spec.label} (резервная модель)", index, len(policy.text_route)),
                    )
                reply, error = self._try_provider(
                    spec,
                    model_name,
                    api_key,
                    messages,
                    ai_mode=model_mode,
                    budget_seconds=remaining_budget,
                )
                if reply:
                    return AIReplyResult(
                        text=reply,
                        mode=mode,
                        provider=spec.key,
                        provider_label=spec.label,
                        model=model_name,
                        elapsed_ms=self._elapsed_ms(started_at),
                        fallback_used=index > 0 or model_index > 0,
                    )
                last_error = error or last_error

        if mode == "private" and not policy.text_cloud_allowed:
            return AIReplyResult(
                text="Нужна локальная модель Llama. Подключите Ollama или укажите .gguf в настройках для опытных.",
                mode=mode,
                elapsed_ms=self._elapsed_ms(started_at),
                fallback_used=False,
                error=last_error or "local_llama_missing",
            )

        return AIReplyResult(
            text=self._fallback_reply(user_text, last_error),
            mode=mode,
            elapsed_ms=self._elapsed_ms(started_at),
            fallback_used=len(policy.text_route) > 1,
            error=last_error or "",
        )

    def provider_plan(self, ai_mode: str | None = None) -> list[ProviderAttempt]:
        mode = self._normalize_mode(ai_mode or self._ai_mode())
        configured_provider = str(self.settings.get("ai_provider", "auto")).strip().lower()
        if configured_provider in PROVIDERS:
            provider_keys = (configured_provider,)
        else:
            provider_keys = PROVIDER_PLANS[mode]

        seen: set[tuple[str, str]] = set()
        attempts: list[ProviderAttempt] = []
        for provider_key in provider_keys:
            spec = PROVIDERS[provider_key]
            attempt = ProviderAttempt(provider=provider_key, model=spec.models[mode])
            identity = (attempt.provider, attempt.model)
            if identity in seen:
                continue
            seen.add(identity)
            attempts.append(attempt)

        # Some OpenAI-compatible providers intermittently return an empty body on
        # their lightweight fast model. Keep the fast lane reliable by allowing
        # one in-provider fallback to the provider's quality model before giving up.
        if mode == "fast":
            for provider_key in provider_keys:
                spec = PROVIDERS[provider_key]
                fallback_model = str(spec.models.get("quality", "")).strip()
                if not fallback_model or fallback_model == spec.models["fast"]:
                    continue
                attempt = ProviderAttempt(provider=provider_key, model=fallback_model)
                identity = (attempt.provider, attempt.model)
                if identity in seen:
                    continue
                seen.add(identity)
                attempts.append(attempt)
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
        network = self.network_settings()

        for attempt_index in range(max_attempts):
            http_client: httpx.Client | None = None
            try:
                elapsed = time.perf_counter() - started_at
                remaining_budget = budget_seconds - elapsed
                if remaining_budget <= 0:
                    break
                http_client = self._make_http_client(network)
                client = self._client_factory(
                    api_key=api_key,
                    base_url=spec.base_url,
                    http_client=http_client,
                    default_headers=self._default_headers(spec),
                )
                request_timeout = max(0.8, min(network.timeout_seconds, remaining_budget))
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=request_timeout,
                    **request_options,
                )
                text = sanitize_ai_reply_text(self._extract_text(response))
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

    def _make_http_client(self, network: NetworkSettings | None = None) -> httpx.Client:
        network = network or self.network_settings()
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

    def _assistant_mode_enabled(self) -> bool:
        return bool(str(self.settings.get("assistant_mode", "")).strip())

    def _provider_model_candidates(self, spec: ProviderSpec, mode: str) -> list[str]:
        primary = str(spec.models.get(mode, "")).strip()
        if not primary:
            return []
        models = [primary]
        if mode in {"auto", "fast"}:
            quality = str(spec.models.get("quality", "")).strip()
            if quality and quality != primary:
                models.append(quality)
        return models

    def _assistant_mode_request_mode(self, mode: str) -> str:
        if mode == "fast":
            return "fast"
        if mode == "standard":
            return "auto"
        if mode == "smart":
            return "quality"
        return "auto"

    def _assistant_stage_label(self, mode: str, label: str, index: int, total: int) -> str:
        mode_label = {
            "fast": "Быстрый режим",
            "standard": "Стандартный режим",
            "smart": "Умный режим",
            "private": "Приватный режим",
        }.get(mode, "ИИ")
        if total <= 1:
            return f"{mode_label}: {label}…"
        return f"{mode_label}: {label} ({index + 1}/{total})…"

    def _try_local_llama(self, messages: list[dict[str, str]]) -> tuple[str | None, str | None]:
        from core.ai.local_llm_service import LocalLLMService

        service = LocalLLMService(self.settings)
        try:
            reply = sanitize_ai_reply_text(service.generate(messages))
            if reply:
                return reply, None
            return None, "Local Llama: empty response"
        except Exception as exc:  # noqa: BLE001
            return None, f"Local Llama: {exc}"

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
                "max_tokens": 240,
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
            return f"{mode_label}: {spec.label}…"
        return f"{mode_label}: {spec.label} ({attempt_index + 1}/{attempts_total})…"

    def _fallback_stage_label(
        self,
        current: ProviderSpec,
        current_model: str,
        next_spec: ProviderSpec,
        next_model: str,
    ) -> str:
        if current.key == next_spec.key and current_model != next_model:
            return f"{current.label} не ответил, пробую резервную модель…"
        return f"{current.label} не ответил, переключаюсь на {next_spec.label}…"

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

    def _build_messages(self, user_text: str, history: list[dict[str, str]], *, mode: str = "auto") -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt_for_mode(mode)}]
        for item in history[-self._history_window_for_mode(mode):]:
            role = str(item.get("role", "")).strip()
            if role not in {"user", "assistant"}:
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            if role == "assistant":
                text = sanitize_ai_reply_text(text, max_lines=3, max_chars=400)
                if not text:
                    continue
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": self._augment_user_prompt(user_text, mode=mode)})
        return messages

    def _augment_user_prompt(self, user_text: str, *, mode: str) -> str:
        clean = str(user_text or "").strip()
        if not clean:
            return ""

        notes: list[str] = []
        if self._looks_russian_text(clean):
            notes.append("Ответь полностью по-русски.")
            notes.append(
                "Если в ответе есть название игры, приложения или сервиса, не начинай с английского заголовка; "
                "используй русское написание или короткое пояснение в начале."
            )
        if self._should_answer_directly(clean):
            notes.append("Сразу дай короткий ответ по существу. Не начинай с вопроса-уточнения.")
        if mode == "fast":
            notes.append("Уложись в 2-4 коротких предложения без воды.")
        elif mode == "smart":
            notes.append("Если нужно, добавь только самые полезные детали и не расползайся.")
        elif mode == "standard":
            notes.append("Сначала дай рабочий ответ, а уже потом при необходимости предложи уточнить.")

        if not notes:
            return clean
        return "Инструкция для ответа:\n- " + "\n- ".join(notes) + f"\n\nЗапрос пользователя:\n{clean}"

    def _looks_russian_text(self, text: str) -> bool:
        return bool(_CYRILLIC_PATTERN.search(str(text or "")))

    def _should_answer_directly(self, text: str) -> bool:
        clean = str(text or "").strip().casefold()
        if not clean:
            return False
        if clean.startswith(_DIRECT_ANSWER_PREFIXES):
            return True
        return "?" in clean and not self._looks_mostly_english(clean)

    def _looks_mostly_english(self, text: str) -> bool:
        sample = str(text or "")
        return bool(_LATIN_PATTERN.search(sample)) and not self._looks_russian_text(sample)

    def _history_window_for_mode(self, mode: str) -> int:
        normalized = self._normalize_mode(mode)
        if mode in MODE_CONTEXT_WINDOWS:
            return MODE_CONTEXT_WINDOWS[mode]
        return MODE_CONTEXT_WINDOWS.get(normalized, MODE_CONTEXT_WINDOWS["auto"])

    def _system_prompt_for_mode(self, mode: str) -> str:
        normalized = self._normalize_mode(mode)
        if mode == "private":
            note = "Режим private: держи ответы локальными, сдержанными и без ссылок на облако."
        elif mode == "smart" or normalized == "quality":
            note = "Режим smart: выбирай самый точный ответ и добавляй только нужные нюансы. На общий вопрос сначала дай полезный стартовый ответ, а не один вопрос-уточнение."
        elif mode == "fast":
            note = "Режим fast: отвечай как можно быстрее, короче и без лишней воды."
        elif mode == "standard" or normalized == "auto":
            note = "Режим standard: держи баланс между скоростью и качеством, отвечай естественно. На общий вопрос сначала дай короткий рабочий ответ, а потом при необходимости предложи уточнить."
        else:
            note = ""
        return f"{SYSTEM_PROMPT}\n{note}" if note else SYSTEM_PROMPT

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
            return "Откройте настройки подключения: там можно изменить ключи и режимы."
        if last_error:
            return "Сейчас ответ не получился. Попробуйте ещё раз."
        return "Сейчас я отвечаю в базовом режиме. Локальные команды продолжают работать."



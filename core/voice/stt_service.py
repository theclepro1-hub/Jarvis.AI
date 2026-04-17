from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np

from core.policy.assistant_mode import AssistantReadiness, resolve_assistant_policy
from core.routing.text_rules import normalize_text
from core.voice.faster_whisper_runtime import (
    can_auto_download_faster_whisper_model,
    find_existing_faster_whisper_model,
    load_faster_whisper_model,
    resolve_local_faster_whisper_model,
)
from core.voice.voice_models import TranscriptionResult

FASTER_WHISPER_CACHE_DIR = "faster-whisper"
DEFAULT_FASTER_WHISPER_MODEL = os.environ.get("JARVIS_UNITY_FASTER_WHISPER_MODEL", "small").strip() or "small"
COMMAND_HOTWORDS = ", ".join(
    (
        "джарвис",
        "жарвис",
        "жаравис",
        "дарвис",
        "гарри",
        "гарви",
        "гарвис",
        "рыж",
        "ютуб",
        "youtube",
        "steam",
        "discord",
        "браузер",
        "яндекс музыка",
        "музыка",
        "параметры",
        "проводник",
    )
)
COMMAND_PROMPT = (
    "Русские голосовые команды и короткий разговор с ассистентом в Windows. "
    "Джарвис, жарвис, жаравис, дарвис, гарри, гарви, горы, гори, гарий, рыж. "
    "Открой YouTube, Steam, Discord, браузер, Яндекс Музыку, параметры, проводник, "
    "панель управления. Сделай громче, сделай тише, заблокируй экран. "
    "Привет, как дела, что умеешь, почему."
)
WAKE_HOTWORDS = ", ".join(
    (
        "горы",
        "гори",
        "гарий",
        "джарвис",
        "жарвис",
        "жаравис",
        "дарвис",
        "гарри",
        "гарви",
        "гарвис",
        "гаривис",
        "джаврис",
        "джарви",
        "рыж",
    )
)
WAKE_PROMPT = (
    "Слово активации ассистента на русском: "
    "джарвис, жарвис, жаравис, дарвис, гарри, гарви, гарвис, гаривис, джаврис, джарви, горы, гори, гарий, рыж."
)
LOCAL_FASTER_WHISPER_BEAM_SIZE = 5
LOCAL_FASTER_WHISPER_BEST_OF = 4
LOCAL_FASTER_WHISPER_VAD = {
    "min_silence_duration_ms": 420,
    "speech_pad_ms": 320,
}
WAKE_FASTER_WHISPER_BEAM_SIZE = 4
WAKE_FASTER_WHISPER_BEST_OF = 4
WAKE_FASTER_WHISPER_VAD = {
    "min_silence_duration_ms": 220,
    "speech_pad_ms": 220,
}


class STTService:
    def __init__(self, settings_service, local_model_path: Path | None = None) -> None:
        self.settings = settings_service
        self._local_model_path_overridden = local_model_path is not None
        self._local_model_override = local_model_path
        self.faster_whisper_download_root = self._find_faster_whisper_download_root()
        self._http_client = None
        self._http_client_signature: tuple[str, str, float] | None = None

    def engine(self) -> str:
        value = self._configured_engine()
        if value != "auto":
            return value
        route = self._resolved_stt_route()
        return route[0] if route else "auto"

    def _configured_engine(self) -> str:
        value = str(self.settings.get("stt_engine", "auto")).strip().casefold()
        if value in {"groq", "groq_whisper"}:
            return "groq_whisper"
        if value in {"local", "whisper", "faster_whisper", "local_faster_whisper"}:
            return "local_faster_whisper"
        return "auto"

    def status_text(self) -> str:
        configured_engine = self._configured_engine()
        groq_key = self._groq_key()
        policy = self._assistant_policy()

        if configured_engine == "groq_whisper":
            return "Облачное распознавание готово" if groq_key else "Нужен ключ для облачного распознавания"
        if configured_engine == "local_faster_whisper":
            if self._local_faster_whisper_ready():
                return "локальное распознавание готово"
            if policy.stt_cloud_allowed:
                return "Нужен ключ для облачного распознавания или локальный backend распознавания речи"
            return "Нужен локальный backend распознавания речи"

        if policy.mode == "private":
            if self._local_faster_whisper_ready():
                return "локальное распознавание готово"
            return "Нужен локальный backend распознавания речи"

        if self._local_faster_whisper_ready():
            return "локальное распознавание готово"
        if groq_key:
            return "Облачное распознавание готово"
        return "Нужен ключ для облачного распознавания или локальный backend распознавания речи"

    def can_transcribe(self) -> bool:
        configured_engine = self._configured_engine()
        if configured_engine == "groq_whisper":
            return bool(self._groq_key())
        if configured_engine == "local_faster_whisper":
            return self._local_faster_whisper_ready()
        policy = self._assistant_policy()
        return any(self._backend_available(backend) for backend in policy.stt_route)

    def warm_up_local_backend(self, cancel_event: threading.Event | None = None) -> bool:
        if self._is_cancelled(cancel_event):
            return False
        model_source = self._resolve_local_faster_whisper_source()
        if model_source is None:
            return False
        try:
            load_faster_whisper_model(
                str(model_source),
                self.faster_whisper_download_root,
                device="cpu",
                compute_type="int8",
                cpu_threads=self._cpu_threads(),
            )
            return not self._is_cancelled(cancel_event)
        except Exception:
            return False

    def transcribe_pcm_bytes(self, raw_bytes: bytes, cancel_event: threading.Event | None = None) -> TranscriptionResult:
        if self._is_cancelled(cancel_event):
            return self._cancelled_result()
        if not raw_bytes:
            return TranscriptionResult(status="no_speech", detail="Пустая запись.")

        engine = self._configured_engine()
        groq_key = self._groq_key()

        if engine == "auto":
            return self._transcribe_auto(raw_bytes, groq_key, cancel_event)
        if engine == "groq_whisper" and groq_key:
            return self._transcribe_with_groq(raw_bytes, cancel_event)
        if engine == "local_faster_whisper":
            return self._transcribe_local_chain(raw_bytes, ("local_faster_whisper",), cancel_event)

        return self._transcribe_route(raw_bytes, self._resolved_stt_route(), cancel_event)

    def transcribe_wake_window(
        self,
        raw_bytes: bytes,
        cancel_event: threading.Event | None = None,
    ) -> TranscriptionResult:
        return self._transcribe_with_local_faster_whisper(
            raw_bytes,
            cancel_event=cancel_event,
            initial_prompt=WAKE_PROMPT,
            hotwords=WAKE_HOTWORDS,
            beam_size=WAKE_FASTER_WHISPER_BEAM_SIZE,
            best_of=WAKE_FASTER_WHISPER_BEST_OF,
            vad_parameters=WAKE_FASTER_WHISPER_VAD,
            chunk_length=3,
        )

    def transcribe_wake_command(
        self,
        raw_bytes: bytes,
        cancel_event: threading.Event | None = None,
    ) -> TranscriptionResult:
        return self._transcribe_local_chain(raw_bytes, ("local_faster_whisper",), cancel_event)

    def _transcribe_auto(
        self,
        raw_bytes: bytes,
        groq_key: str,
        cancel_event: threading.Event | None = None,
    ) -> TranscriptionResult:
        if self._is_cancelled(cancel_event):
            return self._cancelled_result(engine="auto")
        route = self._resolved_stt_route()
        if groq_key and "groq_whisper" in route:
            return self._transcribe_route(raw_bytes, route, cancel_event)
        return self._transcribe_route(raw_bytes, tuple(step for step in route if step != "groq_whisper"), cancel_event)

    def _transcribe_route(
        self,
        raw_bytes: bytes,
        route: tuple[str, ...],
        cancel_event: threading.Event | None = None,
    ) -> TranscriptionResult:
        attempted: list[str] = []
        total_latency = 0.0
        last_failure: TranscriptionResult | None = None

        for backend in route:
            if self._is_cancelled(cancel_event):
                return self._with_trace(
                    self._cancelled_result(engine=backend, backend_trace=tuple(attempted)),
                    attempted,
                    total_latency,
                )
            if backend == "groq_whisper":
                if not self._groq_key():
                    continue
                result = self._transcribe_with_groq(raw_bytes, cancel_event)
            elif backend == "local_faster_whisper":
                if not self._local_faster_whisper_ready():
                    continue
                result = self._transcribe_with_local_faster_whisper(raw_bytes, cancel_event)
            else:
                continue

            attempted.append(backend)
            total_latency += result.latency_ms
            if result.ok or result.status == "cancelled":
                return self._with_trace(result, attempted, total_latency)
            last_failure = self._with_trace(result, attempted, total_latency)

        if last_failure is not None:
            return last_failure

        detail = "Нужен ключ для облачного распознавания или локальная модель распознавания."
        if "groq_whisper" not in route:
            detail = "Нужна локальная модель распознавания."
        return TranscriptionResult(
            status="model_missing",
            detail=detail,
            engine=route[0] if route else "auto",
            backend_trace=route,
        )

    def _transcribe_local_chain(
        self,
        raw_bytes: bytes,
        engines: tuple[str, ...],
        cancel_event: threading.Event | None = None,
    ) -> TranscriptionResult:
        attempted: list[str] = []
        total_latency = 0.0
        last_failure: TranscriptionResult | None = None

        for engine in engines:
            if self._is_cancelled(cancel_event):
                return self._with_trace(
                    self._cancelled_result(engine=engine, backend_trace=tuple(attempted)),
                    attempted,
                    total_latency,
                )
            if engine != "local_faster_whisper" or not self._local_faster_whisper_ready():
                continue

            result = self._transcribe_with_local_faster_whisper(raw_bytes, cancel_event)
            attempted.append(engine)
            total_latency += result.latency_ms
            if result.ok or result.status == "cancelled":
                return self._with_trace(result, attempted, total_latency)
            last_failure = self._with_trace(result, attempted, total_latency)

        if last_failure is not None:
            return last_failure

        return TranscriptionResult(
            status="model_missing",
            detail="Локальный backend распознавания не готов.",
            engine=engines[0] if engines else "local",
            backend_trace=engines,
        )

    def _transcribe_with_groq(
        self,
        raw_bytes: bytes,
        cancel_event: threading.Event | None = None,
    ) -> TranscriptionResult:
        if self._is_cancelled(cancel_event):
            return self._cancelled_result(engine="groq_whisper", backend_trace=("groq_whisper",))
        groq_key = self._groq_key()
        if not groq_key:
            return TranscriptionResult(
                status="stt_key_missing",
                detail="Нужен ключ для облачного распознавания.",
                engine="groq_whisper",
                backend_trace=("groq_whisper",),
            )

        temp_path = self._write_temp_wav(raw_bytes)
        client = self._build_http_client()
        started_at = time.perf_counter()
        try:
            if self._is_cancelled(cancel_event):
                return self._cancelled_result(engine="groq_whisper", backend_trace=("groq_whisper",))
            from openai import OpenAI

            api = OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                http_client=client,
            )
            with temp_path.open("rb") as handle:
                response = api.audio.transcriptions.create(
                    file=handle,
                    model="whisper-large-v3-turbo",
                    response_format="json",
                    language="ru",
                    temperature=0.0,
                )
            text = self._normalize_transcript_text(getattr(response, "text", ""))
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
            if not text:
                return TranscriptionResult(
                    status="no_speech",
                    detail="Не удалось распознать речь.",
                    engine="groq_whisper",
                    backend_trace=("groq_whisper",),
                    latency_ms=elapsed_ms,
                )
            return TranscriptionResult(
                status="ok",
                text=text,
                detail="Речь распознана.",
                engine="groq_whisper",
                backend_trace=("groq_whisper",),
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            return TranscriptionResult(
                status="stt_failed",
                detail=f"Не удалось распознать речь через облачный backend: {exc}",
                engine="groq_whisper",
                backend_trace=("groq_whisper",),
                latency_ms=round((time.perf_counter() - started_at) * 1000.0, 1),
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def _transcribe_with_local_faster_whisper(
        self,
        raw_bytes: bytes,
        cancel_event: threading.Event | None = None,
        *,
        initial_prompt: str = COMMAND_PROMPT,
        hotwords: str = COMMAND_HOTWORDS,
        beam_size: int = LOCAL_FASTER_WHISPER_BEAM_SIZE,
        best_of: int = LOCAL_FASTER_WHISPER_BEST_OF,
        vad_parameters: dict[str, int] | None = None,
        chunk_length: int | None = None,
    ) -> TranscriptionResult:
        if self._is_cancelled(cancel_event):
            return self._cancelled_result(engine="local_faster_whisper", backend_trace=("local_faster_whisper",))
        model_source = self._resolve_local_faster_whisper_source()
        if model_source is None:
            return TranscriptionResult(
                status="model_missing",
                detail="Локальная Whisper-модель не найдена.",
                engine="local_faster_whisper",
                backend_trace=("local_faster_whisper",),
            )

        waveform = self._pcm_bytes_to_waveform(raw_bytes)
        if waveform.size == 0:
            return TranscriptionResult(
                status="no_speech",
                detail="Не удалось распознать речь.",
                engine="local_faster_whisper",
                backend_trace=("local_faster_whisper",),
            )

        started_at = time.perf_counter()
        try:
            if self._is_cancelled(cancel_event):
                return self._cancelled_result(engine="local_faster_whisper", backend_trace=("local_faster_whisper",))
            model = load_faster_whisper_model(
                str(model_source),
                self.faster_whisper_download_root,
                device="cpu",
                compute_type="int8",
                cpu_threads=self._cpu_threads(),
            )
            if self._is_cancelled(cancel_event):
                return self._cancelled_result(engine="local_faster_whisper", backend_trace=("local_faster_whisper",))
            kwargs = {
                "language": "ru",
                "beam_size": beam_size,
                "best_of": best_of,
                "temperature": 0.0,
                "vad_filter": True,
                "vad_parameters": vad_parameters or LOCAL_FASTER_WHISPER_VAD,
                "condition_on_previous_text": False,
                "initial_prompt": initial_prompt,
                "hotwords": hotwords,
                "without_timestamps": True,
            }
            if chunk_length is not None:
                kwargs["chunk_length"] = chunk_length
            segments, _info = model.transcribe(waveform, **kwargs)
            segment_texts: list[str] = []
            for segment in segments:
                if self._is_cancelled(cancel_event):
                    return self._cancelled_result(engine="local_faster_whisper", backend_trace=("local_faster_whisper",))
                segment_texts.append(segment.text)
            text = self._normalize_transcript_text(" ".join(segment_texts))
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
            if not text:
                return TranscriptionResult(
                    status="no_speech",
                    detail="Не удалось распознать речь.",
                    engine="local_faster_whisper",
                    backend_trace=("local_faster_whisper",),
                    latency_ms=elapsed_ms,
                )
            return TranscriptionResult(
                status="ok",
                text=text,
                detail="Речь распознана локально.",
                engine="local_faster_whisper",
                backend_trace=("local_faster_whisper",),
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            return TranscriptionResult(
                status="stt_failed",
                detail=f"Не удалось распознать речь локальным Whisper: {exc}",
                engine="local_faster_whisper",
                backend_trace=("local_faster_whisper",),
                latency_ms=round((time.perf_counter() - started_at) * 1000.0, 1),
            )

    def _normalize_transcript_text(self, text: object) -> str:
        normalized = normalize_text(str(text or ""))
        if not normalized:
            return ""
        normalized = normalized.replace("ё", "е").replace("Ё", "Е")
        normalized = re.sub(r"\s+([,.:;!?])", r"\1", normalized)
        normalized = re.sub(r"([,.:;!?]){2,}", r"\1", normalized)
        return normalize_text(normalized)

    def _pcm_bytes_to_waveform(self, raw_bytes: bytes) -> np.ndarray:
        if not raw_bytes:
            return np.asarray([], dtype=np.float32)
        samples = np.frombuffer(raw_bytes, dtype=np.int16)
        if samples.size == 0:
            return np.asarray([], dtype=np.float32)
        return samples.astype(np.float32) / 32768.0

    def _faster_whisper_available(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _local_faster_whisper_ready(self) -> bool:
        return self._faster_whisper_available() and self._resolve_local_faster_whisper_source() is not None

    def _preferred_local_engine(self) -> str:
        if self._local_faster_whisper_ready():
            return "local_faster_whisper"
        return "local_faster_whisper"

    def _faster_whisper_model_ref(self) -> str:
        env_override = str(os.environ.get("JARVIS_UNITY_FASTER_WHISPER_MODEL", "") or "").strip()
        if env_override:
            return env_override
        configured = str(self.settings.get("stt_local_model", DEFAULT_FASTER_WHISPER_MODEL)).strip()
        return configured or DEFAULT_FASTER_WHISPER_MODEL

    def _resolve_local_faster_whisper_source(self) -> str | Path | None:
        if not self._faster_whisper_available():
            return None
        if self._local_model_override is not None:
            if self._local_model_override.exists():
                return self._local_model_override
            return None

        model_ref = self._faster_whisper_model_ref()
        local_path = resolve_local_faster_whisper_model(model_ref, self.faster_whisper_download_root)
        if local_path is not None:
            return local_path
        existing_path = find_existing_faster_whisper_model(model_ref, self.faster_whisper_download_root)
        if existing_path is not None:
            return existing_path
        if can_auto_download_faster_whisper_model(model_ref):
            return model_ref
        return None

    def _is_cancelled(self, cancel_event: threading.Event | None) -> bool:
        return bool(cancel_event is not None and cancel_event.is_set())

    def _cancelled_result(
        self,
        *,
        engine: str = "",
        backend_trace: tuple[str, ...] = (),
    ) -> TranscriptionResult:
        return TranscriptionResult(
            status="cancelled",
            detail="Запись остановлена.",
            engine=engine,
            backend_trace=backend_trace,
        )

    def _auto_local_chain(self) -> tuple[str, ...]:
        route = tuple(step for step in self._resolved_stt_route() if step == "local_faster_whisper")
        return route or ("local_faster_whisper",)

    def _find_faster_whisper_download_root(self) -> Path:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            return Path(data_dir) / "models" / FASTER_WHISPER_CACHE_DIR
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            bundled = Path(frozen_root) / "assets" / "models" / FASTER_WHISPER_CACHE_DIR
            if resolve_local_faster_whisper_model(self._faster_whisper_model_ref(), bundled) is not None:
                return bundled
        local_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
        return local_root / "JarvisAi_Unity" / "models" / FASTER_WHISPER_CACHE_DIR

    def _cpu_threads(self) -> int:
        return max(1, min(8, os.cpu_count() or 1))

    def _groq_key(self) -> str:
        registration = self.settings.get_registration()
        configured = str(registration.get("groq_api_key", "")).strip()
        if configured:
            return configured
        return str(os.environ.get("GROQ_API_KEY", "") or "").strip()

    def _assistant_policy(self):
        readiness = AssistantReadiness(
            local_llama_ready=False,
            local_faster_whisper_ready=self._local_faster_whisper_ready(),
        )
        return resolve_assistant_policy(self.settings, readiness=readiness)

    def _resolved_stt_route(self) -> tuple[str, ...]:
        override = str(self.settings.get("stt_backend_override", "auto")).strip().casefold()
        if override in {"groq_whisper", "local_faster_whisper"}:
            return (override,)
        return self._assistant_policy().stt_route

    def _backend_available(self, backend: str) -> bool:
        if backend == "groq_whisper":
            return bool(self._groq_key())
        if backend == "local_faster_whisper":
            return self._local_faster_whisper_ready()
        return False

    def _build_http_client(self):
        import httpx

        network = self.settings.get("network", {}) or {}
        timeout = float(network.get("timeout_seconds", 20.0))
        proxy_mode = str(network.get("proxy_mode", "system") or "system").casefold()
        proxy_url = str(network.get("proxy_url", "") or "").strip()
        signature = (proxy_mode, proxy_url, timeout)

        if self._http_client is not None and self._http_client_signature == signature:
            return self._http_client

        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass

        client_kwargs: dict[str, object] = {"timeout": timeout}
        if proxy_mode == "manual" and proxy_url:
            client_kwargs["proxy"] = proxy_url
        self._http_client = httpx.Client(**client_kwargs)
        self._http_client_signature = signature
        return self._http_client

    def _merge_backend_trace(
        self,
        result: TranscriptionResult,
        prior: TranscriptionResult,
        prior_engine: str,
    ) -> TranscriptionResult:
        trace: list[str] = []
        if prior.backend_trace:
            trace.extend(prior.backend_trace)
        elif prior_engine:
            trace.append(prior_engine)
        if result.backend_trace:
            trace.extend(step for step in result.backend_trace if step not in trace)
        elif result.engine and result.engine not in trace:
            trace.append(result.engine)
        return TranscriptionResult(
            status=result.status,
            text=result.text,
            detail=result.detail,
            engine=result.engine,
            backend_trace=tuple(trace),
            latency_ms=round(prior.latency_ms + result.latency_ms, 1),
        )

    def _with_trace(
        self,
        result: TranscriptionResult,
        attempted: list[str],
        total_latency: float,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            status=result.status,
            text=result.text,
            detail=result.detail,
            engine=result.engine,
            backend_trace=tuple(dict.fromkeys((*attempted, *result.backend_trace))),
            latency_ms=round(total_latency, 1),
        )

    def _write_temp_wav(self, raw_bytes: bytes) -> Path:
        fd, raw_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_unity_")
        os.close(fd)
        path = Path(raw_path)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16_000)
            wav_file.writeframes(raw_bytes)
        return path

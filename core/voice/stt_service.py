from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx
from openai import OpenAI
from vosk import KaldiRecognizer

from core.routing.text_rules import normalize_text
from core.voice.faster_whisper_runtime import load_faster_whisper_model, resolve_local_faster_whisper_model
from core.voice.voice_models import TranscriptionResult
from core.voice.vosk_runtime import load_vosk_model


MODEL_DIR_NAME = "vosk-model-small-ru-0.22"
FASTER_WHISPER_CACHE_DIR = "faster-whisper"
DEFAULT_FASTER_WHISPER_MODEL = os.environ.get("JARVIS_UNITY_FASTER_WHISPER_MODEL", "small").strip() or "small"
COMMAND_PROMPT = (
    "Русские голосовые команды для Windows. "
    "Джарвис, открой YouTube, Steam, Discord, браузер, музыку, параметры, проводник, "
    "панель управления, сделай громче, сделай тише, заблокируй экран."
)


class STTService:
    def __init__(self, settings_service, local_model_path: Path | None = None) -> None:
        self.settings = settings_service
        self.local_model_path = local_model_path or self._find_local_model_path()
        self.faster_whisper_download_root = self._find_faster_whisper_download_root()
        self._http_client: httpx.Client | None = None
        self._http_client_signature: tuple[str, str, float] | None = None

    def engine(self) -> str:
        value = str(self.settings.get("stt_engine", "auto")).strip().casefold()
        if value in {"groq", "groq_whisper"}:
            return "groq_whisper"
        if value in {"vosk", "local_vosk"}:
            return "local_vosk"
        if value in {"local", "whisper", "faster_whisper", "local_faster_whisper"}:
            return "local_faster_whisper"
        return "auto"

    def status_text(self) -> str:
        engine = self.engine()
        groq_key = self._groq_key()

        if engine == "groq_whisper":
            return "распознавание через Groq готово" if groq_key else "Нужен ключ Groq"
        if engine == "local_vosk":
            return "локальная модель Vosk готова" if self._local_vosk_available() else "Локальная модель Vosk не найдена"
        if engine == "local_faster_whisper":
            if self._local_faster_whisper_ready():
                return "локальный Whisper готов"
            if self._local_vosk_available():
                return "Whisper недоступен, резервный Vosk готов"
            return "Нужен faster-whisper или локальная модель Vosk"

        voice_mode = self._voice_mode()
        if voice_mode == "private":
            if self._local_faster_whisper_ready():
                return "локальное распознавание готово"
            if self._local_vosk_available():
                return "локальное распознавание работает через Vosk"
            return "Нужен локальный backend распознавания"

        if groq_key and self._local_faster_whisper_ready():
            return "распознавание готово"
        if groq_key:
            return "распознавание через Groq готово"
        if self._local_faster_whisper_ready():
            return "локальное распознавание готово"
        if self._local_vosk_available():
            return "локальное распознавание работает через Vosk"
        return "Нужен ключ Groq или локальный backend распознавания"

    def can_transcribe(self) -> bool:
        engine = self.engine()
        if engine == "groq_whisper":
            return bool(self._groq_key())
        if engine == "local_vosk":
            return self._local_vosk_available()
        if engine == "local_faster_whisper":
            return self._local_faster_whisper_ready() or self._local_vosk_available()
        if self._voice_mode() == "private":
            return self._local_faster_whisper_ready() or self._local_vosk_available()
        return bool(self._groq_key()) or self._local_faster_whisper_ready() or self._local_vosk_available()

    def warm_up_local_backend(self) -> bool:
        preferred_local = self._preferred_local_engine()
        if preferred_local == "local_faster_whisper":
            model_source = self._resolve_local_faster_whisper_source()
            if model_source is None:
                if self._local_vosk_available():
                    load_vosk_model(self.local_model_path)
                    return True
                return False
            try:
                load_faster_whisper_model(
                    str(model_source),
                    self.faster_whisper_download_root,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self._cpu_threads(),
                )
                return True
            except Exception:
                if self._local_vosk_available():
                    load_vosk_model(self.local_model_path)
                    return True
                return False

        if self._local_vosk_available():
            load_vosk_model(self.local_model_path)
            return True
        return False

    def transcribe_pcm_bytes(self, raw_bytes: bytes) -> TranscriptionResult:
        if not raw_bytes:
            return TranscriptionResult(status="no_speech", detail="Пустая запись.")

        engine = self.engine()
        groq_key = self._groq_key()

        if engine == "auto":
            return self._transcribe_auto(raw_bytes, groq_key)
        if engine == "groq_whisper" and groq_key:
            return self._transcribe_with_groq(raw_bytes)
        if engine == "local_vosk":
            return self._transcribe_with_local_vosk(raw_bytes)
        if engine == "local_faster_whisper":
            return self._transcribe_local_chain(raw_bytes, ("local_faster_whisper", "local_vosk"))

        if groq_key:
            return self._transcribe_with_groq(raw_bytes)
        if self._local_faster_whisper_ready():
            return self._transcribe_local_chain(raw_bytes, ("local_faster_whisper", "local_vosk"))
        if self._local_vosk_available():
            return self._transcribe_with_local_vosk(raw_bytes)

        return TranscriptionResult(
            status="model_missing",
            detail="Нужен ключ Groq или локальный backend распознавания.",
            engine="auto",
        )

    def _transcribe_auto(self, raw_bytes: bytes, groq_key: str) -> TranscriptionResult:
        voice_mode = self._voice_mode()
        if voice_mode == "private":
            return self._transcribe_local_chain(raw_bytes, ("local_faster_whisper", "local_vosk"))

        if voice_mode == "balance":
            if self._local_faster_whisper_ready() or self._local_vosk_available():
                local_result = self._transcribe_local_chain(raw_bytes, ("local_faster_whisper", "local_vosk"))
                if local_result.ok:
                    return local_result
                if groq_key:
                    fallback = self._transcribe_with_groq(raw_bytes)
                    return self._merge_backend_trace(fallback, local_result, local_result.engine or "local_faster_whisper")
                return local_result
            if groq_key:
                return self._transcribe_with_groq(raw_bytes)

        if groq_key:
            result = self._transcribe_with_groq(raw_bytes)
            if result.ok:
                return result
            fallback = self._transcribe_local_chain(raw_bytes, ("local_faster_whisper", "local_vosk"))
            return self._merge_backend_trace(fallback, result, "groq_whisper")

        return self._transcribe_local_chain(raw_bytes, ("local_faster_whisper", "local_vosk"))

    def _transcribe_local_chain(self, raw_bytes: bytes, engines: tuple[str, ...]) -> TranscriptionResult:
        attempted: list[str] = []
        total_latency = 0.0
        last_failure: TranscriptionResult | None = None

        for engine in engines:
            if engine == "local_faster_whisper":
                if not self._local_faster_whisper_ready():
                    continue
                result = self._transcribe_with_local_faster_whisper(raw_bytes)
            elif engine == "local_vosk":
                if not self._local_vosk_available():
                    continue
                result = self._transcribe_with_local_vosk(raw_bytes)
            else:
                continue

            attempted.append(engine)
            total_latency += result.latency_ms
            if result.ok:
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

    def _transcribe_with_groq(self, raw_bytes: bytes) -> TranscriptionResult:
        groq_key = self._groq_key()
        if not groq_key:
            return TranscriptionResult(
                status="stt_key_missing",
                detail="Нужен ключ Groq.",
                engine="groq_whisper",
                backend_trace=("groq_whisper",),
            )

        temp_path = self._write_temp_wav(raw_bytes)
        client = self._build_http_client()
        started_at = time.perf_counter()
        try:
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
                detail=f"Не удалось распознать речь через Groq: {exc}",
                engine="groq_whisper",
                backend_trace=("groq_whisper",),
                latency_ms=round((time.perf_counter() - started_at) * 1000.0, 1),
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def _transcribe_with_local_faster_whisper(self, raw_bytes: bytes) -> TranscriptionResult:
        model_source = self._resolve_local_faster_whisper_source()
        if model_source is None:
            return TranscriptionResult(
                status="model_missing",
                detail="Локальная Whisper-модель не найдена.",
                engine="local_faster_whisper",
                backend_trace=("local_faster_whisper",),
            )

        temp_path = self._write_temp_wav(raw_bytes)
        started_at = time.perf_counter()
        try:
            model = load_faster_whisper_model(
                str(model_source),
                self.faster_whisper_download_root,
                device="cpu",
                compute_type="int8",
                cpu_threads=self._cpu_threads(),
            )
            segments, _info = model.transcribe(
                str(temp_path),
                language="ru",
                beam_size=1,
                best_of=1,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 180},
                condition_on_previous_text=False,
                initial_prompt=COMMAND_PROMPT,
            )
            text = self._normalize_transcript_text(" ".join(segment.text for segment in list(segments)))
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
        finally:
            temp_path.unlink(missing_ok=True)

    def _transcribe_with_local_vosk(self, raw_bytes: bytes) -> TranscriptionResult:
        if not self._local_vosk_available():
            return TranscriptionResult(
                status="model_missing",
                detail="Локальная модель Vosk не найдена.",
                engine="local_vosk",
                backend_trace=("local_vosk",),
            )

        started_at = time.perf_counter()
        try:
            model = load_vosk_model(self.local_model_path)
            recognizer = KaldiRecognizer(model, 16_000)
            recognizer.AcceptWaveform(raw_bytes)
            payload = recognizer.FinalResult()
            data = json.loads(payload)
            text = self._normalize_transcript_text(data.get("text", ""))
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
            if not text:
                return TranscriptionResult(
                    status="no_speech",
                    detail="Не удалось распознать речь.",
                    engine="local_vosk",
                    backend_trace=("local_vosk",),
                    latency_ms=elapsed_ms,
                )
            return TranscriptionResult(
                status="ok",
                text=text,
                detail="Речь распознана локально.",
                engine="local_vosk",
                backend_trace=("local_vosk",),
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            return TranscriptionResult(
                status="stt_failed",
                detail=f"Не удалось распознать речь локально: {exc}",
                engine="local_vosk",
                backend_trace=("local_vosk",),
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

    def _faster_whisper_available(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _local_vosk_available(self) -> bool:
        return self.local_model_path.exists()

    def _local_faster_whisper_ready(self) -> bool:
        return self._faster_whisper_available() and self._resolve_local_faster_whisper_source() is not None

    def _preferred_local_engine(self) -> str:
        if self._local_faster_whisper_ready():
            return "local_faster_whisper"
        if self._local_vosk_available():
            return "local_vosk"
        return "local_faster_whisper"

    def _faster_whisper_model_ref(self) -> str:
        configured = str(self.settings.get("stt_local_model", DEFAULT_FASTER_WHISPER_MODEL)).strip()
        return configured or DEFAULT_FASTER_WHISPER_MODEL

    def _resolve_local_faster_whisper_source(self) -> Path | None:
        if not self._faster_whisper_available():
            return None
        return resolve_local_faster_whisper_model(
            self._faster_whisper_model_ref(),
            self.faster_whisper_download_root,
        )

    def _find_faster_whisper_download_root(self) -> Path:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            return Path(data_dir) / "models" / FASTER_WHISPER_CACHE_DIR
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            bundled = Path(frozen_root) / "assets" / "models" / FASTER_WHISPER_CACHE_DIR
            if bundled.exists():
                return bundled
        local_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
        return local_root / "JarvisAi_Unity" / "models" / FASTER_WHISPER_CACHE_DIR

    def _cpu_threads(self) -> int:
        return max(1, min(8, os.cpu_count() or 1))

    def _groq_key(self) -> str:
        registration = self.settings.get_registration()
        return str(registration.get("groq_api_key", "")).strip()

    def _voice_mode(self) -> str:
        value = str(self.settings.get("voice_mode", "balance")).strip().casefold()
        return value if value in {"private", "balance", "quality"} else "balance"

    def _build_http_client(self) -> httpx.Client:
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

    def _find_local_model_path(self) -> Path:
        candidates = []
        env_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if env_dir:
            candidates.append(Path(env_dir) / "models" / MODEL_DIR_NAME)
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            candidates.append(Path(frozen_root) / "assets" / "models" / MODEL_DIR_NAME)
        candidates.append(Path(__file__).resolve().parents[2] / "assets" / "models" / MODEL_DIR_NAME)
        local_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
        candidates.append(local_root / "JarvisAi_Unity" / "models" / MODEL_DIR_NAME)

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[-1]

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx
from openai import OpenAI
from vosk import KaldiRecognizer

from core.voice.voice_models import TranscriptionResult
from core.voice.vosk_runtime import load_vosk_model


MODEL_DIR_NAME = "vosk-model-small-ru-0.22"


class STTService:
    def __init__(self, settings_service, local_model_path: Path | None = None) -> None:
        self.settings = settings_service
        self.local_model_path = local_model_path or self._find_local_model_path()
        self._http_client: httpx.Client | None = None
        self._http_client_signature: tuple[str, str, float] | None = None

    def engine(self) -> str:
        value = str(self.settings.get("stt_engine", "auto")).strip().casefold()
        if value in {"groq", "groq_whisper"}:
            return "groq_whisper"
        if value in {"local", "local_vosk"}:
            return "local_vosk"
        return "auto"

    def status_text(self) -> str:
        engine = self.engine()
        groq_key = self._groq_key()
        has_local = self.local_model_path.exists()

        if engine == "groq_whisper":
            return "распознавание готово" if groq_key else "Нужен ключ Groq"
        if engine == "local_vosk":
            return "локальная модель распознавания готова" if has_local else "Локальная модель не загружена"

        voice_mode = self._voice_mode()
        if voice_mode == "private":
            return "локальное распознавание готово" if has_local else "Локальная модель не загружена"
        if groq_key or has_local:
            return "распознавание готово"
        if has_local:
            return "локальная модель распознавания готова"
        return "Нужен ключ Groq"

    def can_transcribe(self) -> bool:
        engine = self.engine()
        if engine == "groq_whisper":
            return bool(self._groq_key())
        if engine == "local_vosk":
            return self.local_model_path.exists()
        if self._voice_mode() == "private":
            return self.local_model_path.exists()
        return bool(self._groq_key()) or self.local_model_path.exists()

    def warm_up_local_backend(self) -> bool:
        if not self.local_model_path.exists():
            return False
        load_vosk_model(self.local_model_path)
        return True

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
            return self._transcribe_with_local_model(raw_bytes)

        if groq_key:
            return self._transcribe_with_groq(raw_bytes)
        if self.local_model_path.exists():
            return self._transcribe_with_local_model(raw_bytes)

        return TranscriptionResult(
            status="model_missing",
            detail="Нужен ключ Groq или локальная модель распознавания.",
            engine="auto",
        )

    def _transcribe_auto(self, raw_bytes: bytes, groq_key: str) -> TranscriptionResult:
        voice_mode = self._voice_mode()
        has_local = self.local_model_path.exists()

        if voice_mode == "private":
            if has_local:
                return self._transcribe_with_local_model(raw_bytes)
            return TranscriptionResult(
                status="model_missing",
                detail="Для приватного режима нужна локальная модель распознавания.",
                engine="local_vosk",
                backend_trace=("local_vosk",),
            )

        if voice_mode == "balance" and has_local:
            local_result = self._transcribe_with_local_model(raw_bytes)
            if local_result.ok:
                return local_result
            if groq_key:
                fallback = self._transcribe_with_groq(raw_bytes)
                return self._merge_backend_trace(fallback, local_result, "local_vosk")
            return local_result

        if groq_key:
            result = self._transcribe_with_groq(raw_bytes)
            if result.ok or not has_local:
                return result
            fallback = self._transcribe_with_local_model(raw_bytes)
            return self._merge_backend_trace(fallback, result, "groq_whisper")

        if has_local:
            return self._transcribe_with_local_model(raw_bytes)

        return TranscriptionResult(
            status="model_missing",
            detail="Нужен ключ Groq или локальная модель распознавания.",
            engine="auto",
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
            text = str(getattr(response, "text", "") or "").strip()
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

    def _transcribe_with_local_model(self, raw_bytes: bytes) -> TranscriptionResult:
        if not self.local_model_path.exists():
            return TranscriptionResult(
                status="model_missing",
                detail="Локальная модель распознавания не найдена.",
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
            text = str(data.get("text", "") or "").strip()
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

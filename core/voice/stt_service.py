from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path

import httpx
from openai import OpenAI
from vosk import KaldiRecognizer, Model

from core.voice.voice_models import TranscriptionResult


MODEL_DIR_NAME = "vosk-model-small-ru-0.22"


class STTService:
    def __init__(self, settings_service, local_model_path: Path | None = None) -> None:
        self.settings = settings_service
        self.local_model_path = local_model_path or self._find_local_model_path()

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

    def transcribe_pcm_bytes(self, raw_bytes: bytes) -> TranscriptionResult:
        if not raw_bytes:
            return TranscriptionResult(status="no_speech", detail="Пустая запись.")

        engine = self.engine()
        groq_key = self._groq_key()

        if engine == "auto":
            return self._transcribe_auto(raw_bytes, groq_key)

        if engine == "groq_whisper" and groq_key:
            result = self._transcribe_with_groq(raw_bytes)
            return result

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
            )

        if voice_mode == "balance" and has_local:
            local_result = self._transcribe_with_local_model(raw_bytes)
            if local_result.ok:
                return local_result
            if groq_key:
                return self._transcribe_with_groq(raw_bytes)
            return local_result

        if groq_key:
            result = self._transcribe_with_groq(raw_bytes)
            if result.ok or not has_local:
                return result
            return self._transcribe_with_local_model(raw_bytes)

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
            )

        temp_path = self._write_temp_wav(raw_bytes)
        client = self._build_http_client()
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
            if not text:
                return TranscriptionResult(
                    status="no_speech",
                    detail="Не удалось распознать речь.",
                    engine="groq_whisper",
                )
            return TranscriptionResult(status="ok", text=text, detail="Речь распознана.", engine="groq_whisper")
        except Exception as exc:
            return TranscriptionResult(
                status="stt_failed",
                detail=f"Не удалось распознать речь через Groq: {exc}",
                engine="groq_whisper",
            )
        finally:
            temp_path.unlink(missing_ok=True)
            try:
                client.close()
            except Exception:
                pass

    def _transcribe_with_local_model(self, raw_bytes: bytes) -> TranscriptionResult:
        if not self.local_model_path.exists():
            return TranscriptionResult(
                status="model_missing",
                detail="Локальная модель распознавания не найдена.",
                engine="local_vosk",
            )

        try:
            model = Model(str(self.local_model_path))
            recognizer = KaldiRecognizer(model, 16_000)
            recognizer.AcceptWaveform(raw_bytes)
            payload = recognizer.FinalResult()
            data = json.loads(payload)
            text = str(data.get("text", "") or "").strip()
            if not text:
                return TranscriptionResult(
                    status="no_speech",
                    detail="Не удалось распознать речь.",
                    engine="local_vosk",
                )
            return TranscriptionResult(
                status="ok",
                text=text,
                detail="Речь распознана локально.",
                engine="local_vosk",
            )
        except Exception as exc:
            return TranscriptionResult(
                status="stt_failed",
                detail=f"Не удалось распознать речь локально: {exc}",
                engine="local_vosk",
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

        client_kwargs: dict[str, object] = {"timeout": timeout}
        if proxy_mode == "manual" and proxy_url:
            client_kwargs["proxy"] = proxy_url
        return httpx.Client(**client_kwargs)

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

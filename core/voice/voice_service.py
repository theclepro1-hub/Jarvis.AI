from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from openai import OpenAI


class VoiceService:
    SAMPLE_RATE = 16_000
    CHANNELS = 1
    BLOCK_FRAMES = 1600

    def __init__(self, settings_service) -> None:
        self.settings = settings_service
        self.microphones = self._detect_microphones()
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._recording = False
        self._wake_status = "локальный wake runtime готовится"
        self._wake_ready = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def set_wake_runtime_status(self, text: str, ready: bool) -> None:
        self._wake_status = text
        self._wake_ready = ready

    def summary(self) -> str:
        mode = self.settings.get("voice_mode", "balance")
        style = self.settings.get("command_style", "one_shot")
        wake = self._wake_status
        stt = "Groq Whisper после записи" if self._has_groq_key() else "ожидает Groq API Key"
        style_label = "одной фразой" if style == "one_shot" else "в два шага"
        return f"Wake word: {wake}. STT: {stt}. Режим: {mode}. Сценарий: {style_label}."

    def runtime_status(self) -> dict[str, str]:
        return {
            "wakeWord": self._wake_status,
            "command": "локально после активации + Groq STT" if self._has_groq_key() else "нужен Groq API Key",
            "ai": "Groq или локальный fallback",
            "model": "готова" if self._has_groq_key() else "не подключена",
        }

    def test_wake_word(self) -> str:
        if self._wake_ready:
            return "Always-on local wake runtime активен и ждёт «Джарвис»."
        return "Wake runtime ещё готовится. Если модель не скачана, первое включение поднимет её локально."

    def start_manual_capture(self) -> str:
        if self._recording:
            return "Запись уже идёт."

        self._chunks = []
        try:
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="int16",
                device=self._resolve_input_device(),
                callback=self._on_audio,
            )
            self._stream.start()
            self._recording = True
            return "Слушаю. Нажмите микрофон ещё раз, чтобы отправить запись."
        except Exception:
            self._stream = None
            self._recording = False
            return "Не удалось открыть микрофон. Проверьте выбранное устройство."

    def stop_manual_capture(self) -> str:
        if not self._recording:
            return ""

        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._recording = False

        audio = self._collect_audio()
        if audio is None:
            return ""
        return self._transcribe_array(audio)

    def capture_after_wake(self, pre_roll: bytes) -> str:
        chunks: list[bytes] = [pre_roll] if pre_roll else []
        speech_started = bool(pre_roll and self._chunk_energy(pre_roll) > 160)
        silence_seconds = 0.0

        try:
            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="int16",
                device=self._resolve_input_device(),
                blocksize=self.BLOCK_FRAMES,
            ) as stream:
                max_iterations = int(4.5 * self.SAMPLE_RATE / self.BLOCK_FRAMES)
                for _ in range(max_iterations):
                    data, _overflowed = stream.read(self.BLOCK_FRAMES)
                    raw = bytes(data)
                    chunks.append(raw)

                    energy = self._chunk_energy(raw)
                    if energy > 160:
                        speech_started = True
                        silence_seconds = 0.0
                    elif speech_started:
                        silence_seconds += self.BLOCK_FRAMES / self.SAMPLE_RATE
                        if silence_seconds >= 0.9:
                            break
        except Exception:
            return ""

        combined = b"".join(chunks)
        if not combined:
            return ""

        text = self._transcribe_pcm_bytes(combined)
        return self._strip_wake_word(text)

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        if status:
            return
        self._chunks.append(indata.copy())

    def _collect_audio(self) -> np.ndarray | None:
        if not self._chunks:
            return None
        combined = np.concatenate(self._chunks, axis=0).flatten()
        if combined.size == 0:
            return None
        return combined

    def _transcribe_array(self, audio: np.ndarray) -> str:
        return self._transcribe_pcm_bytes(audio.astype(np.int16).tobytes())

    def _transcribe_pcm_bytes(self, raw_bytes: bytes) -> str:
        if not self._has_groq_key():
            return ""

        temp_path = self._write_temp_wav(raw_bytes)
        try:
            client = OpenAI(
                api_key=self.settings.get_registration()["groq_api_key"],
                base_url="https://api.groq.com/openai/v1",
            )
            with temp_path.open("rb") as handle:
                response = client.audio.transcriptions.create(
                    file=handle,
                    model="whisper-large-v3-turbo",
                    response_format="json",
                    language="ru",
                    temperature=0.0,
                )
            text = getattr(response, "text", "") or ""
            return text.strip()
        except Exception:
            return ""
        finally:
            temp_path.unlink(missing_ok=True)

    def _write_temp_wav(self, raw_bytes: bytes) -> Path:
        fd, raw_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_unity_")
        Path(raw_path).unlink(missing_ok=True)
        path = Path(raw_path)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(self.CHANNELS)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(raw_bytes)
        return path

    def _strip_wake_word(self, text: str) -> str:
        clean = text.strip()
        for wake in ("джарвис", "jarvis"):
            if clean.lower().startswith(wake):
                clean = clean[len(wake) :].lstrip(" ,.:;!-")
                break
        return clean

    def _chunk_energy(self, raw_bytes: bytes) -> float:
        if not raw_bytes:
            return 0.0
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples * samples)))

    def _has_groq_key(self) -> bool:
        return bool(self.settings.get_registration().get("groq_api_key", "").strip())

    def _detect_microphones(self) -> list[str]:
        try:
            devices = sd.query_devices()
            names = [device["name"] for device in devices if device.get("max_input_channels", 0) > 0]
            if "Системный по умолчанию" not in names:
                names.insert(0, "Системный по умолчанию")
            return names or ["Системный по умолчанию"]
        except Exception:
            return ["Системный по умолчанию"]

    def _resolve_input_device(self) -> int | None:
        selected = self.settings.get("microphone_name", "Системный по умолчанию")
        if not selected or selected == "Системный по умолчанию":
            return None

        try:
            devices = sd.query_devices()
            for index, device in enumerate(devices):
                if device.get("max_input_channels", 0) > 0 and device.get("name") == selected:
                    return index
        except Exception:
            return None
        return None

from __future__ import annotations

import re
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
from openai import OpenAI


class VoiceService:
    SAMPLE_RATE = 16_000
    CHANNELS = 1
    BLOCK_FRAMES = 1600
    MANUAL_MAX_SECONDS = 8.0
    SILENCE_SECONDS = 0.9
    ENERGY_THRESHOLD = 160.0
    DEFAULT_MICROPHONE_LABEL = "Системный по умолчанию"
    SYSTEM_ENDPOINT_MARKERS = (
        "@system32",
        "\\drivers\\",
        "input (@",
        "driver dump",
        "system capture",
        "переназначение звуковых устр",
    )

    def __init__(self, settings_service) -> None:
        self.settings = settings_service
        self._manual_stop_event = threading.Event()
        self._manual_thread: threading.Thread | None = None
        self._recording = False
        self._wake_phase = "idle"
        self._wake_detail = "Локальный wake runtime не запущен"
        self._wake_ready = False
        self._microphone_lookup: dict[str, str] = {}
        self.microphones = self._detect_microphones()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def set_wake_runtime_status(self, phase: str, ready: bool = False, detail: str | None = None) -> None:
        self._wake_phase = phase
        self._wake_ready = ready
        if detail is not None:
            self._wake_detail = detail

    def wake_status_text(self) -> str:
        labels = {
            "preparing": "Готовлю локальный контур",
            "waiting": "Жду «Джарвис»",
            "listening": "Слушаю",
            "transcribing": self._wake_detail or "Распознаю команду",
            "error": self._wake_detail or "Ошибка слова активации",
            "no_key": "Нужен ключ Groq",
            "idle": self._wake_detail or "Локальный wake runtime не запущен",
        }
        return labels.get(self._wake_phase, self._wake_detail or "Готов")

    def command_status_text(self) -> str:
        if self._has_groq_key():
            return "Локально после активации + распознавание Groq"
        return "Нужен ключ Groq"

    def model_status_text(self) -> str:
        return "распознавание Groq готово" if self._has_groq_key() else "не подключена"

    def summary(self) -> str:
        mode = self.settings.get("voice_mode", "balance")
        mode_label = {
            "private": "приватный",
            "balance": "баланс",
            "quality": "качество",
        }.get(mode, mode)
        style = self.settings.get("command_style", "one_shot")
        style_label = "одной фразой" if style == "one_shot" else "в два шага"
        return f"Слово активации: {self.wake_status_text()}. Распознавание: {self.command_status_text()}. Режим: {mode_label}. Сценарий: {style_label}."

    def runtime_status(self) -> dict[str, str]:
        return {
            "wakeWord": self.wake_status_text(),
            "command": self.command_status_text(),
            "ai": "Groq или локальный резерв",
            "model": self.model_status_text(),
        }

    def test_wake_word(self) -> str:
        if self._wake_phase == "listening" and self._wake_ready:
            return "Локальный контур активации ждёт «Джарвис»."
        if self._wake_phase == "preparing":
            return "Контур активации ещё готовится. Модель загружается локально при первом запуске."
        if self._wake_phase == "error":
            return self._wake_detail or "Ошибка слова активации."
        return "Контур активации готов."

    def start_manual_capture(
        self,
        on_text: Callable[[str], None] | None = None,
        on_note: Callable[[str], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> str:
        if self._recording:
            return "Запись уже идёт."

        self._manual_stop_event.clear()
        self._recording = True
        self._manual_thread = threading.Thread(
            target=self._manual_capture_worker,
            args=(on_text, on_note, on_finish),
            daemon=True,
        )
        self._manual_thread.start()
        return "Слушаю. Говорите один раз, запись остановится сама."

    def stop_manual_capture(self) -> str:
        if not self._recording and (self._manual_thread is None or not self._manual_thread.is_alive()):
            return ""

        self._manual_stop_event.set()
        return "Останавливаю запись..."

    def capture_after_wake(self, pre_roll: bytes) -> str:
        combined = self._capture_until_silence(
            pre_roll=pre_roll,
            max_seconds=4.5,
            silence_seconds=self.SILENCE_SECONDS,
            energy_threshold=self.ENERGY_THRESHOLD,
        )
        if not combined:
            return ""

        text = self._transcribe_pcm_bytes(combined)
        return self._strip_wake_word(text)

    def _manual_capture_worker(
        self,
        on_text: Callable[[str], None] | None,
        on_note: Callable[[str], None] | None,
        on_finish: Callable[[], None] | None,
    ) -> None:
        try:
            combined = self._capture_until_silence(
                max_seconds=self.MANUAL_MAX_SECONDS,
                silence_seconds=self.SILENCE_SECONDS,
                energy_threshold=self.ENERGY_THRESHOLD,
            )
            if not combined:
                if on_note is not None:
                    on_note("Не удалось получить текст из записи. Проверьте микрофон или Groq API Key.")
                return

            text = self._transcribe_pcm_bytes(combined)
            if text:
                if on_text is not None:
                    on_text(text)
            elif on_note is not None:
                on_note("Не удалось получить текст из записи. Проверьте микрофон или Groq API Key.")
        except Exception:
            if on_note is not None:
                on_note("Не удалось открыть микрофон. Проверьте выбранное устройство.")
        finally:
            self._recording = False
            self._manual_thread = None
            self._manual_stop_event.clear()
            if on_finish is not None:
                on_finish()

    def _capture_until_silence(
        self,
        pre_roll: bytes = b"",
        max_seconds: float = 4.5,
        silence_seconds: float = 0.9,
        energy_threshold: float = 160.0,
    ) -> bytes:
        chunks: list[bytes] = [pre_roll] if pre_roll else []
        speech_started = bool(pre_roll and self._chunk_energy(pre_roll) > energy_threshold)
        silence_for = 0.0
        max_iterations = int(max_seconds * self.SAMPLE_RATE / self.BLOCK_FRAMES)

        try:
            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="int16",
                device=self._resolve_input_device(),
                blocksize=self.BLOCK_FRAMES,
            ) as stream:
                for _ in range(max_iterations):
                    if self._manual_stop_event.is_set():
                        break

                    data, _overflowed = stream.read(self.BLOCK_FRAMES)
                    raw = bytes(data)
                    chunks.append(raw)

                    energy = self._chunk_energy(raw)
                    if energy > energy_threshold:
                        speech_started = True
                        silence_for = 0.0
                    elif speech_started:
                        silence_for += self.BLOCK_FRAMES / self.SAMPLE_RATE
                        if silence_for >= silence_seconds:
                            break
        except Exception:
            return b""

        if not speech_started:
            return b""
        return b"".join(chunks)

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
        _fd, raw_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_unity_")
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
        lowered = clean.casefold()
        for wake in ("джарвис", "jarvis"):
            if lowered.startswith(wake):
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
        except Exception:
            devices = []

        labels: list[str] = [self.DEFAULT_MICROPHONE_LABEL]
        lookup: dict[str, str] = {
            self.DEFAULT_MICROPHONE_LABEL.casefold(): "system_default",
            self._microphone_key(self.DEFAULT_MICROPHONE_LABEL): "system_default",
        }
        seen: set[str] = set()

        for device in devices:
            if device.get("max_input_channels", 0) <= 0:
                continue

            raw_name = str(device.get("name", "")).strip()
            if not raw_name or self._is_system_endpoint(raw_name):
                continue

            label = self._microphone_display_name(raw_name)
            if not label:
                continue

            key = self._microphone_key(label)
            if key in seen:
                continue

            seen.add(key)
            labels.append(label)
            lookup[label.casefold()] = raw_name
            lookup[raw_name.casefold()] = raw_name
            lookup[key] = raw_name

        self._microphone_lookup = lookup
        return labels

    def normalize_microphone_selection(self, value: str) -> str:
        if not value:
            return self.DEFAULT_MICROPHONE_LABEL
        if value == self.DEFAULT_MICROPHONE_LABEL:
            return value

        raw_name = self._microphone_lookup.get(value.casefold())
        if raw_name is None:
            raw_name = self._microphone_lookup.get(self._microphone_key(value))
        if raw_name is None:
            normalized = self._microphone_display_name(value)
            return normalized or self.DEFAULT_MICROPHONE_LABEL

        normalized = self._microphone_display_name(raw_name)
        return normalized or self.DEFAULT_MICROPHONE_LABEL

    def _resolve_input_device(self) -> int | None:
        selected = self.normalize_microphone_selection(
            self.settings.get("microphone_name", self.DEFAULT_MICROPHONE_LABEL)
        )
        if not selected or selected == self.DEFAULT_MICROPHONE_LABEL:
            return None

        try:
            devices = sd.query_devices()
            selected_key = self._microphone_key(selected)
            for index, device in enumerate(devices):
                if device.get("max_input_channels", 0) <= 0:
                    continue

                raw_name = str(device.get("name", "")).strip()
                if not raw_name:
                    continue

                candidate = self._microphone_display_name(raw_name)
                if self._microphone_key(candidate) == selected_key:
                    return index
                if raw_name.casefold() == selected.casefold():
                    return index
        except Exception:
            return None
        return None

    def _microphone_display_name(self, raw_name: str) -> str:
        cleaned = raw_name.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(
            r"^(microphone|микрофон|input|primary driver|переназначение звуковых устр\.\s*-\s*)\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^-\s*", "", cleaned)
        cleaned = re.sub(r"^(microphone|микрофон|input)\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*@system32.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(@.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*-\s*(input|capture|render).*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("()[]{} -")
        if cleaned.startswith("@"):
            return ""
        if len(cleaned) > 72:
            cleaned = cleaned[:72].rstrip()
        return cleaned

    def _microphone_key(self, raw_name: str) -> str:
        cleaned = raw_name.casefold()
        cleaned = re.sub(r"\(.*?\)", " ", cleaned)
        cleaned = re.sub(r"[^0-9a-zа-яё]+", " ", cleaned)
        cleaned = re.sub(
            r"\b(microphone|микрофон|input|primary|driver|переназначение|звуковых|устр|system|системный|по|умолчанию)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_system_endpoint(self, raw_name: str) -> bool:
        lowered = raw_name.casefold()
        return any(marker in lowered for marker in self.SYSTEM_ENDPOINT_MARKERS) or lowered.startswith("@system32")

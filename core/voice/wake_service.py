from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque

import sounddevice as sd

from core.routing.text_rules import STRICT_WAKE_ALIASES, normalize_text, strip_leading_wake_prefix
from core.voice.model_paths import (
    resolve_vosk_bundled_model_path,
    resolve_vosk_model_path,
    resolve_vosk_runtime_model_path,
    is_vosk_model_ready,
)
from core.voice.vosk_runtime import load_vosk_model, new_vosk_recognizer


class WakeService:
    SAMPLE_RATE = 16_000
    BLOCK_FRAMES = 1600
    PRE_ROLL_FRAMES = 22
    POST_WAKE_BRIDGE_FRAMES = 6
    POST_WAKE_BRIDGE_TIMEOUT = 0.05
    HANDOFF_PHASES = {"capturing_command", "transcribing", "routing", "executing"}

    def __init__(self, settings_service, voice_service) -> None:
        self.settings = settings_service
        self.voice = voice_service
        self.base_dir = resolve_vosk_runtime_model_path().parent
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.user_model_path = resolve_vosk_runtime_model_path()
        self.bundled_model_path = resolve_vosk_bundled_model_path()
        self.model_path = resolve_vosk_model_path()
        self._callback = None
        self._status_callback = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._phase = "idle"
        self._detail = "Слово активации не запущено"
        self._buffer = deque(maxlen=self.PRE_ROLL_FRAMES)
        self._last_detected_at = 0.0
        try:
            from vosk import SetLogLevel

            SetLogLevel(-1)
        except Exception:
            pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def phase(self) -> str:
        return self._phase

    def start(self, on_detected, on_status=None) -> str:
        self._callback = on_detected
        self._status_callback = on_status
        if self._thread and self._thread.is_alive():
            return self.status()
        self._refresh_model_path()
        if not is_vosk_model_ready(self.model_path):
            self._set_phase("error", "Локальная модель слова активации не загружена", ready=False)
            return self.status()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return "Готовлю слово активации"

    def stop(self) -> None:
        self._stop_event.set()
        cancel_pipeline = getattr(self.voice, "cancel_active_pipeline", None)
        if callable(cancel_pipeline):
            cancel_pipeline()
        self._running = False
        if self._phase != "error":
            self._set_phase("idle", "Слово активации не запущено", ready=False)
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def status(self) -> str:
        return self._detail

    def model_status(self) -> str:
        self._refresh_model_path()
        return "загружена" if is_vosk_model_ready(self.model_path) else "не загружена"

    def warm_up_model(self) -> bool:
        self._refresh_model_path()
        if not is_vosk_model_ready(self.model_path):
            return False
        try:
            load_vosk_model(self.model_path)
            return True
        except Exception:
            return False

    def _run(self) -> None:
        try:
            self._set_phase("preparing", "Готовлю слово активации", ready=False)
            load_vosk_model(self.model_path)
            recognizer = self._new_recognizer()

            audio_queue: queue.Queue[bytes] = queue.Queue()

            def callback(indata, frames, time_info, status):  # noqa: ARG001
                if status:
                    return
                audio_queue.put(bytes(indata))

            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_FRAMES,
                dtype="int16",
                device=self.voice._resolve_input_device(),
                channels=1,
                callback=callback,
            ):
                self._running = True
                self._set_phase("waiting_wake", "Жду «Джарвис»", ready=True)

                while not self._stop_event.is_set():
                    try:
                        data = audio_queue.get(timeout=0.3)
                    except queue.Empty:
                        continue

                    self._buffer.append(data)
                    if recognizer.AcceptWaveform(data):
                        detected = self._contains_wake(recognizer.Result())
                    else:
                        detected = self._contains_wake(recognizer.PartialResult(), partial=True)

                    if detected and time.time() - self._last_detected_at > 2.5:
                        self._last_detected_at = time.time()
                        post_roll = self._collect_post_wake_bridge(audio_queue)
                        pre_roll = b"".join(self._buffer) + post_roll
                        self._buffer.clear()
                        self._set_phase("capturing_command", "Подхватываю начало команды", ready=False)
                        self._running = False
                        if self._callback is not None:
                            self._callback(pre_roll)
                        return
        except Exception as exc:
            self._set_phase("error", f"Ошибка слова активации: {exc}", ready=False)
        finally:
            self._running = False
            if not self._phase_in_handoff() and self._phase != "error" and not self._stop_event.is_set():
                self._set_phase("idle", "Слово активации не запущено", ready=False)

    def _new_recognizer(self):
        grammar = [*STRICT_WAKE_ALIASES, "[unk]"]
        return new_vosk_recognizer(self.model_path, self.SAMPLE_RATE, grammar=grammar)

    def _refresh_model_path(self) -> None:
        self.bundled_model_path = resolve_vosk_bundled_model_path()
        self.model_path = resolve_vosk_model_path()

    def _contains_wake(self, payload: str, partial: bool = False) -> bool:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False
        key = "partial" if partial else "text"
        text = normalize_text(str(data.get(key, "")))
        if not text:
            return False
        stripped = strip_leading_wake_prefix(text, aliases=STRICT_WAKE_ALIASES)
        return stripped != text or text.casefold().strip(" ,.:;!?-") in STRICT_WAKE_ALIASES

    def _collect_post_wake_bridge(self, audio_queue: "queue.Queue[bytes]") -> bytes:
        bridge: list[bytes] = []
        for _ in range(self.POST_WAKE_BRIDGE_FRAMES):
            try:
                bridge.append(audio_queue.get(timeout=self.POST_WAKE_BRIDGE_TIMEOUT))
            except queue.Empty:
                break
        return b"".join(bridge)

    def _set_phase(self, phase: str, detail: str, ready: bool) -> None:
        self._phase = phase
        self._detail = detail
        self.voice.set_wake_runtime_status(phase, ready=ready, detail=detail)
        self._emit_status()

    def _emit_status(self) -> None:
        if self._status_callback is not None:
            self._status_callback()

    def _phase_in_handoff(self) -> bool:
        return self._phase in self.HANDOFF_PHASES

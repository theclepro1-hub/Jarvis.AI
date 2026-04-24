from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import zipfile
from collections import deque
from pathlib import Path

import httpx
import sounddevice as sd

from core.routing.text_rules import STRICT_WAKE_ALIASES, normalize_text, strip_leading_wake_prefix
from core.voice.model_paths import (
    MODEL_DIR_NAME,
    resolve_vosk_build_cache_model_path,
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
    MODEL_DOWNLOAD_TIMEOUT_SECONDS = 45.0
    MODEL_DOWNLOAD_CHUNK_BYTES = 256 * 1024

    def __init__(self, settings_service, voice_service) -> None:
        self.settings = settings_service
        self.voice = voice_service
        self.base_dir = resolve_vosk_runtime_model_path().parent
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.user_model_path = resolve_vosk_runtime_model_path()
        self.bundled_model_path = resolve_vosk_bundled_model_path()
        self._model_path = resolve_vosk_model_path()
        self._model_path_overridden = False
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

    @property
    def model_path(self) -> Path:
        return self._model_path

    @model_path.setter
    def model_path(self, value: Path | str) -> None:
        self._model_path = Path(value)
        self._model_path_overridden = True

    def start(self, on_detected, on_status=None) -> str:
        self._callback = on_detected
        self._status_callback = on_status
        if self._thread and self._thread.is_alive():
            if self._phase != "error":
                return self.status()
            self._thread.join(timeout=0.15)
            if self._thread.is_alive():
                return self.status()
        if not self._ensure_model_ready(allow_download=False):
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
        if not self._ensure_model_ready(allow_download=True):
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
                    speaking = self._voice_is_speaking()
                    if recognizer.AcceptWaveform(data):
                        detected = self._contains_wake(recognizer.Result(), barge_in=speaking)
                    else:
                        detected = False if speaking else self._contains_wake(recognizer.PartialResult(), partial=True)

                    if detected and time.time() - self._last_detected_at > 2.5:
                        self._last_detected_at = time.time()
                        if speaking:
                            self._interrupt_tts_for_barge_in()
                            self._buffer.clear()
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
        if not self._model_path_overridden:
            self._model_path = resolve_vosk_model_path()

    def _ensure_model_ready(self, *, allow_download: bool) -> bool:
        self._refresh_model_path()
        if is_vosk_model_ready(self.model_path):
            return True
        if self._model_path_overridden:
            return False
        if self._seed_runtime_model_from_local_sources():
            self._refresh_model_path()
            if is_vosk_model_ready(self.model_path):
                return True
        if allow_download and self._allow_model_download() and self._download_runtime_model():
            self._refresh_model_path()
            return is_vosk_model_ready(self.model_path)
        return False

    def _seed_runtime_model_from_local_sources(self) -> bool:
        if is_vosk_model_ready(self.user_model_path):
            return True
        candidates = (
            self.bundled_model_path,
            resolve_vosk_build_cache_model_path(),
            resolve_vosk_model_path(),
        )
        seen: set[Path] = set()
        for candidate in candidates:
            path = Path(candidate)
            if path in seen or path == self.user_model_path:
                continue
            seen.add(path)
            if not is_vosk_model_ready(path):
                continue
            if self._copy_model_tree(path, self.user_model_path):
                return True
        return False

    def _allow_model_download(self) -> bool:
        raw = str(os.environ.get("JARVIS_UNITY_WAKE_AUTO_DOWNLOAD", "1")).strip().casefold()
        return raw not in {"0", "false", "off", "no"}

    def _download_runtime_model(self) -> bool:
        runtime_path = self.user_model_path
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        download_url = str(
            os.environ.get(
                "JARVIS_UNITY_WAKE_MODEL_URL",
                f"https://alphacephei.com/vosk/models/{MODEL_DIR_NAME}.zip",
            )
        ).strip()
        if not download_url:
            return False
        archive_path = runtime_path.parent / f"{MODEL_DIR_NAME}.zip.download"
        extract_dir = runtime_path.parent / f".{MODEL_DIR_NAME}.extract"
        self._set_phase("preparing", "Загружаю модель слова активации", ready=False)
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
            extract_dir.mkdir(parents=True, exist_ok=True)
            if archive_path.exists():
                archive_path.unlink()
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.MODEL_DOWNLOAD_TIMEOUT_SECONDS,
                write=20.0,
                pool=10.0,
            )
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    with archive_path.open("wb") as handle:
                        for chunk in response.iter_bytes(chunk_size=self.MODEL_DOWNLOAD_CHUNK_BYTES):
                            if chunk:
                                handle.write(chunk)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_dir)
            extracted_root = self._locate_extracted_model_root(extract_dir)
            if extracted_root is None:
                return False
            return self._copy_model_tree(extracted_root, runtime_path)
        except Exception:
            return False
        finally:
            try:
                if archive_path.exists():
                    archive_path.unlink()
            except Exception:
                pass
            shutil.rmtree(extract_dir, ignore_errors=True)

    def _locate_extracted_model_root(self, extract_dir: Path) -> Path | None:
        expected_dir = extract_dir / MODEL_DIR_NAME
        if is_vosk_model_ready(expected_dir):
            return expected_dir
        if is_vosk_model_ready(extract_dir):
            return extract_dir
        for child in extract_dir.iterdir():
            if child.is_dir() and is_vosk_model_ready(child):
                return child
        return None

    def _copy_model_tree(self, source: Path, target: Path) -> bool:
        temp_target = target.parent / f".{target.name}.copy"
        try:
            shutil.rmtree(temp_target, ignore_errors=True)
            shutil.copytree(source, temp_target, dirs_exist_ok=True)
            shutil.rmtree(target, ignore_errors=True)
            temp_target.replace(target)
            return is_vosk_model_ready(target)
        except Exception:
            return False
        finally:
            shutil.rmtree(temp_target, ignore_errors=True)

    def _contains_wake(self, payload: str, partial: bool = False, barge_in: bool = False) -> bool:
        if barge_in and partial:
            return False
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

    def _voice_is_speaking(self) -> bool:
        return bool(getattr(self.voice, "is_speaking", False))

    def _interrupt_tts_for_barge_in(self) -> None:
        interrupt = getattr(self.voice, "interrupt_tts", None)
        if callable(interrupt):
            interrupt()

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

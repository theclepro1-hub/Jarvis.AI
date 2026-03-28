import audioop
import logging
import os
import tempfile
import threading
import time
import tkinter as tk
import wave

import speech_recognition as sr

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import winsound
except Exception:
    winsound = None

from .audio_devices import _find_audio_device_entry_by_name, pick_microphone_device
from .branding import APP_LOGGER_NAME, app_title
from .commands import detect_wake_word, normalize_text, strip_wake_word
from .state import CONFIG_MGR
from .theme import Theme
from .utils import short_exc
from .voice_profiles import device_profile_kind


logger = logging.getLogger(APP_LOGGER_NAME)


def _voice_device_bucket(device_name: str = "") -> str:
    low = str(device_name or "").strip().lower()
    if any(token in low for token in ("webcam", "camera", "камера", "c922", "c920", "brio")):
        return "webcam"
    return device_profile_kind(device_name)


def _friendly_profile_label(profile_name: str) -> str:
    labels = {
        "normal": "базовый",
        "boost": "усиленный",
        "aggressive": "максимальный",
    }
    key = str(profile_name or "").strip().lower()
    return labels.get(key, key or "базовый")


def _friendly_bucket_label(bucket: str) -> str:
    labels = {
        "headset": "гарнитура",
        "usb_mic": "USB-микрофон",
        "built_in": "встроенный микрофон",
        "webcam": "веб-камера",
        "default": "универсальный профиль",
    }
    key = str(bucket or "").strip()
    return labels.get(key, key or "универсальный профиль")


def _meter_samplerate_candidates(device_entry=None, device_index=None):
    seen = set()
    candidates = []

    def add(rate):
        try:
            value = int(float(rate or 0))
        except Exception:
            value = 0
        if value <= 0 or value in seen:
            return
        seen.add(value)
        candidates.append(value)

    if isinstance(device_entry, dict):
        add(device_entry.get("default_samplerate"))

    if sd is not None:
        try:
            if device_index is None:
                info = sd.query_devices(kind="input")
            else:
                info = sd.query_devices(int(device_index))
            if isinstance(info, dict):
                add(info.get("default_samplerate"))
        except Exception:
            pass

    for rate in (48000, 44100, 32000, 24000, 22050, 16000):
        add(rate)
    return candidates or [16000]


def _resolve_meter_stream_config(device_entry=None, device_index=None):
    if sd is None:
        return None, "sounddevice не установлен"

    errors = []
    for rate in _meter_samplerate_candidates(device_entry, device_index):
        kwargs = {
            "samplerate": rate,
            "channels": 1,
            "dtype": "int16",
        }
        if device_index is not None:
            kwargs["device"] = int(device_index)
        try:
            checker = getattr(sd, "check_input_settings", None)
            if callable(checker):
                checker(**kwargs)
            return kwargs, ""
        except Exception as exc:
            message = short_exc(exc)
            if message not in errors:
                errors.append(message)
    return None, "; ".join(errors[:2]).strip() or "не удалось подобрать совместимый режим"


def _ensure_voice_debug_state(self):
    if not hasattr(self, "_voice_meter_level"):
        self._voice_meter_level = 0
    if not hasattr(self, "_voice_meter_rms"):
        self._voice_meter_rms = 0
    if not hasattr(self, "_voice_meter_threshold"):
        self._voice_meter_threshold = 180
    if not hasattr(self, "_voice_meter_device_name"):
        self._voice_meter_device_name = ""
    if not hasattr(self, "_wake_debug_text"):
        self._wake_debug_text = "Wake-word: жду слово 'джарвис'."
    if not hasattr(self, "_voice_meter_stop"):
        self._voice_meter_stop = False
    if not hasattr(self, "_voice_meter_thread"):
        self._voice_meter_thread = None
    if not hasattr(self, "_voice_training_peak"):
        self._voice_training_peak = 0
    if not hasattr(self, "_last_auto_profile_bucket"):
        self._last_auto_profile_bucket = ""
    if not hasattr(self, "_last_auto_profile_name"):
        self._last_auto_profile_name = ""
    if not hasattr(self, "_voice_last_heard_text"):
        self._voice_last_heard_text = "Пока нет распознанных фраз."
    if not hasattr(self, "_voice_test_audio_path"):
        self._voice_test_audio_path = ""
    if not hasattr(self, "_voice_test_recording"):
        self._voice_test_recording = False
    self._apply_voice_insight_widgets()


def _apply_voice_insight_widgets(self):
    meter_var = getattr(self, "voice_meter_var", None)
    wake_var = getattr(self, "wake_debug_var", None)
    explainer_var = getattr(self, "action_explainer_var", None)
    last_heard_var = getattr(self, "voice_last_heard_var", None)
    corner_var = getattr(self, "corner_voice_meter_var", None)
    corner_stats_var = getattr(self, "corner_voice_stats_var", None)
    level = int(max(0, min(100, getattr(self, "_voice_meter_level", 0) or 0)))
    rms = int(getattr(self, "_voice_meter_rms", 0) or 0)
    threshold = int(max(80, getattr(self, "_voice_meter_threshold", 0) or 0))
    device_name = str(getattr(self, "_voice_meter_device_name", "") or self.get_selected_microphone_name() or "").strip()
    bucket = _voice_device_bucket(device_name)
    if meter_var is not None:
        profile_name = str(self._cfg().get_listening_profile() or "normal").strip().lower()
        meter_var.set(
            f"Уровень микрофона: {level}%  •  RMS {rms} / порог {threshold}  •  "
            f"{_friendly_bucket_label(bucket)}  •  профиль {_friendly_profile_label(profile_name)}"
        )
    if wake_var is not None:
        wake_var.set(str(getattr(self, "_wake_debug_text", "Wake-word: жду слово 'джарвис'.") or "").strip())
    if explainer_var is not None and not str(explainer_var.get() or "").strip():
        explainer_var.set("JARVIS коротко покажет, что понял, перед сложным действием.")
    if last_heard_var is not None:
        last_heard_var.set(str(getattr(self, "_voice_last_heard_text", "Пока нет распознанных фраз.") or "").strip())
    if corner_var is not None:
        corner_var.set(f"Микрофон {level}%")
    if corner_stats_var is not None:
        corner_stats_var.set(f"RMS {rms}  •  порог {threshold}")

    for canvas_name in ("voice_meter_canvas", "voice_meter_canvas_secondary", "corner_voice_meter_canvas"):
        canvas = getattr(self, canvas_name, None)
        if canvas is None:
            continue
        try:
            minimum_width = 180 if canvas_name == "corner_voice_meter_canvas" else 260
            width = max(int(canvas.winfo_width() or 0), minimum_width)
            height = max(int(canvas.winfo_height() or 0), 14 if canvas_name == "corner_voice_meter_canvas" else 16)
            fill_width = int((width - 2) * (level / 100.0))
            if level >= 65:
                fill = "#22c55e"
            elif level >= 35:
                fill = Theme.ACCENT
            else:
                fill = "#38bdf8"
            canvas.delete("all")
            canvas.create_rectangle(0, 0, width, height, fill=Theme.INPUT_BG, outline=Theme.BORDER)
            if fill_width > 0:
                canvas.create_rectangle(1, 1, max(1, fill_width), height - 1, fill=fill, outline=fill)
        except Exception:
            pass


def _set_last_heard_text(self, text: str = ""):
    _ensure_voice_debug_state(self)
    message = str(text or "").strip() or "Пока нет распознанных фраз."
    self._voice_last_heard_text = message[:280]
    try:
        self.root.after(0, self._apply_voice_insight_widgets)
    except Exception:
        pass


def _voice_test_target_path() -> str:
    return os.path.join(tempfile.gettempdir(), "jarvis_ai_2_voice_test.wav")


def run_voice_recording_test(self):
    _ensure_voice_debug_state(self)
    if getattr(self, "_voice_test_recording", False):
        self.set_status_temp("Тестовая запись уже идет", "warn")
        return
    if sd is None:
        self.set_status_temp("Тестовая запись недоступна: sounddevice не установлен", "warn", duration_ms=3200)
        return

    self._voice_test_recording = True
    self._set_last_heard_text("Идет тестовая запись. Говорите 4 секунды обычным голосом.")
    self.set_status_temp("Записываю тест голоса...", "busy", duration_ms=1800)

    def _worker():
        try:
            device_name = str(self.get_selected_microphone_name() or "").strip()
            entry = _find_audio_device_entry_by_name(device_name, kind="input", refresh=False)
            device_index = entry.get("index") if isinstance(entry, dict) else None
            stream_kwargs, stream_error = _resolve_meter_stream_config(entry, device_index)
            if not stream_kwargs:
                raise RuntimeError(stream_error or "Не удалось подобрать режим записи")

            rate = int(stream_kwargs.get("samplerate") or 16000)
            frames = int(rate * 4)
            record_kwargs = {
                "samplerate": rate,
                "channels": 1,
                "dtype": "int16",
                "frames": frames,
            }
            if device_index is not None:
                record_kwargs["device"] = int(device_index)
            data = sd.rec(**record_kwargs)
            sd.wait()
            raw = data.tobytes()
            path = _voice_test_target_path()
            with wave.open(path, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(rate)
                handle.writeframes(raw)
            self._voice_test_audio_path = path

            audio = sr.AudioData(raw, rate, 2)
            transcript = ""
            try:
                transcript = str(self._recognize_audio_text(audio, manual_mode=True) or "").strip()
            except Exception:
                transcript = ""

            if transcript:
                self._set_last_heard_text("Тест распознан: " + transcript)
            else:
                self._set_last_heard_text("Запись готова. Текст распознать не удалось, но файл можно прослушать.")
            self.root.after(0, lambda: self.set_status_temp("Тестовая запись готова", "ok", duration_ms=2600))
        except Exception as exc:
            detail = short_exc(exc)
            self._set_last_heard_text("Тестовая запись не удалась: " + detail)
            if hasattr(self, "_record_human_log"):
                try:
                    self._record_human_log("Тестовая запись", "Не удалось записать тест микрофона.", "Откройте центр голоса, смените микрофон и повторите тест.", level="warn")
                except Exception:
                    pass
            self.root.after(0, lambda: self.set_status_temp("Тестовая запись не удалась", "warn", duration_ms=3200))
        finally:
            self._voice_test_recording = False
            try:
                self.root.after(0, self._apply_voice_insight_widgets)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True, name="VoiceTestRecording").start()


def play_last_voice_capture(self):
    path = str(getattr(self, "_voice_test_audio_path", "") or "").strip()
    if not path or not os.path.exists(path):
        self.set_status_temp("Сначала сделайте тестовую запись", "warn")
        return
    if winsound is None:
        self.set_status_temp("Прослушивание доступно только в Windows-среде", "warn", duration_ms=2800)
        return
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        self.set_status_temp("Воспроизвожу последнюю тестовую запись", "ok", duration_ms=2400)
    except Exception as exc:
        self.set_status_temp("Не удалось воспроизвести запись", "warn", duration_ms=2800)
        if hasattr(self, "_record_human_log"):
            try:
                self._record_human_log("Прослушивание записи", "Не получилось воспроизвести тестовый файл микрофона.", "Повторите тестовую запись и проверьте устройство вывода.", level="warn")
            except Exception:
                pass
        logger.warning(f"Voice playback error: {exc}")


def show_last_voice_capture_summary(self):
    _ensure_voice_debug_state(self)
    path = str(getattr(self, "_voice_test_audio_path", "") or "").strip()
    heard = str(getattr(self, "_voice_last_heard_text", "") or "").strip() or "Пока нет распознанных фраз."
    device_name = str(self.get_selected_microphone_name() or "микрофон по умолчанию").strip()
    profile_name = str(self._cfg().get_listening_profile() or "normal").strip().lower()
    lines = [
        "Центр голоса",
        "",
        "Последнее, что услышал JARVIS:",
        heard,
        "",
        f"Микрофон: {device_name}",
        f"Профиль: {_friendly_profile_label(profile_name)}",
        f"Файл тестовой записи: {path or 'пока нет'}",
    ]
    report = "\n".join(lines).strip()
    if hasattr(self, "_show_text_report_window"):
        self._show_text_report_window("Центр голоса", report, geometry="680x420")
    else:
        self.set_status_temp(heard[:90], "ok", duration_ms=2800)


def _update_audio_signal_snapshot(self, rms: int = 0, device_name: str = ""):
    self._ensure_voice_debug_state()
    raw_threshold = int(float(getattr(self.recognizer, "energy_threshold", 1200) or 1200))
    threshold = max(80, raw_threshold)
    level = int(min(100, max(0, (float(rms or 0) / float(threshold)) * 210.0)))
    self._voice_meter_rms = int(rms or 0)
    self._voice_meter_threshold = threshold
    self._voice_meter_level = level
    if device_name:
        self._voice_meter_device_name = str(device_name or "").strip()
    self._voice_training_peak = max(int(getattr(self, "_voice_training_peak", 0) or 0), level)
    try:
        self.root.after(0, self._apply_voice_insight_widgets)
    except Exception:
        pass


def _set_wake_debug(self, reason: str = "", heard_text: str = "", matched_word: str = "", rms: int = 0, threshold: int = 0):
    if not self._cfg().get_wake_debug_enabled():
        self._wake_debug_text = "Wake-word debug выключен."
    else:
        reason_text = str(reason or "").strip() or "ожидание"
        heard = str(heard_text or "").strip()
        matched = str(matched_word or "").strip()
        pieces = [f"Wake-word: {reason_text}"]
        if matched:
            pieces.append(f"слово: {matched}")
        if heard:
            pieces.append(f"услышал: '{heard[:80]}'")
        if rms or threshold:
            pieces.append(f"rms {int(rms or 0)} / порог {int(max(80, threshold or 0))}")
        self._wake_debug_text = "  •  ".join(pieces)
    try:
        self.root.after(0, self._apply_voice_insight_widgets)
    except Exception:
        pass


def _maybe_auto_switch_device_profile(self, device_name: str = ""):
    cfg = self._cfg()
    if str(cfg.get_device_profile_mode() or "auto").strip().lower() != "auto":
        return
    device_name = str(device_name or self.get_selected_microphone_name() or "").strip()
    bucket = _voice_device_bucket(device_name)
    overrides = dict(cfg.get_device_profile_overrides() or {})
    target = str(overrides.get(bucket) or overrides.get("default") or "normal").strip().lower()
    current = str(cfg.get_listening_profile() or "normal").strip().lower()
    if target not in {"normal", "boost", "aggressive"}:
        target = "normal"
    if bucket == getattr(self, "_last_auto_profile_bucket", "") and target == getattr(self, "_last_auto_profile_name", ""):
        return
    self._last_auto_profile_bucket = bucket
    self._last_auto_profile_name = target
    if current != target:
        try:
            cfg.set_listening_profile(target)
            self.apply_listening_profile(target)
            self.set_status_temp(f"Голосовой профиль: {target}", "ok", duration_ms=2200)
        except Exception:
            pass


def _attempt_voice_recovery(self, error_text: str = ""):
    if not self._cfg().get_auto_recovery_enabled():
        return
    try:
        self._apply_proxy_env_from_config()
        self.proxy_detected = self._detect_proxy_enabled()
    except Exception:
        pass
    try:
        names = self._get_microphone_devices(refresh=True)
    except Exception:
        names = []
    selected_index = self._cfg().get_mic_device_index()
    invalid_index = selected_index is not None and (
        not isinstance(selected_index, int) or selected_index < 0 or selected_index >= len(names)
    )
    if invalid_index or not names:
        try:
            auto_index, auto_name = pick_microphone_device()
            CONFIG_MGR.set_mic_device_index(auto_index)
            CONFIG_MGR.set_mic_device_name(auto_name or "")
        except Exception:
            pass
    try:
        self.refresh_mic_status_label()
        self.refresh_tts_status_label()
        self._apply_tts_auto_network_mode(self.is_online)
        self.apply_listening_profile(CONFIG_MGR.get_listening_profile())
    except Exception:
        pass
    if error_text:
        try:
            self.set_status_temp("Пробую восстановить голосовой контур...", "warn", duration_ms=2200)
        except Exception:
            pass


def _start_audio_meter_monitor(self):
    self._ensure_voice_debug_state()
    if getattr(self, "_voice_meter_thread", None) and self._voice_meter_thread.is_alive():
        return
    self._voice_meter_stop = False
    if sd is None:
        self._set_wake_debug("живой индикатор недоступен: sounddevice не установлен")
        return
    thread = threading.Thread(target=self._audio_meter_task, daemon=True, name="VoiceMeterThread")
    self._voice_meter_thread = thread
    thread.start()


def _audio_meter_task(self):
    last_token = None
    while self.running and not getattr(self, "_voice_meter_stop", False):
        if not self._cfg().get_microphone_meter_enabled():
            self._update_audio_signal_snapshot(0, self.get_selected_microphone_name())
            time.sleep(0.5)
            continue
        device_name = str(self.get_selected_microphone_name() or "").strip()
        entry = _find_audio_device_entry_by_name(device_name, kind="input", refresh=False)
        device_index = entry.get("index") if isinstance(entry, dict) else None
        token = (device_index, device_name)
        if token != last_token:
            self._maybe_auto_switch_device_profile(device_name)
            last_token = token

        stream_kwargs, stream_error = _resolve_meter_stream_config(entry, device_index)
        if not stream_kwargs:
            self._update_audio_signal_snapshot(0, device_name or "микрофон по умолчанию")
            self._set_wake_debug("монитор микрофона работает в безопасном режиме")
            logger.warning(f"Voice meter fallback for device '{device_name or 'default'}': {stream_error}")
            time.sleep(1.8)
            continue

        try:
            last_rms = {"value": 0}

            def _callback(indata, _frames, _time_info, status):
                try:
                    raw = bytes(indata or b"")
                    rms = audioop.rms(raw, 2) if raw else 0
                    last_rms["value"] = int(rms or 0)
                    self._update_audio_signal_snapshot(rms, device_name)
                    if status:
                        self._set_wake_debug(
                            "монитор микрофона сообщил о состоянии",
                            rms=rms,
                            threshold=getattr(self.recognizer, "energy_threshold", 0),
                        )
                except Exception:
                    pass

            stream_kwargs = dict(stream_kwargs)
            stream_kwargs["blocksize"] = 1024
            stream_kwargs["callback"] = _callback

            with sd.RawInputStream(**stream_kwargs):
                quiet_ticks = 0
                while self.running and not getattr(self, "_voice_meter_stop", False):
                    current_name = str(self.get_selected_microphone_name() or "").strip()
                    current_entry = _find_audio_device_entry_by_name(current_name, kind="input", refresh=False)
                    current_index = current_entry.get("index") if isinstance(current_entry, dict) else None
                    if (current_index, current_name) != token:
                        break
                    if last_rms["value"] <= 0:
                        quiet_ticks += 1
                        if quiet_ticks >= 6:
                            self._update_audio_signal_snapshot(0, current_name)
                    else:
                        quiet_ticks = 0
                    time.sleep(0.18)
        except Exception as exc:
            if not self.running:
                break
            message = short_exc(exc)
            low = str(message).lower()
            if "invalid sample rate" in low or "-9997" in low:
                self._set_wake_debug("монитор микрофона подбирает совместимый режим")
            else:
                self._set_wake_debug("монитор микрофона временно недоступен")
            logger.warning(f"Voice meter stream error: {exc}")
            time.sleep(1.2)


def _patched_mic_pulse_tick(self):
    try:
        active = self._is_manual_listen_active()
        if active:
            self.mic_pulse_state = not self.mic_pulse_state
            self.mic_btn.config(bg="#16a34a" if self.mic_pulse_state else "#15803d", fg=Theme.MIC_ICON_FG)
            self.refresh_mic_status_label("слушаю")
        else:
            self.mic_btn.config(bg=Theme.BUTTON_BG, fg=Theme.MIC_ICON_FG)
        self._apply_voice_insight_widgets()
    except Exception as exc:
        logger.warning(f"patched mic_pulse_tick error: {exc}")
    if getattr(self, "running", False):
        self.root.after(320, self.mic_pulse_tick)


def _patched_listen_task(self):
    mic = None
    mic_source = None
    current_device_index = self.get_selected_microphone_index()
    current_device_name = self.get_selected_microphone_name()
    last_ambient_adjust = 0.0
    last_passive_mode = None

    while self.running:
        try:
            desired_index = self.get_selected_microphone_index()
            desired_name = self.get_selected_microphone_name()
            if desired_index != current_device_index:
                current_device_index = desired_index
                current_device_name = desired_name
                if mic is not None:
                    try:
                        mic.__exit__(None, None, None)
                    except Exception:
                        pass
                    mic = None
                    mic_source = None

            if mic is None:
                mic = sr.Microphone(device_index=current_device_index) if current_device_index is not None else sr.Microphone()
                mic_source = mic.__enter__()
                if mic_source is None or not getattr(mic_source, "stream", None):
                    raise RuntimeError("Microphone stream is not initialized.")
                passive_mode = self._should_use_wake_word_boost()
                self._apply_listening_values(self._compose_listening_values(self._cfg().get_listening_profile(), passive_mode=passive_mode))
                self.recognizer.adjust_for_ambient_noise(mic_source, duration=0.42 if passive_mode else 0.60)
                self._clamp_energy_after_adjust(passive_mode=passive_mode)
                self._maybe_auto_switch_device_profile(current_device_name)
                last_passive_mode = passive_mode
                last_ambient_adjust = time.monotonic()
                self.root.after(0, lambda: self.refresh_mic_status_label("готов"))
                self._set_wake_debug("жду слово 'джарвис'", rms=0, threshold=getattr(self.recognizer, "energy_threshold", 0))

            while self.running:
                if self.speaking:
                    time.sleep(0.05)
                    continue

                now = time.monotonic()
                manual_mode = self._is_manual_listen_active(now)
                passive_mode = not manual_mode
                manual_deadline = self._manual_listen_deadline()
                timeout, phrase_time_limit = self._capture_params_for_listening(manual_mode)

                if last_passive_mode is None or passive_mode != last_passive_mode:
                    self._apply_listening_values(self._compose_listening_values(self._cfg().get_listening_profile(), passive_mode=passive_mode))
                    last_passive_mode = passive_mode

                if manual_deadline > 0 and now >= manual_deadline:
                    if manual_mode:
                        self._set_wake_debug("не слышу голос", rms=0, threshold=getattr(self.recognizer, "energy_threshold", 0))
                        self._complete_manual_listen_with_status("Не слышу голос. Попробуйте еще раз.", "warn", duration_ms=2400)
                    continue

                recalibrate_after = 24.0 if passive_mode else 36.0
                if (now - last_ambient_adjust) > recalibrate_after:
                    try:
                        self.recognizer.adjust_for_ambient_noise(mic_source, duration=0.12 if passive_mode else 0.18)
                        self._clamp_energy_after_adjust(passive_mode=passive_mode)
                        last_ambient_adjust = now
                    except Exception:
                        pass

                try:
                    with self._mic_listen_lock:
                        audio = self.recognizer.listen(
                            mic_source if mic_source is not None else mic,
                            timeout=timeout,
                            phrase_time_limit=phrase_time_limit,
                        )
                    _raw, rms, duration = self._audio_signal_stats(audio)
                    self._update_audio_signal_snapshot(rms, current_device_name)
                    threshold = getattr(self.recognizer, "energy_threshold", 0)
                    if duration < 0.1:
                        self._set_wake_debug("слишком короткий фрагмент", rms=rms, threshold=threshold)
                    text = self._recognize_audio_text(audio, manual_mode=manual_mode)
                    if text:
                        self._set_last_heard_text(text)
                except sr.WaitTimeoutError:
                    if manual_mode and manual_deadline > 0 and time.monotonic() >= manual_deadline:
                        self._set_wake_debug("таймаут ожидания голоса", rms=0, threshold=getattr(self.recognizer, "energy_threshold", 0))
                        self._complete_manual_listen_with_status("Не слышу голос. Попробуйте еще раз.", "warn", duration_ms=2400)
                    continue
                except sr.UnknownValueError:
                    self._set_wake_debug("речь не распознана", rms=getattr(self, "_voice_meter_rms", 0), threshold=getattr(self.recognizer, "energy_threshold", 0))
                    if manual_mode:
                        if manual_deadline > 0 and time.monotonic() < manual_deadline:
                            continue
                        self._complete_manual_listen_with_status("Не разобрал команду. Повторите еще раз.", "warn", duration_ms=2400)
                    continue
                except sr.RequestError as exc:
                    err = str(exc).lower()
                    if "timed out" in err or "timeout" in err or "connection failed" in err:
                        self._log_listen_transient_issue(exc)
                    else:
                        logger.error(f"Speech API error: {exc}")
                    self._set_wake_debug(
                        "сервис распознавания временно недоступен",
                        rms=getattr(self, "_voice_meter_rms", 0),
                        threshold=getattr(self.recognizer, "energy_threshold", 0),
                    )
                    self._attempt_voice_recovery(str(exc))
                    if manual_mode:
                        self._complete_manual_listen_with_status("Распознавание речи недоступно. Проверьте интернет и Groq API ключ.", "warn", duration_ms=3400)
                    time.sleep(0.35)
                    continue
                except Exception as exc:
                    err = str(exc).lower()
                    transient_markers = ("10054", "timed out", "timeout", "forcibly closed", "connection reset", "принудительно разорвано")
                    if "audio source must be entered before adjusting" in err or ("audiosource" in err and "with" in err):
                        logger.warning("STT source lost context, reopening microphone stream.")
                        self._set_wake_debug("перезапускаю аудиоисточник")
                        break
                    if any(marker in err for marker in transient_markers):
                        self._log_listen_transient_issue(exc)
                        self._set_wake_debug("потеряна связь с голосовым сервисом", rms=getattr(self, "_voice_meter_rms", 0), threshold=getattr(self.recognizer, "energy_threshold", 0))
                        self._attempt_voice_recovery(str(exc))
                        if manual_mode:
                            self._complete_manual_listen_with_status("Потеряна связь с голосовым сервисом. Попробуйте еще раз.", "warn", duration_ms=3200)
                        time.sleep(0.35)
                        continue
                    logger.warning(f"Unexpected listen error: {exc}")
                    self._set_wake_debug("ошибка микрофона")
                    break

                norm = normalize_text(text)
                if manual_mode:
                    self._finish_manual_listen()
                    self._set_wake_debug("ручная команда распознана", heard_text=text, rms=getattr(self, "_voice_meter_rms", 0), threshold=getattr(self.recognizer, "energy_threshold", 0))
                    self.root.after(0, lambda t=text: self.add_msg(t, "user"))
                    self.executor.submit(self.process_query, text)
                    continue

                if not self._cfg().get_active_listening_enabled():
                    continue

                detected, matched_word = detect_wake_word(norm)
                if detected:
                    command_text = strip_wake_word(norm)
                    self._set_wake_debug("wake-word сработал", heard_text=text, matched_word=matched_word, rms=getattr(self, "_voice_meter_rms", 0), threshold=getattr(self.recognizer, "energy_threshold", 0))
                    if command_text:
                        self.root.after(0, lambda t=command_text: self.add_msg(t, "user"))
                        self.executor.submit(self.process_query, command_text)
                    else:
                        self._begin_manual_listen(5.5)
                    continue

                self._set_wake_debug("слово не найдено", heard_text=text, rms=getattr(self, "_voice_meter_rms", 0), threshold=getattr(self.recognizer, "energy_threshold", 0))

            if mic is not None:
                try:
                    mic.__exit__(None, None, None)
                except Exception:
                    pass
                mic = None
                mic_source = None
        except Exception as exc:
            if not self.running:
                break
            if "main thread is not in main loop" in str(exc).lower():
                break
            logger.error(f"STT error: {exc}")
            self._attempt_voice_recovery(str(exc))
            if mic:
                try:
                    mic.__exit__(None, None, None)
                except Exception:
                    pass
                mic = None
            mic_source = None
            self._clear_manual_listen_state()
            if self.running:
                try:
                    self.root.after(0, lambda: self.set_status("Готов", "ok"))
                except Exception:
                    pass
            time.sleep(1)


def run_voice_training_wizard(self):
    if getattr(self, "_voice_training_window", None):
        try:
            if self._voice_training_window.winfo_exists():
                self._voice_training_window.lift()
                return
        except Exception:
            pass
    self._ensure_voice_debug_state()
    win = tk.Toplevel(self.root)
    self._voice_training_window = win
    win.title(app_title("Обучение слышимости"))
    win.geometry("600x420")
    win.configure(bg=Theme.BG)
    win.transient(self.root)

    shell = tk.Frame(win, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    shell.pack(fill="both", expand=True, padx=12, pady=12)
    tk.Label(shell, text="Обучение слышимости", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=16, pady=(16, 6))
    tk.Label(shell, text="Скажите три короткие фразы обычным голосом. JARVIS посмотрит на пики громкости и подберет профиль сам.", bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 10)).pack(fill="x", padx=16, pady=(0, 10))

    step_var = tk.StringVar(value="Шаг 1 из 3")
    hint_var = tk.StringVar(value="Нажмите «Начать» и скажите: «Джарвис, проверка связи».")
    result_var = tk.StringVar(value="Пиков пока нет.")
    tk.Label(shell, textvariable=step_var, bg=Theme.CARD_BG, fg=Theme.ACCENT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16)
    tk.Label(shell, textvariable=hint_var, bg=Theme.CARD_BG, fg=Theme.FG, justify="left", font=("Segoe UI", 11)).pack(fill="x", padx=16, pady=(6, 10))
    meter = tk.Canvas(shell, height=18, bg=Theme.CARD_BG, highlightthickness=0)
    meter.pack(fill="x", padx=16, pady=(0, 10))
    tk.Label(shell, textvariable=result_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, justify="left", font=("Segoe UI", 10)).pack(fill="x", padx=16, pady=(0, 12))

    actions = tk.Frame(shell, bg=Theme.CARD_BG)
    actions.pack(fill="x", padx=16, pady=(0, 16))
    samples = []
    prompts = [
        "Скажите: «Джарвис, проверка связи».",
        "Скажите: «Открой YouTube».",
        "Скажите: «Какой сейчас профиль?».",
    ]
    state = {"step": 0, "active": False}

    def _close():
        self._voice_training_window = None
        try:
            win.destroy()
        except Exception:
            pass

    def _render_meter():
        width = max(int(meter.winfo_width() or 0), 300)
        level = int(getattr(self, "_voice_training_peak", 0) or 0)
        fill_width = int((width - 2) * (max(0, min(100, level)) / 100.0))
        meter.delete("all")
        meter.create_rectangle(0, 0, width, 18, fill=Theme.INPUT_BG, outline=Theme.BORDER)
        if fill_width > 0:
            meter.create_rectangle(1, 1, fill_width, 17, fill=Theme.ACCENT, outline=Theme.ACCENT)
        if state["active"] and win.winfo_exists():
            win.after(160, _render_meter)

    def _finish_step():
        if not win.winfo_exists():
            return
        state["active"] = False
        peak = int(getattr(self, "_voice_training_peak", 0) or 0)
        samples.append(peak)
        result_var.set("Пики: " + ", ".join(str(x) for x in samples))
        state["step"] += 1
        if state["step"] >= len(prompts):
            avg = sum(samples) / max(1, len(samples))
            if avg < 24:
                profile = "aggressive"
            elif avg < 50:
                profile = "boost"
            else:
                profile = "normal"
            self._cfg().set_listening_profile(profile)
            self.apply_listening_profile(profile)
            if str(self._cfg().get_device_profile_mode() or "auto").strip().lower() == "auto":
                overrides = dict(self._cfg().get_device_profile_overrides() or {})
                overrides[_voice_device_bucket(self.get_selected_microphone_name())] = profile
                self._cfg().set_device_profile_overrides(overrides)
            self._apply_voice_insight_widgets()
            self.set_status_temp(f"Профиль слышимости: {profile}", "ok", duration_ms=2800)
            hint_var.set(f"Готово. Рекомендованный профиль: {profile}. Его уже применил.")
            start_btn.configure(state="disabled", text="Готово")
            return
        step_var.set(f"Шаг {state['step'] + 1} из 3")
        hint_var.set("Нажмите «Дальше» и " + prompts[state["step"]].lower())
        start_btn.configure(state="normal", text="Дальше")

    def _start_step():
        if state["active"]:
            return
        self._voice_training_peak = 0
        state["active"] = True
        hint_var.set("Говорите сейчас. JARVIS собирает уровень сигнала 3 секунды...")
        start_btn.configure(state="disabled")
        _render_meter()
        win.after(3200, _finish_step)

    win.protocol("WM_DELETE_WINDOW", _close)
    start_btn = tk.Button(actions, text="Начать", command=_start_step, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8)
    start_btn.pack(side="right")
    tk.Button(actions, text="Закрыть", command=_close, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=8).pack(side="right", padx=(0, 8))


def register_voice_runtime(app_cls):
    app_cls._ensure_voice_debug_state = _ensure_voice_debug_state
    app_cls._apply_voice_insight_widgets = _apply_voice_insight_widgets
    app_cls._update_audio_signal_snapshot = _update_audio_signal_snapshot
    app_cls._set_wake_debug = _set_wake_debug
    app_cls._maybe_auto_switch_device_profile = _maybe_auto_switch_device_profile
    app_cls._attempt_voice_recovery = _attempt_voice_recovery
    app_cls._start_audio_meter_monitor = _start_audio_meter_monitor
    app_cls._audio_meter_task = _audio_meter_task
    app_cls._set_last_heard_text = _set_last_heard_text
    app_cls.run_voice_recording_test = run_voice_recording_test
    app_cls.play_last_voice_capture = play_last_voice_capture
    app_cls.show_last_voice_capture_summary = show_last_voice_capture_summary
    app_cls.mic_pulse_tick = _patched_mic_pulse_tick
    app_cls.listen_task = _patched_listen_task
    app_cls.run_voice_training_wizard = run_voice_training_wizard


__all__ = ["register_voice_runtime"]

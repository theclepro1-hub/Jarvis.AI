import json
import logging
import re
import threading
import time
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import speech_recognition as sr

try:
    import sounddevice as sd
except Exception:
    sd = None

from ..branding import APP_LOGGER_NAME, APP_USER_AGENT
from ..audio_runtime import audio_rms_int16
from ..commands import detect_wake_word, normalize_text, strip_wake_word
from ..state import CONFIG_MGR
from ..theme import Theme
from ..utils import short_exc
from ..voice_profiles import apply_device_listening_tuning, get_capture_timing, profile_values, resolved_device_profile_kind

logger = logging.getLogger(APP_LOGGER_NAME)


class VoicePipelineMixin:
    def _cfg(self):
        return getattr(self, "config_mgr", CONFIG_MGR)

    def _listening_profile_values(self, profile_name: str):
        return profile_values(profile_name)

    def _listening_device_name(self) -> str:
        try:
            return str(self.get_selected_microphone_name() or "").strip()
        except Exception:
            return ""

    def _should_use_wake_word_boost(self) -> bool:
        cfg = self._cfg()
        return bool(cfg.get_active_listening_enabled() and cfg.get_wake_word_boost_enabled())

    def _device_profile_mode(self) -> str:
        cfg = self._cfg()
        return str(cfg.get_device_profile_mode() or "auto").strip().lower()

    def _compose_listening_values(self, profile_name: str = "", passive_mode: bool = False):
        cfg = self._cfg()
        values = self._listening_profile_values(profile_name or cfg.get_listening_profile())
        values = apply_device_listening_tuning(
            values,
            self._listening_device_name(),
            passive_mode=passive_mode and self._should_use_wake_word_boost(),
            device_kind_override=self._device_profile_mode(),
        )
        resolved_kind = resolved_device_profile_kind(self._listening_device_name(), self._device_profile_mode())
        if cfg.get_noise_suppression_enabled():
            values["energy_threshold"] = int(max(180, float(values.get("energy_threshold", 1200)) * 0.90))
            values["dynamic_energy_ratio"] = max(1.0, float(values.get("dynamic_energy_ratio", 1.5)) - 0.08)
        if cfg.get_vad_enabled():
            values["phrase_threshold"] = max(0.04, float(values.get("phrase_threshold", 0.12)) - 0.02)
            values["non_speaking_duration"] = max(0.08, float(values.get("non_speaking_duration", 0.20)) - 0.02)
        if resolved_kind == "headset" and passive_mode:
            values["energy_threshold"] = int(max(120, float(values.get("energy_threshold", 900)) * 0.72))
            values["phrase_threshold"] = max(0.02, float(values.get("phrase_threshold", 0.10)) - 0.02)
        elif resolved_kind == "usb_mic" and passive_mode:
            values["energy_threshold"] = int(max(120, float(values.get("energy_threshold", 900)) * 0.76))
            values["phrase_threshold"] = max(0.02, float(values.get("phrase_threshold", 0.10)) - 0.02)
        if self.proxy_detected:
            values = self.apply_vpn_adaptation(values)
            logger.info("Applied VPN/proxy adaptation to speech recognition profile.")
        return values

    def _apply_listening_values(self, values: Dict[str, Any]):
        self.recognizer.energy_threshold = int(values["energy_threshold"])
        self.recognizer.pause_threshold = float(values["pause_threshold"])
        self.recognizer.phrase_threshold = float(values["phrase_threshold"])
        self.recognizer.non_speaking_duration = float(values["non_speaking_duration"])
        self.recognizer.dynamic_energy_adjustment_damping = float(values["dynamic_energy_adjustment_damping"])
        self.recognizer.dynamic_energy_ratio = float(values["dynamic_energy_ratio"])

    def _clamp_energy_after_adjust(self, passive_mode: bool = False):
        base_values = self._compose_listening_values(self._cfg().get_listening_profile(), passive_mode=passive_mode)
        current_energy = int(float(getattr(self.recognizer, "energy_threshold", base_values["energy_threshold"]) or base_values["energy_threshold"]))
        max_energy = int(float(base_values["energy_threshold"]) * (1.24 if passive_mode else 1.38))
        min_energy = int(max(220, float(base_values["energy_threshold"]) * 0.60))
        self.recognizer.energy_threshold = max(min_energy, min(max_energy, current_energy))

    def apply_vpn_adaptation(self, values: Dict[str, Any]):
        adjusted = dict(values or {})
        adjusted["energy_threshold"] = int(float(adjusted.get("energy_threshold", 1700)) * 1.15)
        adjusted["pause_threshold"] = min(0.56, float(adjusted.get("pause_threshold", 0.25)) + 0.1)
        adjusted["non_speaking_duration"] = min(0.48, float(adjusted.get("non_speaking_duration", 0.18)) + 0.07)
        adjusted["dynamic_energy_adjustment_damping"] = min(0.18, float(adjusted.get("dynamic_energy_adjustment_damping", 0.08)) + 0.03)
        adjusted["dynamic_energy_ratio"] = min(2.2, float(adjusted.get("dynamic_energy_ratio", 1.6)) + 0.2)
        return adjusted

    def apply_listening_profile(self, profile_name: str = ""):
        cfg = self._cfg()
        profile_name = (profile_name or cfg.get_listening_profile() or "normal").strip().lower()
        values = self._compose_listening_values(profile_name, passive_mode=self._should_use_wake_word_boost())
        self._apply_listening_values(values)
        cfg.set_listening_profile(profile_name)

    def _capture_params_for_listening(self, manual_mode: bool):
        profile = (self._cfg().get_listening_profile() or "normal").strip().lower()
        timeout, phrase_time_limit = get_capture_timing(profile, manual_mode=manual_mode)
        device_kind = resolved_device_profile_kind(self._listening_device_name(), self._device_profile_mode())
        if device_kind in {"headset", "usb_mic"}:
            timeout = max(0.72, timeout - 0.08)
            phrase_time_limit = min(6.6, phrase_time_limit + 0.35)
        if self.proxy_detected:
            timeout = min(1.10, timeout + 0.12)
        return timeout, phrase_time_limit

    def _is_manual_listen_active(self, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.monotonic()
        with self._mic_state_lock:
            return bool(
                self._mic_manual_request
                or self._mic_manual_active
                or self.listening_once
                or (self.manual_listen_until > 0 and now < self.manual_listen_until)
            )

    def _manual_listen_deadline(self) -> float:
        with self._mic_state_lock:
            return float(self.manual_listen_until or 0.0)

    def _clear_manual_listen_state(self):
        with self._mic_state_lock:
            self._mic_manual_request = False
            self._mic_manual_active = False
            self.listening_once = False
            self.manual_listen_until = 0.0

    def _audio_signal_stats(self, audio) -> Tuple[bytes, int, float]:
        raw = b""
        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2) if audio else b""
        except Exception:
            raw = b""
        rms = audio_rms_int16(raw)
        duration = len(raw) / 32000.0 if raw else 0.0
        return raw, rms, duration

    def _audio_is_too_weak_for_stt(self, audio, manual_mode: bool = False) -> bool:
        _raw, rms, duration = self._audio_signal_stats(audio)
        threshold = int(float(getattr(self.recognizer, "energy_threshold", 1200) or 1200))
        min_rms = max(18, min(96, int(float(threshold) * 0.024)))
        if self._cfg().get_noise_suppression_enabled():
            min_rms = max(12, min_rms - 4)
        if manual_mode:
            min_rms = max(10, min_rms - 8)
            min_duration = 0.16
        else:
            if self._should_use_wake_word_boost():
                min_rms = max(7, min_rms - 12)
                min_duration = 0.09
            else:
                min_rms = max(12, min_rms - 6)
                min_duration = 0.12
        if self._cfg().get_vad_enabled():
            min_duration = max(0.08, min_duration - 0.03)
        return duration < min_duration or rms < min_rms

    def _complete_manual_listen_with_status(self, text: str, tone: str = "warn", duration_ms: int = 2400):
        self._finish_manual_listen(restore_status=False)
        if self.running:
            self.set_status_temp(text, tone, duration_ms=duration_ms)

    def _transcribe_with_groq(self, audio) -> str:
        api_key = str(self._cfg().get_api_key() or "").strip()
        if not api_key:
            raise sr.RequestError("Ключ Groq API не задан.")

        wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2) if audio else b""
        if not wav_data:
            raise sr.UnknownValueError()

        boundary = f"----JarvisBoundary{int(time.time() * 1000):x}{threading.get_ident():x}"
        fields = (
            ("model", "whisper-large-v3-turbo"),
            ("language", "ru"),
            ("temperature", "0"),
            ("response_format", "json"),
        )
        body = bytearray()
        for name, value in fields:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n')
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(wav_data)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        req = Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": APP_USER_AGENT,
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=10.0) as resp:
                raw_response = resp.read().decode("utf-8", "replace")
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")
            except Exception:
                detail = str(e)
            detail = re.sub(r"\s+", " ", detail).strip()
            match = re.search(r'"message"\s*:\s*"([^"]+)"', detail)
            human_detail = match.group(1).strip() if match else detail[:180]
            raise sr.RequestError(f"Groq STT HTTP {e.code}: {human_detail}") from e
        except URLError as e:
            raise sr.RequestError(f"Groq STT network error: {short_exc(e)}") from e
        except Exception as e:
            raise sr.RequestError(f"Groq STT error: {short_exc(e)}") from e

        try:
            payload = json.loads(raw_response)
            text = str(payload.get("text", "") or "").strip()
        except Exception:
            text = raw_response.strip()

        if not text:
            raise sr.UnknownValueError()
        return text

    def _begin_manual_listen(self, seconds: float = 5.0):
        with self._mic_state_lock:
            if self._mic_manual_active or self._mic_manual_request:
                return
            self._mic_manual_request = True
            self._mic_manual_active = True
            self.listening_once = True
            self.manual_listen_until = time.monotonic() + max(2.5, float(seconds))
        self.set_status("Слушаю...", "busy")

    def _finish_manual_listen(self, restore_status: bool = True):
        with self._mic_state_lock:
            self._mic_manual_request = False
            self._mic_manual_active = False
            self.listening_once = False
            self.manual_listen_until = 0.0
            self._mic_click_cooldown_until = time.monotonic() + 0.5
        if restore_status and self.running:
            try:
                self.root.after(0, lambda: self.set_status("Готов", "ok"))
            except Exception:
                pass

    def mic_pulse_tick(self):
        try:
            active = self._is_manual_listen_active()
            if active:
                self.mic_pulse_state = not self.mic_pulse_state
                self.mic_btn.config(bg="#16a34a" if self.mic_pulse_state else "#15803d", fg=Theme.FG)
                self.refresh_mic_status_label("слушаю")
            else:
                self.mic_btn.config(bg=Theme.ACCENT, fg=Theme.FG)
                self.refresh_mic_status_label()
        except Exception as e:
            logger.warning(f"mic_pulse_tick error: {e}")
        self.root.after(260, self.mic_pulse_tick)

    def mic_click(self, e=None):
        if self._startup_gate_setup and not bool(str(self._cfg().get_api_key() or "").strip()):
            self.set_status("Нужна активация", "warn")
            try:
                self.root.after(0, lambda: self.run_setup_wizard(True))
            except Exception:
                pass
            return
        now = time.monotonic()
        if self.processing_command or self._is_manual_listen_active(now) or now < self._mic_click_cooldown_until:
            return
        self.stop_speaking()
        self._begin_manual_listen(5.5)

    def _recognize_audio_text(self, audio, manual_mode: bool = False) -> str:
        if self._audio_is_too_weak_for_stt(audio, manual_mode=manual_mode):
            raise sr.UnknownValueError()

        last_exc = None
        if str(self._cfg().get_api_key() or "").strip():
            try:
                text = self._transcribe_with_groq(audio).strip()
                if text:
                    return text
            except sr.UnknownValueError as e:
                last_exc = e
            except sr.RequestError as e:
                last_exc = e
                logger.warning(f"Groq STT transient issue: {e}")
            except Exception as e:
                last_exc = e
                logger.warning(f"Groq STT unexpected issue: {e}")

        langs = ("ru-RU", "ru-RU,en-US", "en-US")
        for lang in langs:
            try:
                text = self.recognizer.recognize_google(audio, language=lang).strip()
                if text:
                    return text
            except sr.UnknownValueError as e:
                last_exc = e
                continue
            except sr.RequestError:
                raise
            except Exception as e:
                last_exc = e
                continue
        if last_exc:
            raise last_exc
        raise sr.UnknownValueError()

    def listen_task(self):
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
                    if current_device_index is not None:
                        mic = sr.Microphone(device_index=current_device_index)
                    else:
                        mic = sr.Microphone()
                    mic_source = mic.__enter__()
                    if mic_source is None:
                        raise RuntimeError("Microphone context initialization failed.")
                    if not getattr(mic_source, "stream", None):
                        raise RuntimeError("Microphone stream is not initialized.")
                    passive_mode = self._should_use_wake_word_boost()
                    self._apply_listening_values(self._compose_listening_values(self._cfg().get_listening_profile(), passive_mode=passive_mode))
                    self.recognizer.adjust_for_ambient_noise(mic_source, duration=0.42 if passive_mode else 0.60)
                    self._clamp_energy_after_adjust(passive_mode=passive_mode)
                    last_passive_mode = passive_mode
                    last_ambient_adjust = time.monotonic()
                    self.root.after(0, lambda n=current_device_name: self.refresh_mic_status_label("готов"))

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
                        text = self._recognize_audio_text(audio, manual_mode=manual_mode)
                    except sr.WaitTimeoutError:
                        if manual_mode and manual_deadline > 0 and time.monotonic() >= manual_deadline:
                            self._complete_manual_listen_with_status("Не слышу голос. Попробуйте еще раз.", "warn", duration_ms=2400)
                        continue
                    except sr.UnknownValueError:
                        if manual_mode:
                            if manual_deadline > 0 and time.monotonic() < manual_deadline:
                                continue
                            self._complete_manual_listen_with_status("Не разобрал команду. Повторите еще раз.", "warn", duration_ms=2400)
                        continue
                    except sr.RequestError as e:
                        err = str(e).lower()
                        if "timed out" in err or "timeout" in err or "connection failed" in err:
                            self._log_listen_transient_issue(e)
                        else:
                            logger.error(f"Speech API error: {e}")
                        if manual_mode:
                            self._complete_manual_listen_with_status("Распознавание речи недоступно. Проверьте интернет и Groq API ключ.", "warn", duration_ms=3400)
                        time.sleep(0.35)
                        continue
                    except Exception as e:
                        err = str(e).lower()
                        transient_markers = (
                            "10054",
                            "timed out",
                            "timeout",
                            "forcibly closed",
                            "connection reset",
                            "принудительно разорвано",
                        )
                        if "audio source must be entered before adjusting" in err or ("audiosource" in err and "with" in err):
                            logger.warning("STT source lost context, reopening microphone stream.")
                            break
                        if any(marker in err for marker in transient_markers):
                            self._log_listen_transient_issue(e)
                            if manual_mode:
                                self._complete_manual_listen_with_status("Потеряна связь с голосовым сервисом. Попробуйте еще раз.", "warn", duration_ms=3200)
                            time.sleep(0.35)
                            continue
                        logger.warning(f"Unexpected listen error: {e}")
                        break

                    norm = normalize_text(text)

                    if manual_mode:
                        self._finish_manual_listen()
                        self.root.after(0, lambda t=text: self.add_msg(t, "user"))
                        self.executor.submit(self.process_query, text)
                        continue

                    if not self._cfg().get_active_listening_enabled():
                        continue

                    detected, matched_word = detect_wake_word(norm)
                    if detected:
                        command_text = strip_wake_word(norm)
                        if command_text:
                            self.root.after(0, lambda t=command_text: self.add_msg(t, "user"))
                            self.executor.submit(self.process_query, command_text)
                        else:
                            self._begin_manual_listen(5.5)
                        continue

                if mic is not None:
                    try:
                        mic.__exit__(None, None, None)
                    except Exception:
                        pass
                    mic = None
                    mic_source = None

            except Exception as e:
                if not self.running:
                    break
                if "main thread is not in main loop" in str(e).lower():
                    break
                logger.error(f"STT error: {e}")
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

    def _submit_from_mic(self, text):
        if not text:
            return
        self.root.after(0, lambda t=text: self.add_msg(t, "user"))
        if hasattr(self, 'initial_push_history'):
            self.initial_push_history(text)
        self.executor.submit(self.process_query, text)


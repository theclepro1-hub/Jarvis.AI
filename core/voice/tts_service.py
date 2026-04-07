from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from core.voice.voice_models import TTSResult


@dataclass(frozen=True)
class TTSAvailability:
    key: str
    title: str
    note: str
    available: bool
    supports_output_device: bool


class TTSService:
    DEFAULT_VOICE_LABEL = "Голос по умолчанию"
    DEFAULT_OUTPUT_LABEL = "Системный вывод"
    DEFAULT_TEST_TEXT = "Я на связи."

    def __init__(self, settings_service) -> None:
        self.settings = settings_service

    def voice_response_enabled(self) -> bool:
        return bool(self.settings.get("voice_response_enabled", False))

    def tts_engine(self) -> str:
        engine = str(self.settings.get("tts_engine", "system"))
        if engine in {"system", "pyttsx3"}:
            return "system"
        if engine == "edge":
            return "edge" if self._edge_voice_ready() else "system"
        return engine

    def tts_voice_name(self) -> str:
        return str(self.settings.get("tts_voice_name", self.DEFAULT_VOICE_LABEL))

    def tts_rate(self) -> int:
        return int(self.settings.get("tts_rate", 185))

    def tts_volume(self) -> int:
        return int(self.settings.get("tts_volume", 85))

    def can_route_output(self) -> bool:
        return self.tts_engine() == "system" and self._module_available("win32com.client")

    def status_text(self) -> str:
        if not self.voice_response_enabled():
            return "голосовые ответы выключены"

        engine = self.tts_engine()
        if engine == "system":
            return "системный голос готов" if self._system_voice_available() else "системный голос недоступен"
        if engine == "edge":
            return "онлайн-голос готов" if self._edge_voice_ready() else "онлайн-голос пока не подключён"
        return "неизвестный движок голоса"

    def available_engines(self) -> list[TTSAvailability]:
        engines = [
            TTSAvailability(
                key="system",
                title="Системный голос",
                note=(
                    "Голос Windows. Может говорить в выбранные колонки, если Windows отдаёт их через SAPI."
                    if self.can_route_output()
                    else "Голос Windows. Сейчас говорит через системное устройство вывода."
                ),
                available=self._system_voice_available(),
                supports_output_device=self.can_route_output(),
            ),
        ]
        if self._edge_voice_ready():
            engines.append(
                TTSAvailability(
                    key="edge",
                    title="Онлайн-голос",
                    note="Онлайн-голос готов.",
                    available=True,
                    supports_output_device=False,
                )
            )
        return engines

    def available_voices(self) -> list[str]:
        if self.tts_engine() not in {"system", "pyttsx3"} or not self._system_voice_available():
            return [self.DEFAULT_VOICE_LABEL]

        sapi_voices = self._sapi_voices()
        if sapi_voices:
            return sapi_voices

        try:
            import pyttsx3  # type: ignore[import-not-found]

            tts = pyttsx3.init()
            voices = tts.getProperty("voices") or []
            result = [str(getattr(voice, "name", "") or getattr(voice, "id", "")).strip() for voice in voices]
            result = [voice for voice in result if voice]
            tts.stop()
        except Exception:
            result = []
        return result or [self.DEFAULT_VOICE_LABEL]

    def speak(self, text: str, force: bool = False) -> TTSResult:
        clean = text.strip()
        if not clean:
            return TTSResult(
                status="empty",
                message="Нечего озвучивать.",
                engine=self.tts_engine(),
                available=False,
                supports_output_device=self.can_route_output(),
            )
        if not force and not self.voice_response_enabled():
            return TTSResult(
                status="disabled",
                message="Голосовые ответы выключены.",
                engine=self.tts_engine(),
                available=False,
                supports_output_device=self.can_route_output(),
            )

        output = self.normalize_output_selection(self.settings.get("voice_output_name", ""))
        if output and output != self.DEFAULT_OUTPUT_LABEL and not self.can_route_output():
            return TTSResult(
                status="unsupported_output",
                message="Выбор колонки сохранён, но голос пока говорит через системный вывод.",
                engine=self.tts_engine(),
                available=False,
                supports_output_device=False,
            )

        engine = self.tts_engine()
        if engine == "system":
            return self._speak_with_pyttsx3(clean)
        if engine == "edge":
            return self._speak_with_edge(clean)

        return TTSResult(
            status="unsupported",
            message="Неизвестный движок голоса.",
            engine=engine,
            available=False,
            supports_output_device=self.can_route_output(),
        )

    def test_voice(self, text: str | None = None) -> TTSResult:
        return self.speak(text or self.DEFAULT_TEST_TEXT, force=True)

    def normalize_output_selection(self, value: str) -> str:
        normalized = str(value or "").strip()
        return normalized or self.DEFAULT_OUTPUT_LABEL

    def _module_available(self, module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    def _edge_voice_ready(self) -> bool:
        return False

    def _system_voice_available(self) -> bool:
        return self._module_available("win32com.client") or self._module_available("pyttsx3")

    def _speak_with_pyttsx3(self, text: str) -> TTSResult:
        if self._module_available("win32com.client"):
            result = self._speak_with_sapi(text)
            if result.status != "failed":
                return result

        if not self._module_available("pyttsx3"):
            return TTSResult(
                status="unavailable",
                message="Системный голос не установлен. Голос JARVIS пока недоступен.",
                engine="system",
                available=False,
                supports_output_device=False,
            )

        try:
            import pyttsx3  # type: ignore[import-not-found]

            tts = pyttsx3.init()
            tts.setProperty("rate", self.tts_rate())
            tts.setProperty("volume", max(0.0, min(1.0, self.tts_volume() / 100)))
            selected_voice = self.tts_voice_name()
            if selected_voice and selected_voice != self.DEFAULT_VOICE_LABEL:
                for voice in tts.getProperty("voices") or []:
                    voice_name = str(getattr(voice, "name", "") or getattr(voice, "id", ""))
                    if selected_voice.casefold() in voice_name.casefold():
                        tts.setProperty("voice", getattr(voice, "id"))
                        break
            tts.say(text)
            tts.runAndWait()
            return TTSResult(
                status="ok",
                message="Голос JARVIS проверен.",
                engine="system",
                available=True,
                supports_output_device=self.can_route_output(),
            )
        except Exception as exc:
            return TTSResult(
                status="failed",
                message=f"Не удалось запустить голос JARVIS: {exc}",
                engine="system",
                available=False,
                supports_output_device=self.can_route_output(),
            )

    def _speak_with_sapi(self, text: str) -> TTSResult:
        try:
            import pythoncom  # type: ignore[import-not-found]
            import win32com.client  # type: ignore[import-not-found]

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                self._apply_sapi_voice(voice)
                if not self._apply_sapi_output(voice):
                    return TTSResult(
                        status="unsupported_output",
                        message="Не нашёл выбранную колонку для голоса JARVIS. Выберите системный вывод или другую колонку.",
                        engine="system",
                        available=False,
                        supports_output_device=self.can_route_output(),
                    )
                voice.Rate = self._sapi_rate()
                voice.Volume = max(0, min(100, self.tts_volume()))
                voice.Speak(text)
            finally:
                pythoncom.CoUninitialize()
            return TTSResult(
                status="ok",
                message="Голос JARVIS проверен.",
                engine="system",
                available=True,
                supports_output_device=self.can_route_output(),
            )
        except Exception as exc:
            return TTSResult(
                status="failed",
                message=f"Не удалось запустить голос JARVIS: {exc}",
                engine="system",
                available=False,
                supports_output_device=self.can_route_output(),
            )

    def _sapi_voices(self) -> list[str]:
        if not self._module_available("win32com.client"):
            return []
        try:
            import pythoncom  # type: ignore[import-not-found]
            import win32com.client  # type: ignore[import-not-found]

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voices = voice.GetVoices()
                names = [str(voices.Item(index).GetDescription()).strip() for index in range(voices.Count)]
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            return []
        return [name for name in names if name]

    def _apply_sapi_voice(self, voice) -> None:  # noqa: ANN001
        selected = self.tts_voice_name().strip()
        if not selected or selected == self.DEFAULT_VOICE_LABEL:
            return
        selected_key = selected.casefold()
        voices = voice.GetVoices()
        for index in range(voices.Count):
            token = voices.Item(index)
            description = str(token.GetDescription())
            if selected_key in description.casefold():
                voice.Voice = token
                return

    def _apply_sapi_output(self, voice) -> bool:  # noqa: ANN001
        selected = self.normalize_output_selection(self.settings.get("voice_output_name", ""))
        if not selected or selected == self.DEFAULT_OUTPUT_LABEL:
            return True
        selected_key = selected.casefold()
        outputs = voice.GetAudioOutputs()
        for index in range(outputs.Count):
            token = outputs.Item(index)
            description = str(token.GetDescription())
            if selected_key in description.casefold() or description.casefold() in selected_key:
                voice.AudioOutput = token
                return True
        return False

    def _sapi_rate(self) -> int:
        return max(-10, min(10, round((self.tts_rate() - 185) / 14)))

    def _speak_with_edge(self, _text: str) -> TTSResult:
        if not self._module_available("edge_tts"):
            return TTSResult(
                status="unavailable",
                message="Онлайн-голос не установлен. Выберите системный голос.",
                engine="edge",
                available=False,
                supports_output_device=False,
            )
        return TTSResult(
            status="unsupported",
            message="Онлайн-голос найден, но пока отключён, чтобы не обещать нерабочую озвучку.",
            engine="edge",
            available=True,
            supports_output_device=False,
        )

from __future__ import annotations


class STTService:
    def status(self) -> str:
        return "Основной STT сейчас идёт через Groq Whisper после ручной записи или after-wake capture."

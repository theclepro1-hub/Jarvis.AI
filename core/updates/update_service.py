from __future__ import annotations


class UpdateService:
    def __init__(self) -> None:
        self.current_version = "22.0.0"
        self.channel = "stable"

    def summary(self) -> str:
        channel = "стабильный" if self.channel == "stable" else self.channel
        return f"Версия {self.current_version} · канал {channel}"

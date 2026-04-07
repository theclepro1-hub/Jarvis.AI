from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_MESSAGES = [
    {
        "role": "assistant",
        "text": "Я JARVIS Unity. Новый быстрый контур уже поднят. Можете писать как человеку или запускать действия прямо отсюда.",
        "time": "00:00",
    }
]


class ChatHistoryStore:
    def __init__(self) -> None:
        data_dir = os.environ.get("JARVIS_UNITY_DATA_DIR")
        if data_dir:
            self.base_dir = Path(data_dir)
        else:
            appdata = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", Path.home()))
            self.base_dir = appdata / "JarvisAi_Unity"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.base_dir / "chat_history.json"

    def load(self) -> list[dict[str, str]]:
        if not self.history_path.exists():
            return list(DEFAULT_MESSAGES)
        with self.history_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, messages: list[dict[str, str]]) -> None:
        with self.history_path.open("w", encoding="utf-8") as handle:
            json.dump(messages[-80:], handle, ensure_ascii=False, indent=2)

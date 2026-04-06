from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QObject, Property, Signal, Slot


class ChatBridge(QObject):
    messagesChanged = Signal()
    quickActionsChanged = Signal()
    appCatalogChanged = Signal()
    queueChanged = Signal()
    thinkingChanged = Signal()
    workerReplyReady = Signal(str)

    def __init__(self, state, services, app_bridge) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self.app_bridge = app_bridge
        self._messages: list[dict[str, str]] = self._load_history()
        self._queue_items: list[str] = []
        self._quick_actions = self.services.actions.quick_actions()
        self._app_catalog = self.services.actions.app_catalog()
        self._thinking = False
        self.workerReplyReady.connect(self._append_assistant_message)

    @Property("QVariantList", notify=messagesChanged)
    def messages(self) -> list[dict[str, str]]:
        return self._messages

    @Property("QVariantList", notify=quickActionsChanged)
    def quickActions(self) -> list[dict[str, str]]:
        return self._quick_actions

    @Property("QVariantList", notify=appCatalogChanged)
    def appCatalog(self) -> list[dict[str, str]]:
        return self._app_catalog

    @Property("QVariantList", notify=queueChanged)
    def queueItems(self) -> list[str]:
        return self._queue_items

    @Property(bool, notify=thinkingChanged)
    def thinking(self) -> bool:
        return self._thinking

    @Slot(str)
    def sendMessage(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            return

        self._append_message("user", clean)
        self.state.status = "Думаю"

        route = self.services.command_router.handle(clean)
        self._queue_items = route.queue_items
        self.queueChanged.emit()

        if route.kind == "local":
            self._thinking = False
            self.thinkingChanged.emit()
            for line in route.assistant_lines:
                self._append_message("assistant", line)
            self._queue_items = []
            self.queueChanged.emit()
            self.state.status = "Готов"
            return

        self._thinking = True
        self.thinkingChanged.emit()
        thread = threading.Thread(target=self._resolve_ai_reply, args=(clean,), daemon=True)
        thread.start()

    @Slot(str)
    def triggerQuickAction(self, action_id: str) -> None:
        self.refreshCatalog()
        action = next((item for item in self._quick_actions if item["id"] == action_id), None)
        if action is None:
            return
        self.sendMessage(f"открой {action['title']}")

    @Slot(str)
    def submitTranscribedText(self, text: str) -> None:
        self.sendMessage(text)

    @Slot(str)
    def appendAssistantNote(self, text: str) -> None:
        self._append_message("assistant", text)
        self.state.status = "Готов"

    def _resolve_ai_reply(self, text: str) -> None:
        history = self._messages[:-1]
        reply = self.services.ai.generate_reply(text, history)
        self.workerReplyReady.emit(reply)

    def _append_assistant_message(self, text: str) -> None:
        self._append_message("assistant", text)
        self._queue_items = []
        self.queueChanged.emit()
        self._thinking = False
        self.thinkingChanged.emit()
        self.state.status = "Готов"

    def _append_message(self, role: str, text: str) -> None:
        self._messages = [
            *self._messages,
            {
                "role": role,
                "text": text,
                "time": self._time_string(),
            },
        ]
        self.services.chat_history.save(self._messages)
        self.messagesChanged.emit()

    def _time_string(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _load_history(self) -> list[dict[str, str]]:
        messages = self.services.chat_history.load()
        if not messages:
            messages = [
                {
                    "role": "assistant",
                    "text": "Я JARVIS Unity. Новый быстрый контур уже поднят. Можете писать как человеку или запускать действия прямо отсюда.",
                    "time": self._time_string(),
                }
            ]
        return messages

    def refreshCatalog(self) -> None:
        self._quick_actions = self.services.actions.quick_actions()
        self._app_catalog = self.services.actions.app_catalog()
        self.quickActionsChanged.emit()
        self.appCatalogChanged.emit()

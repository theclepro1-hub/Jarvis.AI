from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


class ChatBridge(QObject):
    messagesChanged = Signal()
    quickActionsChanged = Signal()
    appCatalogChanged = Signal()
    queueChanged = Signal()
    thinkingChanged = Signal()
    saveHistoryEnabledChanged = Signal()
    workerReplyReady = Signal(str)

    def __init__(self, state, services, app_bridge) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self.app_bridge = app_bridge
        self._messages: list[dict[str, Any]] = [self._welcome_message()]
        self._queue_items: list[str] = []
        self._quick_actions: list[dict[str, str]] = []
        self._app_catalog: list[dict[str, str]] = []
        self._thinking = False
        self._initial_state_hydrated = False
        self.workerReplyReady.connect(self._append_assistant_message)
        QTimer.singleShot(0, self._hydrate_initial_state)

    @Property("QVariantList", notify=messagesChanged)
    def messages(self) -> list[dict[str, Any]]:
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

    @Property(bool, notify=saveHistoryEnabledChanged)
    def saveHistoryEnabled(self) -> bool:
        settings = getattr(self.services, "settings", None)
        if settings is None or not hasattr(settings, "get"):
            return True
        return bool(settings.get("save_history_enabled", True))

    @saveHistoryEnabled.setter
    def saveHistoryEnabled(self, value: bool) -> None:
        settings = getattr(self.services, "settings", None)
        if settings is None or not hasattr(settings, "set"):
            return
        settings.set("save_history_enabled", bool(value))
        self.saveHistoryEnabledChanged.emit()

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
            if route.execution_result is None and not route.assistant_lines:
                self._queue_items = []
                self.queueChanged.emit()
                self.state.status = "Готов"
                return
            self._append_local_result(route)
            self._queue_items = []
            self.queueChanged.emit()
            self.state.status = "Готов"
            return

        self._thinking = True
        self.thinkingChanged.emit()
        ai_text = " ".join(route.commands).strip() if route.commands else clean
        thread = threading.Thread(target=self._resolve_ai_reply, args=(ai_text,), daemon=True)
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
        if self._is_system_noise(text):
            return
        self._append_message("assistant", text)
        self.state.status = "Готов"

    @Slot(str, "QVariantList")
    def appendExecutionResult(self, title: str, steps: list[dict[str, Any]]) -> None:
        self._append_message(
            "assistant",
            title,
            message_type="execution",
            title=title,
            steps=steps,
        )
        self.state.status = "Готов"

    @Slot()
    def clearHistory(self) -> None:
        if hasattr(self.services, "chat_history"):
            self.services.chat_history.clear()
        self._messages = [self._welcome_message()]
        self._initial_state_hydrated = True
        self.messagesChanged.emit()

    def _resolve_ai_reply(self, text: str) -> None:
        history = self._messages[:-1]
        reply = self.services.ai.generate_reply(text, history)
        self.workerReplyReady.emit(reply)

    def _append_assistant_message(self, text: str) -> None:
        self._append_message("assistant", text)
        self._speak_assistant_text(text)
        self._queue_items = []
        self.queueChanged.emit()
        self._thinking = False
        self.thinkingChanged.emit()
        self.state.status = "Готов"

    def _append_local_result(self, route) -> None:
        execution = getattr(route, "execution_result", None)
        if execution is not None and getattr(execution, "steps", None):
            execution_title = self._build_execution_title(route)
            execution_steps = self._build_execution_steps(route)
            self._append_message(
                "assistant",
                execution_title,
                message_type="execution",
                title=execution_title,
                steps=execution_steps,
            )
            self._speak_assistant_text(execution_title)
            return

        if len(route.commands) <= 1 and len(route.assistant_lines) <= 1:
            for line in route.assistant_lines:
                self._append_message("assistant", line)
                self._speak_assistant_text(line)
            return

        execution_title = self._build_execution_title(route)
        execution_steps = self._build_execution_steps(route)
        self._append_message(
            "assistant",
            execution_title,
            message_type="execution",
            title=execution_title,
            steps=execution_steps,
        )
        self._speak_assistant_text(execution_title)

    def _build_execution_title(self, route) -> str:
        execution = getattr(route, "execution_result", None)
        steps = list(getattr(execution, "steps", []) or []) if execution is not None else []
        actionable_steps = [step for step in steps if str(getattr(step, "kind", "")) != "unsupported"]
        if steps:
            needs_input = [step for step in steps if str(getattr(step, "status", "")) == "needs_input"]
            if len(actionable_steps) > 1:
                return f"Выполняю {len(actionable_steps)} {self._action_word(len(actionable_steps))}"
            if needs_input and not [step for step in steps if str(getattr(step, "status", "")) == "done"]:
                return "Нужно уточнение"
            if len(steps) == 1:
                title = str(getattr(steps[0], "title", "")).strip()
                if title:
                    return title

        if route.assistant_lines:
            first_line = route.assistant_lines[0].strip()
            if first_line:
                return first_line
        return f"Выполняю {max(1, len(route.commands))} действий"

    def _action_word(self, amount: int) -> str:
        if amount % 10 in {2, 3, 4} and amount % 100 not in {12, 13, 14}:
            return "действия"
        return "действий"

    def _build_execution_steps(self, route) -> list[dict[str, str]]:
        execution = getattr(route, "execution_result", None)
        if execution is not None and getattr(execution, "steps", None):
            return [
                {
                    "title": str(step.title),
                    "status": self._step_status_label(str(step.status)),
                    "detail": str(step.detail),
                }
                for step in execution.steps
            ]

        if len(route.assistant_lines) == len(route.commands) and len(route.assistant_lines) > 1:
            step_texts = route.assistant_lines
        elif route.assistant_lines:
            step_texts = route.commands or route.assistant_lines
        else:
            step_texts = route.commands

        steps: list[dict[str, str]] = []
        for text in step_texts:
            clean = str(text).strip()
            if not clean:
                continue
            steps.append({"title": clean, "status": "готово"})
        return steps

    def _step_status_label(self, status: str) -> str:
        return {
            "done": "готово",
            "failed": "ошибка",
            "sent_unverified": "отправлено",
            "needs_input": "нужно уточнение",
            "needs_ai": "нужен разбор",
            "pending": "ожидает",
        }.get(status, status or "готово")

    def _append_message(
        self,
        role: str,
        text: str,
        *,
        message_type: str = "text",
        title: str = "",
        steps: list[dict[str, Any]] | None = None,
    ) -> None:
        self._messages = [
            *self._messages,
            {
                "role": role,
                "text": text,
                "time": self._time_string(),
                "type": message_type,
                "title": title,
                "steps": steps or [],
            },
        ]
        if self._should_persist_history():
            self.services.chat_history.save(self._messages)
        self.messagesChanged.emit()

    def _time_string(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _load_history(self) -> list[dict[str, Any]]:
        if not self._should_persist_history():
            return [self._welcome_message()]
        messages = self.services.chat_history.load()
        if not messages:
            messages = [self._welcome_message()]
        return messages

    def _welcome_message(self) -> dict[str, Any]:
        return {
            "role": "assistant",
            "text": "Я JARVIS Unity. Можно писать обычным текстом или запускать действия прямо отсюда.",
            "time": self._time_string(),
            "type": "text",
            "title": "",
            "steps": [],
        }

    def _is_system_noise(self, text: str) -> bool:
        clean = str(text or "").strip().casefold()
        if not clean:
            return True
        blocked_prefixes = (
            "слово активации",
            "не расслышал команду после слова активации",
            "не удалось разобрать команду после слова активации",
            "нужен ключ groq для облачного распознавания",
            "нужен ключ groq или локальная модель",
            "не удалось открыть микрофон",
        )
        return any(clean.startswith(prefix) for prefix in blocked_prefixes)

    def _speak_assistant_text(self, text: str) -> None:
        clean = str(text or "").strip()
        if not clean or self._is_system_noise(clean):
            return
        voice = getattr(self.services, "voice", None)
        if voice is None or not voice.voice_response_enabled():
            return
        threading.Thread(target=self._speak_worker, args=(clean,), daemon=True).start()

    def _speak_worker(self, text: str) -> None:
        try:
            self.services.voice.speak(text)
        except Exception:
            # Voice output must never block or break chat delivery.
            return

    def refreshCatalog(self) -> None:
        self._quick_actions = self.services.actions.quick_actions()
        self._app_catalog = self.services.actions.app_catalog()
        self.quickActionsChanged.emit()
        self.appCatalogChanged.emit()

    def _hydrate_initial_state(self) -> None:
        if self._initial_state_hydrated:
            return
        self._initial_state_hydrated = True
        self.refreshCatalog()
        if len(self._messages) == 1 and self._messages[0].get("role") == "assistant":
            self._messages = self._load_history()
            self.messagesChanged.emit()

    def _should_persist_history(self) -> bool:
        settings = getattr(self.services, "settings", None)
        if settings is None or not hasattr(settings, "get"):
            return os.environ.get("JARVIS_UNITY_DISABLE_CHAT_HISTORY") != "1"
        if os.environ.get("JARVIS_UNITY_DISABLE_CHAT_HISTORY") == "1":
            return False
        return bool(settings.get("save_history_enabled", True))

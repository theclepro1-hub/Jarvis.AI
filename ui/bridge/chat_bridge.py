from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


class ChatBridge(QObject):
    messagesChanged = Signal()
    quickActionsChanged = Signal()
    appCatalogChanged = Signal()
    queueChanged = Signal()
    thinkingChanged = Signal()
    thinkingLabelChanged = Signal()
    lastResponseHintChanged = Signal()
    saveHistoryEnabledChanged = Signal()
    workerReplyReady = Signal(str, str, str)
    workerStatusReady = Signal(str)

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
        self._thinking_label = ""
        self._last_response_hint = ""
        self._initial_state_hydrated = False
        self._inflight_signatures: set[str] = set()
        self._recent_submissions: dict[str, float] = {}
        self._submit_lock = threading.Lock()
        self._dedupe_window_seconds = 1.0
        self._single_flight = True
        self.workerReplyReady.connect(self._append_assistant_message)
        self.workerStatusReady.connect(self._set_status_stage)
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

    @Property(str, notify=thinkingLabelChanged)
    def thinkingLabel(self) -> str:
        return self._thinking_label

    @Property(str, notify=lastResponseHintChanged)
    def lastResponseHint(self) -> str:
        return self._last_response_hint

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
        self._submit_message(text, source="ui")

    def _submit_message(self, text: str, *, source: str) -> None:
        clean = text.strip()
        if not clean:
            return
        signature = self._message_signature(clean)
        if not self._reserve_submission(signature):
            self.state.status = "Уже отправлено, жду ответ"
            return

        self._append_message("user", clean)
        self.state.status = "Разбираю запрос"

        try:
            route = self.services.command_router.handle(clean, source=source)
        except Exception as exc:  # noqa: BLE001
            self._append_message("assistant", f"Ошибка обработки команды: {type(exc).__name__}")
            self._release_submission(signature)
            self.state.status = "Готов"
            return
        self._queue_items = route.queue_items
        self.queueChanged.emit()

        if route.kind == "local" and self._should_promote_local_route_to_ai(route):
            self._start_ai_resolution(clean, signature, route=route)
            return

        if route.kind == "local":
            self.state.status = "Выполняю локально"
            self._thinking = False
            self.thinkingChanged.emit()
            self._set_status_stage("")
            self._set_last_response_hint("")
            if route.execution_result is None and not route.assistant_lines:
                self._queue_items = []
                self.queueChanged.emit()
                self.state.status = "Готов"
                self._release_submission(signature)
                return
            self._append_local_result(route)
            self._queue_items = []
            self.queueChanged.emit()
            self.state.status = "Готов"
            self._release_submission(signature)
            return

        self._start_ai_resolution(clean, signature, route=route)

    @Slot(str)
    def triggerQuickAction(self, action_id: str) -> None:
        self.refreshCatalog()
        action = next((item for item in self._quick_actions if item["id"] == action_id), None)
        if action is None:
            return
        self.sendMessage(f"открой {action['title']}")

    @Slot(str)
    def submitTranscribedText(self, text: str) -> None:
        self._submit_message(text, source="voice")

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
        with self._submit_lock:
            self._inflight_signatures.clear()
            self._recent_submissions.clear()
        self._set_status_stage("")
        self._set_last_response_hint("")
        self._initial_state_hydrated = True
        self.messagesChanged.emit()

    def _resolve_ai_reply(self, text: str, signature: str) -> None:
        self.workerStatusReady.emit("Готовлю ответ ИИ…")
        history = self._messages[:-1]
        reply_hint = ""
        try:
            ai_service = self.services.ai
            if hasattr(ai_service, "generate_reply_result"):
                result = ai_service.generate_reply_result(
                    text,
                    history,
                    status_callback=self.workerStatusReady.emit,
                )
                reply = result.text
                reply_hint = self._format_ai_response_hint(result)
            else:
                reply = ai_service.generate_reply(text, history)
        except Exception as exc:  # noqa: BLE001
            reply = f"ИИ временно недоступен: {type(exc).__name__}"
            reply_hint = ""
        self.workerReplyReady.emit(reply, signature, reply_hint)

    def _append_assistant_message(self, text: str, signature: str = "", reply_hint: str = "") -> None:
        self._append_message("assistant", text)
        self._speak_assistant_text(text)
        self._queue_items = []
        self.queueChanged.emit()
        if signature:
            self._release_submission(signature)
        self._thinking = False
        self.thinkingChanged.emit()
        self._set_status_stage("")
        self._set_last_response_hint(reply_hint)
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

    def _set_status_stage(self, text: str) -> None:
        self._thinking_label = str(text or "").strip()
        self.thinkingLabelChanged.emit()
        if self._thinking_label:
            self.state.status = self._thinking_label

    def _set_last_response_hint(self, text: str) -> None:
        self._last_response_hint = str(text or "").strip()
        self.lastResponseHintChanged.emit()

    def _start_ai_resolution(self, original_text: str, signature: str, *, route=None) -> None:  # noqa: ANN001
        self._thinking = True
        self.thinkingChanged.emit()
        self._set_last_response_hint("")
        self._set_status_stage(self._initial_ai_stage_label(route))
        ai_text = " ".join(route.commands).strip() if route is not None and route.commands else original_text
        thread = threading.Thread(target=self._resolve_ai_reply, args=(ai_text, signature), daemon=True)
        thread.start()

    def _should_promote_local_route_to_ai(self, route) -> bool:  # noqa: ANN001
        execution = getattr(route, "execution_result", None)
        if execution is None or not getattr(execution, "requires_ai", False):
            return False
        steps = list(getattr(execution, "steps", []) or [])
        if not steps:
            return True
        if any(bool(getattr(step, "supported", False)) for step in steps):
            return False
        if any(
            str(getattr(step, "status", "")) == "needs_input" or str(getattr(step, "kind", "")) == "clarify"
            for step in steps
        ):
            return False
        return True

    def _initial_ai_stage_label(self, route) -> str:  # noqa: ANN001
        settings = getattr(self.services, "settings", None)
        mode = "auto"
        provider = "auto"
        if settings is not None and hasattr(settings, "get"):
            mode = str(settings.get("ai_mode", "auto") or "auto").strip().lower()
            provider = str(settings.get("ai_provider", "auto") or "auto").strip().lower()
        if route is not None and getattr(route, "execution_result", None) is not None:
            return "Локально не хватило уверенности, подключаю ИИ…"
        if mode == "fast" or provider in {"groq", "cerebras"}:
            return "Быстрый режим: готовлю ответ…"
        if mode == "quality" or provider == "gemini":
            return "Режим качества: готовлю ответ…"
        if mode == "local":
            return "Локальный режим: готовлю ответ…"
        return "Готовлю ответ ИИ…"

    def _format_ai_response_hint(self, result) -> str:  # noqa: ANN001
        provider_label = str(getattr(result, "provider_label", "") or "").strip()
        elapsed_ms = int(getattr(result, "elapsed_ms", 0) or 0)
        mode = str(getattr(result, "mode", "") or "").strip().lower()
        if not provider_label or elapsed_ms <= 0:
            return ""
        mode_label = {
            "fast": "Быстро",
            "quality": "Качество",
            "auto": "Авто",
            "local": "Локально",
        }.get(mode, "ИИ")
        hint = f"{mode_label}: {provider_label} · {elapsed_ms / 1000.0:.1f} с"
        if bool(getattr(result, "fallback_used", False)):
            return f"{hint} (резерв)"
        return hint

    def _message_signature(self, text: str) -> str:
        return " ".join(str(text or "").strip().casefold().split())

    def _reserve_submission(self, signature: str) -> bool:
        if not signature:
            return False
        now = time.monotonic()
        with self._submit_lock:
            stale_signatures = [
                key for key, ts in self._recent_submissions.items() if now - ts > self._dedupe_window_seconds
            ]
            for key in stale_signatures:
                self._recent_submissions.pop(key, None)
            if self._single_flight and self._inflight_signatures:
                return False
            if signature in self._inflight_signatures:
                return False
            last_seen = self._recent_submissions.get(signature)
            if last_seen is not None and now - last_seen <= self._dedupe_window_seconds:
                return False
            self._inflight_signatures.add(signature)
            self._recent_submissions[signature] = now
            return True

    def _release_submission(self, signature: str) -> None:
        if not signature:
            return
        with self._submit_lock:
            self._inflight_signatures.discard(signature)
            self._recent_submissions[signature] = time.monotonic()

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

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.intent.intent_router import IntentRouter
from core.models.action_models import ExecutionPlan, ExecutionResult, ExecutionStep
from core.pc_control.service import PcControlService
from core.routing.text_rules import (
    clarification_question,
    looks_like_broken_command,
    looks_like_conversation,
    normalize_text,
    strip_leading_wake_prefix,
)


@dataclass(slots=True)
class RouteResult:
    kind: str
    commands: list[str]
    assistant_lines: list[str]
    queue_items: list[str]
    execution_result: ExecutionResult | None = None


class CommandRouter:
    def __init__(
        self,
        action_registry,
        batch_router,
        ai_service,
        pc_control: PcControlService | None = None,
        reminder_service=None,
        reminder_provider: Callable[[], object | None] | None = None,
    ) -> None:
        self.actions = action_registry
        self.batch_router = batch_router
        self.ai = ai_service
        self.reminders = reminder_service
        self.reminder_provider = reminder_provider
        self.intent_router = IntentRouter(action_registry)
        self.pc = pc_control or PcControlService(action_registry)

    def handle(self, text: str, *, source: str = "ui", telegram_chat_id: str = "") -> RouteResult:
        return self._build_route(text, source=source, telegram_chat_id=telegram_chat_id, execute=True)

    def preview(self, text: str, *, source: str = "ui", telegram_chat_id: str = "") -> RouteResult:
        return self._build_route(text, source=source, telegram_chat_id=telegram_chat_id, execute=False)

    def _build_route(self, text: str, *, source: str = "ui", telegram_chat_id: str = "", execute: bool) -> RouteResult:
        clean_text = strip_leading_wake_prefix(text)
        if not clean_text:
            return RouteResult("local" if execute else "preview", [], [], [], None)

        early_question = clarification_question(clean_text) if looks_like_broken_command(clean_text) else ""
        if early_question:
            return self._clarification_route(clean_text, early_question, execute=execute)

        reminder_result = (
            self._handle_reminder(clean_text, source=source, telegram_chat_id=telegram_chat_id)
            if execute
            else self._preview_reminder(clean_text, source=source, telegram_chat_id=telegram_chat_id)
        )
        if reminder_result is not None:
            return reminder_result

        commands = self.batch_router.split(clean_text)
        queue_items = list(commands)
        execution_steps: list[ExecutionStep] = []
        unsupported: list[str] = []

        for command in commands:
            plan = self.intent_router.build(command)
            if plan is None:
                unsupported.append(command)
                continue

            if plan.question:
                execution_steps.append(
                    ExecutionStep(
                        id=self._step_id(command, "clarify"),
                        kind="clarify",
                        title=plan.question,
                        detail=plan.question,
                        status="needs_input",
                        supported=False,
                    )
                )
                continue

            if execute:
                execution_steps.extend(self._execute_plan(plan))
            else:
                execution_steps.extend(self._preview_plan(plan))

        if not execution_steps and not unsupported:
            return RouteResult("ai" if execute else "preview", commands, [], queue_items)

        if unsupported and not execution_steps and self._should_fallback_to_ai(commands):
            return RouteResult("ai", [clean_text], [], [clean_text])

        if unsupported:
            for unsupported_command in unsupported:
                clarification = clarification_question(unsupported_command) if looks_like_broken_command(unsupported_command) else ""
                if clarification:
                    execution_steps.append(
                        ExecutionStep(
                            id=self._step_id(unsupported_command, "clarify"),
                            kind="clarify",
                            title=clarification,
                            detail=clarification,
                            status="needs_input",
                            supported=False,
                        )
                    )
                    continue
                execution_steps.append(
                    ExecutionStep(
                        id=self._step_id(unsupported_command, "unsupported"),
                        kind="unsupported",
                        title=f"Не понял: {unsupported_command}",
                        detail="Нужен AI-разбор или уточнение.",
                        status="needs_ai",
                        supported=False,
                    )
                )

        summary = self._render_summary(execution_steps, preview=not execute)
        result = ExecutionResult(
            kind="local" if execute else "preview",
            commands=commands,
            steps=execution_steps,
            assistant_lines=[summary] if summary else [],
            queue_items=queue_items,
            requires_ai=bool(unsupported),
        )
        return RouteResult("local" if execute else "preview", commands, result.assistant_lines, queue_items, result)

    def _clarification_route(self, command: str, question: str, *, execute: bool) -> RouteResult:
        step = ExecutionStep(
            id=self._step_id(command, "clarify"),
            kind="clarify",
            title=question,
            detail=question,
            status="needs_input",
            supported=False,
        )
        result = ExecutionResult(
            kind="local" if execute else "preview",
            commands=[command],
            steps=[step],
            assistant_lines=[question],
            queue_items=[command],
            question=question,
        )
        return RouteResult("local" if execute else "preview", [command], result.assistant_lines, [command], result)

    def _should_fallback_to_ai(self, commands: list[str]) -> bool:
        normalized = [normalize_text(command) for command in commands if normalize_text(command)]
        if not normalized:
            return False
        if any(looks_like_broken_command(command) for command in normalized):
            return False
        return all(looks_like_conversation(command) for command in normalized)

    def _handle_reminder(self, text: str, *, source: str = "ui", telegram_chat_id: str = "") -> RouteResult | None:
        clean = text.strip()
        if not clean.casefold().startswith("напомни"):
            return None

        reminders = self._reminder_service()
        if reminders is None:
            step = ExecutionStep(
                id=self._step_id(clean, "reminder_unavailable"),
                kind="reminder",
                title="Напоминания пока недоступны.",
                detail="Сервис напоминаний не подключён.",
                status="failed",
            )
            result = ExecutionResult("local", [clean], [step], [step.title], [clean])
            return RouteResult("local", [clean], result.assistant_lines, [clean], result)

        created = reminders.create_from_text(clean, source=source, telegram_chat_id=telegram_chat_id)
        if created.ok:
            title = created.message or "Напоминание создано."
            step = ExecutionStep(
                id=self._step_id(clean, "reminder"),
                kind="reminder",
                title=title,
                detail=title,
                status="done",
                payload={"reminder_id": created.record.id if created.record else ""},
            )
            result = ExecutionResult("local", [clean], [step], [title], [clean])
            return RouteResult("local", [clean], result.assistant_lines, [clean], result)

        title = "Не понял время напоминания."
        if created.error == "missing_text":
            title = "Что напомнить?"
        elif created.error == "bad_unit":
            title = "Не понял единицу времени для напоминания."
        step = ExecutionStep(
            id=self._step_id(clean, "reminder_parse_failed"),
            kind="reminder",
            title=title,
            detail=created.error,
            status="needs_input",
            supported=False,
        )
        result = ExecutionResult("local", [clean], [step], [title], [clean], question=title)
        return RouteResult("local", [clean], result.assistant_lines, [clean], result)

    def _preview_reminder(self, text: str, *, source: str = "ui", telegram_chat_id: str = "") -> RouteResult | None:
        clean = text.strip()
        if not clean.casefold().startswith("напомни"):
            return None

        reminders = self._reminder_service()
        if reminders is None:
            step = ExecutionStep(
                id=self._step_id(clean, "reminder_unavailable"),
                kind="reminder",
                title="Напоминания пока недоступны.",
                detail="Сервис напоминаний не подключён.",
                status="failed",
            )
            result = ExecutionResult("preview", [clean], [step], [step.title], [clean])
            return RouteResult("preview", [clean], result.assistant_lines, [clean], result)

        parsed = reminders.preview(clean)
        if parsed.ok and parsed.intent is not None:
            title = reminders.confirmation_message(parsed.intent)
            step = ExecutionStep(
                id=self._step_id(clean, "reminder"),
                kind="reminder",
                title=title,
                detail=title,
                status="pending",
                payload={"preview": True, "source": source, "telegram_chat_id": telegram_chat_id},
            )
            result = ExecutionResult("preview", [clean], [step], [title], [clean])
            return RouteResult("preview", [clean], result.assistant_lines, [clean], result)

        title = "Не понял время напоминания."
        if parsed.error == "missing_text":
            title = "Что напомнить?"
        elif parsed.error == "bad_unit":
            title = "Не понял единицу времени для напоминания."
        step = ExecutionStep(
            id=self._step_id(clean, "reminder_parse_failed"),
            kind="reminder",
            title=title,
            detail=parsed.error,
            status="needs_input",
            supported=False,
        )
        result = ExecutionResult("preview", [clean], [step], [title], [clean], question=title)
        return RouteResult("preview", [clean], result.assistant_lines, [clean], result)

    def _execute_plan(self, plan: ExecutionPlan) -> list[ExecutionStep]:
        step = plan.steps[0]
        if step.kind == "open_items":
            items = step.payload.get("items", [])
            outcomes = self.pc.open_items(items)
            return [outcome.to_step(self._step_id(step.id, index), step.kind, step.payload) for index, outcome in enumerate(outcomes)]
        if step.kind == "open_url":
            return [self.pc.open_url(str(step.payload.get("url", "")), str(step.payload.get("title", step.title))).to_step(step.id, step.kind, step.payload)]
        if step.kind == "search_web":
            return [self.pc.search_web(str(step.payload.get("query", ""))).to_step(step.id, step.kind, step.payload)]
        if step.kind == "media_play_pause":
            return [self.pc.play_pause().to_step(step.id, step.kind, step.payload)]
        if step.kind == "media_next":
            return [self.pc.next_track().to_step(step.id, step.kind, step.payload)]
        if step.kind == "media_previous":
            return [self.pc.previous_track().to_step(step.id, step.kind, step.payload)]
        if step.kind == "media_mute":
            return [self.pc.volume_mute().to_step(step.id, step.kind, step.payload)]
        if step.kind == "volume_up":
            return [self.pc.volume_up().to_step(step.id, step.kind, step.payload)]
        if step.kind == "volume_down":
            return [self.pc.volume_down().to_step(step.id, step.kind, step.payload)]
        return [step]

    def _preview_plan(self, plan: ExecutionPlan) -> list[ExecutionStep]:
        step = plan.steps[0]
        if step.kind == "open_items":
            items = step.payload.get("items", [])
            preview_steps: list[ExecutionStep] = []
            for index, item in enumerate(items):
                title = f"Открою {item.get('title', step.title)}"
                preview_steps.append(
                    ExecutionStep(
                        id=self._step_id(step.id, index),
                        kind=step.kind,
                        title=title,
                        detail=str(item.get("target", "")),
                        status="pending",
                        supported=True,
                        payload=step.payload,
                    )
                )
            return preview_steps
        if step.kind == "open_url":
            return [
                ExecutionStep(
                    id=step.id,
                    kind=step.kind,
                    title=step.title,
                    detail=step.detail,
                    status="pending",
                    supported=True,
                    payload=step.payload,
                )
            ]
        if step.kind == "search_web":
            return [
                ExecutionStep(
                    id=step.id,
                    kind=step.kind,
                    title=step.title,
                    detail=step.detail,
                    status="pending",
                    supported=True,
                    payload=step.payload,
                )
            ]
        if step.kind in {"media_play_pause", "media_next", "media_previous", "media_mute", "volume_up", "volume_down"}:
            return [
                ExecutionStep(
                    id=step.id,
                    kind=step.kind,
                    title=step.title,
                    detail=step.detail,
                    status="pending",
                    supported=True,
                    payload=step.payload,
                )
            ]
        return [
            ExecutionStep(
                id=step.id,
                kind=step.kind,
                title=step.title,
                detail=step.detail,
                status="pending",
                supported=True,
                payload=step.payload,
            )
        ]

    def _render_summary(self, steps: list[ExecutionStep], *, preview: bool = False) -> str:
        executable = [step for step in steps if step.supported and step.kind not in {"clarify", "unsupported"}]
        actionable = [step for step in executable if step.status in {"done", "sent_unverified"}]
        previewable = [step for step in executable if step.status == "pending"]
        failed = [step for step in steps if step.supported and step.status == "failed"]
        questions = [step for step in steps if step.kind == "clarify"]
        needs_input = [step for step in steps if step.status == "needs_input" and step.kind != "clarify"]
        unsupported = [step for step in steps if step.kind == "unsupported"]

        if questions and not (actionable or previewable):
            return questions[0].title
        if needs_input and not (actionable or previewable):
            return needs_input[0].title

        if preview:
            if len(executable) > 1:
                titles = ", ".join(self._clean_title(step.title) for step in executable)
                summary = f"Выполню {len(executable)} {self._action_word(len(executable))}: {titles}"
            elif len(executable) == 1:
                summary = executable[0].title
            elif unsupported:
                summary = f"Не понял: {', '.join(self._clean_title(step.title) for step in unsupported)}"
            else:
                summary = "Не удалось понять команду."
        else:
            if len(executable) > 1:
                titles = ", ".join(self._clean_title(step.title) for step in executable)
                summary = f"Выполняю {len(executable)} {self._action_word(len(executable))}: {titles}"
            elif len(actionable) == 1:
                summary = actionable[0].title
            elif len(executable) == 1 and failed:
                summary = executable[0].title
            else:
                summary = "Не удалось выполнить команду."

        failed_titles = [self._clean_title(step.title) for step in failed]
        if failed and summary not in {step.title for step in failed} and self._clean_title(summary) not in failed_titles:
            summary = f"{summary} | Не удалось: {', '.join(self._clean_title(step.title) for step in failed)}"
        if unsupported and not preview:
            note = ", ".join(self._clean_title(step.title) for step in unsupported)
            summary = f"{summary} | Не понял: {note}"
        if unsupported and preview and len(executable) > 0:
            note = ", ".join(self._clean_title(step.title) for step in unsupported)
            summary = f"{summary} | Не понял: {note}"
        return summary

    def _action_word(self, amount: int) -> str:
        if amount % 10 in {2, 3, 4} and amount % 100 not in {12, 13, 14}:
            return "действия"
        return "действий"

    def _clean_title(self, title: str) -> str:
        for prefix in ("Не удалось: ", "Открываю ", "Ищу в интернете: ", "Открою "):
            if title.startswith(prefix):
                return title.removeprefix(prefix)
        return title

    def _step_id(self, text: str, suffix: str | int) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in text.casefold()).strip("_")
        return f"{safe[:36] or 'command'}:{suffix}"

    def _reminder_service(self):
        if self.reminders is None and self.reminder_provider is not None:
            self.reminders = self.reminder_provider()
        return self.reminders

from __future__ import annotations

from dataclasses import dataclass

from core.intent.intent_router import IntentRouter
from core.models.action_models import ExecutionPlan, ExecutionResult, ExecutionStep
from core.pc_control.service import PcControlService


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
    ) -> None:
        self.actions = action_registry
        self.batch_router = batch_router
        self.ai = ai_service
        self.reminders = reminder_service
        self.intent_router = IntentRouter(action_registry)
        self.pc = pc_control or PcControlService(action_registry)

    def handle(self, text: str) -> RouteResult:
        reminder_result = self._handle_reminder(text)
        if reminder_result is not None:
            return reminder_result

        commands = self.batch_router.split(text)
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

            execution_steps.extend(self._execute_plan(plan))

        if execution_steps:
            if unsupported:
                for unsupported_command in unsupported:
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
            summary = self._render_summary(execution_steps)
            result = ExecutionResult(
                kind="local",
                commands=commands,
                steps=execution_steps,
                assistant_lines=[summary] if summary else [],
                queue_items=queue_items,
                requires_ai=bool(unsupported),
            )
            return RouteResult("local", commands, result.assistant_lines, queue_items, result)

        if unsupported:
            return RouteResult("ai", commands, [], queue_items)

        return RouteResult("ai", commands, [], queue_items)

    def _handle_reminder(self, text: str) -> RouteResult | None:
        clean = text.strip()
        if not clean.casefold().startswith("напомни"):
            return None

        if self.reminders is None:
            step = ExecutionStep(
                id=self._step_id(clean, "reminder_unavailable"),
                kind="reminder",
                title="Напоминания пока недоступны.",
                detail="Сервис напоминаний не подключён.",
                status="failed",
            )
            result = ExecutionResult("local", [clean], [step], [step.title], [clean])
            return RouteResult("local", [clean], result.assistant_lines, [clean], result)

        created = self.reminders.create_from_text(clean)
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

    def _render_summary(self, steps: list[ExecutionStep]) -> str:
        executable = [step for step in steps if step.supported and step.kind not in {"clarify", "unsupported"}]
        actionable = [step for step in executable if step.status in {"done", "sent_unverified"}]
        failed = [step for step in steps if step.supported and step.status == "failed"]
        questions = [step for step in steps if step.kind == "clarify"]
        needs_input = [step for step in steps if step.status == "needs_input" and step.kind != "clarify"]
        unsupported = [step for step in steps if step.kind == "unsupported"]

        if questions and not actionable:
            return questions[0].title
        if needs_input and not actionable:
            return needs_input[0].title

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
        if unsupported:
            note = ", ".join(self._clean_title(step.title) for step in unsupported)
            summary = f"{summary} | Не понял: {note}"
        return summary

    def _action_word(self, amount: int) -> str:
        if amount % 10 in {2, 3, 4} and amount % 100 not in {12, 13, 14}:
            return "действия"
        return "действий"

    def _clean_title(self, title: str) -> str:
        for prefix in ("Не удалось: ", "Открываю ", "Ищу в интернете: "):
            if title.startswith(prefix):
                return title.removeprefix(prefix)
        return title

    def _step_id(self, text: str, suffix: str | int) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in text.casefold()).strip("_")
        return f"{safe[:36] or 'command'}:{suffix}"

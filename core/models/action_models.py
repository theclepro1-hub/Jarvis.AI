from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ActionOutcome:
    success: bool
    title: str
    detail: str
    status: str = ""

    def to_step(
        self,
        step_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> ExecutionStep:
        return ExecutionStep(
            id=step_id,
            kind=kind,
            title=self.title,
            detail=self.detail,
            status=self.status or ("done" if self.success else "failed"),
            supported=True,
            payload=payload or {},
        )


@dataclass(slots=True)
class ExecutionStep:
    id: str
    kind: str
    title: str
    detail: str = ""
    status: str = "pending"
    supported: bool = True
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionPlan:
    command: str
    steps: list[ExecutionStep] = field(default_factory=list)
    question: str = ""
    requires_ai: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.steps and not self.question


@dataclass(slots=True)
class ExecutionResult:
    kind: str
    commands: list[str]
    steps: list[ExecutionStep]
    assistant_lines: list[str]
    queue_items: list[str] = field(default_factory=list)
    question: str = ""
    requires_ai: bool = False

    @property
    def success(self) -> bool:
        supported_steps = [step for step in self.steps if step.supported]
        return bool(supported_steps) and all(step.status == "done" for step in supported_steps)

from __future__ import annotations

from core.intent.intent_router import IntentRouter


class _Actions:
    def resolve_open_command(self, _command: str):  # noqa: ANN001, ANN202
        return [], ""

    def find_items(self, _command: str):  # noqa: ANN001, ANN202
        return []


def test_intent_router_requires_confirmation_for_shutdown() -> None:
    router = IntentRouter(_Actions())

    plan = router.build("выключи компьютер")

    assert plan is not None
    assert plan.question == "Подтвердите выключение: скажите «выключи компьютер подтверждаю»."
    assert plan.steps == []


def test_intent_router_executes_shutdown_when_confirmed() -> None:
    router = IntentRouter(_Actions())

    plan = router.build("выключи компьютер подтверждаю")

    assert plan is not None
    assert plan.question == ""
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.kind == "power_action"
    assert step.payload["action"] == "shutdown"


def test_intent_router_allows_lock_without_extra_confirmation() -> None:
    router = IntentRouter(_Actions())

    plan = router.build("заблокируй экран")

    assert plan is not None
    assert plan.question == ""
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "power_action"
    assert plan.steps[0].payload["action"] == "lock"

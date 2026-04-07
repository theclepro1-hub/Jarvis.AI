from __future__ import annotations

from core.models.action_models import ActionOutcome


def test_action_outcome_converts_to_execution_step():
    outcome = ActionOutcome(True, "Открываю YouTube", "Запущено: YouTube")

    step = outcome.to_step("step-1", "open_items", {"id": "youtube"})

    assert step.id == "step-1"
    assert step.kind == "open_items"
    assert step.status == "done"
    assert step.supported is True
    assert step.payload == {"id": "youtube"}

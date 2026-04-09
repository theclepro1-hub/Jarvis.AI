from __future__ import annotations

from core.intent.intent_router import IntentRouter


class _Actions:
    def resolve_open_command(self, command: str):  # noqa: ANN001, ANN202
        lower = command.casefold()
        if "\u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440" in lower:
            return [
                {
                    "id": "system_settings",
                    "title": "\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b Windows",
                    "kind": "uri",
                    "target": "ms-settings:",
                }
            ], ""
        if "\u0434\u0438\u0441\u043f\u0435\u0442\u0447\u0435\u0440 \u0437\u0430\u0434\u0430\u0447" in lower:
            return [
                {
                    "id": "system_task_manager",
                    "title": "\u0414\u0438\u0441\u043f\u0435\u0442\u0447\u0435\u0440 \u0437\u0430\u0434\u0430\u0447",
                    "kind": "uri",
                    "target": "taskmgr.exe",
                }
            ], ""
        if "\u043f\u0440\u043e\u0432\u043e\u0434\u043d\u0438\u043a" in lower:
            return [
                {
                    "id": "system_explorer",
                    "title": "\u041f\u0440\u043e\u0432\u043e\u0434\u043d\u0438\u043a",
                    "kind": "uri",
                    "target": "explorer.exe",
                }
            ], ""
        return [], ""

    def find_items(self, _command: str):  # noqa: ANN001, ANN202
        return []


def test_intent_router_requires_confirmation_for_shutdown() -> None:
    router = IntentRouter(_Actions())

    plan = router.build("\u0432\u044b\u043a\u043b\u044e\u0447\u0438 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440")

    assert plan is not None
    assert plan.question == "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435: \u0441\u043a\u0430\u0436\u0438\u0442\u0435 \u00ab\u0432\u044b\u043a\u043b\u044e\u0447\u0438 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u044e\u00bb."
    assert plan.steps == []


def test_intent_router_executes_shutdown_when_confirmed() -> None:
    router = IntentRouter(_Actions())

    plan = router.build("\u0432\u044b\u043a\u043b\u044e\u0447\u0438 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u044e")

    assert plan is not None
    assert plan.question == ""
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.kind == "power_action"
    assert step.payload["action"] == "shutdown"


def test_intent_router_allows_lock_without_extra_confirmation() -> None:
    router = IntentRouter(_Actions())

    plan = router.build("\u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u0443\u0439 \u044d\u043a\u0440\u0430\u043d")

    assert plan is not None
    assert plan.question == ""
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "power_action"
    assert plan.steps[0].payload["action"] == "lock"


def test_intent_router_opens_builtin_windows_targets_without_question() -> None:
    router = IntentRouter(_Actions())

    settings_plan = router.build("\u043e\u0442\u043a\u0440\u043e\u0439 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b")
    task_manager_plan = router.build("\u043e\u0442\u043a\u0440\u043e\u0439 \u0434\u0438\u0441\u043f\u0435\u0442\u0447\u0435\u0440 \u0437\u0430\u0434\u0430\u0447")
    explorer_plan = router.build("\u043e\u0442\u043a\u0440\u043e\u0439 \u043f\u0440\u043e\u0432\u043e\u0434\u043d\u0438\u043a")

    assert settings_plan is not None
    assert settings_plan.question == ""
    assert len(settings_plan.steps) == 1
    assert settings_plan.steps[0].kind == "open_items"

    assert task_manager_plan is not None
    assert task_manager_plan.question == ""
    assert len(task_manager_plan.steps) == 1
    assert task_manager_plan.steps[0].kind == "open_items"

    assert explorer_plan is not None
    assert explorer_plan.question == ""
    assert len(explorer_plan.steps) == 1
    assert explorer_plan.steps[0].kind == "open_items"

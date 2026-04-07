from __future__ import annotations

from core.models.action_models import ActionOutcome
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter


class FakeActions:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def find_items(self, text: str):
        items = []
        if "ютуб" in text or "youtube" in text:
            items.append({"id": "youtube", "title": "YouTube"})
        if "музык" in text:
            items.append({"id": "music", "title": "Музыка"})
        return items

    def open_items(self, items):
        outcomes = []
        for item in items:
            self.opened.append(item["id"])
            outcomes.append(ActionOutcome(True, f"Открываю {item['title']}", ""))
        return outcomes

    def volume_up(self) -> ActionOutcome:
        return ActionOutcome(True, "Прибавляю громкость", "")

    def volume_down(self) -> ActionOutcome:
        return ActionOutcome(True, "Убавляю громкость", "")

    def volume_mute(self) -> ActionOutcome:
        return ActionOutcome(True, "Переключаю звук", "")


class FakeAi:
    pass


def make_router() -> tuple[CommandRouter, FakeActions]:
    actions = FakeActions()
    router = CommandRouter(actions, BatchRouter(actions), FakeAi())
    return router, actions


def test_command_router_runs_open_chain_without_ai():
    router, actions = make_router()

    result = router.handle("открой ютуб и музыку")

    assert result.kind == "local"
    assert result.commands == ["открой ютуб", "открой музыку"]
    assert actions.opened == ["youtube", "music"]


def test_command_router_runs_open_then_volume_chain_without_ai():
    router, actions = make_router()

    result = router.handle("запусти музыку и прибавь")

    assert result.kind == "local"
    assert result.commands == ["запусти музыку", "прибавь"]
    assert actions.opened == ["music"]
    assert "Прибавляю громкость" in result.assistant_lines

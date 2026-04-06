from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RouteResult:
    kind: str
    commands: list[str]
    assistant_lines: list[str]
    queue_items: list[str]


class CommandRouter:
    def __init__(self, action_registry, batch_router, ai_service) -> None:
        self.actions = action_registry
        self.batch_router = batch_router
        self.ai = ai_service

    def handle(self, text: str) -> RouteResult:
        commands = self.batch_router.split(text)
        assistant_lines: list[str] = []
        queue_items = list(commands)
        local_only = True

        for command in commands:
            handled, line = self._handle_local(command)
            if handled:
                assistant_lines.append(line)
                continue
            local_only = False
            break

        if local_only and assistant_lines:
            return RouteResult("local", commands, assistant_lines, queue_items)

        return RouteResult("ai", commands, [], queue_items)

    def _handle_local(self, command: str) -> tuple[bool, str]:
        lower = command.lower()
        if any(token in lower for token in ("громче", "прибавь")):
            outcome = self.actions.volume_up()
            return True, outcome.title
        if any(token in lower for token in ("тише", "убавь")):
            outcome = self.actions.volume_down()
            return True, outcome.title
        if any(token in lower for token in ("mute", "без звука", "выключи звук")):
            outcome = self.actions.volume_mute()
            return True, outcome.title

        if lower.startswith(("открой", "открыть", "запусти", "запустить", "включи", "включить")):
            items = self.actions.find_items(lower)
            if items:
                outcomes = self.actions.open_items(items)
                line = ". ".join(outcome.title for outcome in outcomes)
                return True, line
        return False, ""

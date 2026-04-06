from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ActionOutcome:
    success: bool
    title: str
    detail: str

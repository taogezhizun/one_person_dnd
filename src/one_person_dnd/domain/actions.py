from __future__ import annotations

from dataclasses import dataclass, field

from one_person_dnd.engine.dice import DiceEvent


@dataclass(frozen=True)
class PlayerAction:
    campaign_id: int
    session_id: int
    text: str
    manual_tags: list[str] = field(default_factory=list)
    extra_context: str = ""


@dataclass(frozen=True)
class ActionAssessment:
    action_type: str
    dice_events: list[DiceEvent]
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

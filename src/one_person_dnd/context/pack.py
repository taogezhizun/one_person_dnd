from __future__ import annotations

from dataclasses import dataclass, field

from one_person_dnd.domain.actions import ActionAssessment
from one_person_dnd.engine.dice import DiceEvent


@dataclass(frozen=True)
class ContextBlock:
    kind: str
    title: str
    content: str
    source: str
    priority: int = 0
    preview_data: dict[str, object] | None = None


@dataclass(frozen=True)
class ContextPack:
    campaign_id: int
    session_id: int
    action_text: str
    blocks: list[ContextBlock] = field(default_factory=list)
    recalled_world: list[dict] = field(default_factory=list)
    recalled_context: list[dict] = field(default_factory=list)
    dice_events: list[DiceEvent] = field(default_factory=list)
    assessment: ActionAssessment | None = None

    def blocks_of_kind(self, kind: str) -> list[ContextBlock]:
        return [b for b in self.blocks if b.kind == kind]

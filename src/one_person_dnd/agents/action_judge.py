from __future__ import annotations

from one_person_dnd.domain.actions import (
    ActionAssessment,
    PlayerAction,
    action_language_flags,
    classify_action_text,
)
from one_person_dnd.engine.dice import roll_events_from_text


class ActionJudgeAgent:
    def run(self, action: PlayerAction) -> ActionAssessment:
        text = (action.text or "").strip()
        dice_events = roll_events_from_text(text, max_rolls=5)
        action_type = classify_action_text(text)
        signals, warnings = action_language_flags(
            text,
            action_type=action_type,
            has_manual_roll=bool(dice_events),
        )

        return ActionAssessment(
            action_type=action_type,
            dice_events=dice_events,
            signals=signals,
            warnings=warnings,
        )

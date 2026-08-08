from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from one_person_dnd.adjudication import AdjudicationRecord
from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.agents.continuity_critic import ContinuityCriticAgent
from one_person_dnd.agents.response_evaluator import ResponseEvaluatorAgent
from one_person_dnd.domain.actions import ActionAssessment, action_language_flags, classify_action_text
from one_person_dnd.engine.orchestrator import TurnResult
from one_person_dnd.engine.parser import DMStructuredResponse, parse_dm_text


class TurnPresenter:
    """Build the canonical browser-facing shape for stored and completed turns."""

    def __init__(
        self,
        *,
        action_judge: ActionJudgeAgent | None = None,
        continuity_critic: ContinuityCriticAgent | None = None,
        response_evaluator: ResponseEvaluatorAgent | None = None,
    ) -> None:
        self._action_judge = action_judge or ActionJudgeAgent()
        self._continuity_critic = continuity_critic or ContinuityCriticAgent()
        self._response_evaluator = response_evaluator or ResponseEvaluatorAgent()

    def present_history(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        campaign_id: int,
        session_id: int,
    ) -> list[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        for row in reversed(list(rows)):
            dm_raw = str(row.get("dm_text") or "").strip()
            dm = parse_dm_text(dm_raw)
            player_text = str(row.get("player_text") or "")
            stored_dice = self._parse_dice_events(row.get("dice_events"))
            assessment = self._stored_assessment(
                player_text,
                row.get("adjudication_json"),
                stored_dice,
            )
            turns.append(
                self._present(
                    turn_index=int(row["turn_index"]),
                    player_text=player_text,
                    dm=dm,
                    dice_events=list(assessment.dice_events) if assessment.adjudication else stored_dice,
                    action_assessment=assessment,
                    critic_warnings=list(self._continuity_critic.run(dm_raw, assessment).warnings),
                    response_warnings=list(self._response_evaluator.run(dm).warnings),
                    pending_review_delta=0,
                    created_at=str(row.get("created_at") or ""),
                )
            )
        return turns

    def present_result(self, result: TurnResult, *, player_text: str) -> dict[str, Any]:
        replayed = bool(getattr(result, "replayed", False))
        pending_review_delta = 0 if replayed else self._pending_review_delta(result.dm)
        presented = self._present(
            turn_index=result.turn_index,
            player_text=player_text,
            dm=result.dm,
            dice_events=list(result.dice_events or []),
            action_assessment=result.action_assessment,
            critic_warnings=list(result.critic_warnings or []),
            response_warnings=list(result.response_warnings or []),
            pending_review_delta=pending_review_delta,
            created_at="",
        )
        presented["replayed"] = replayed
        return presented

    def _present(
        self,
        *,
        turn_index: int,
        player_text: str,
        dm: DMStructuredResponse,
        dice_events: list[dict[str, Any]],
        action_assessment: ActionAssessment | None,
        critic_warnings: list[str],
        response_warnings: list[str],
        pending_review_delta: int,
        created_at: str,
    ) -> dict[str, Any]:
        return {
            "turn_index": turn_index,
            "player_text": player_text,
            "dm": {
                "narration": dm.narration,
                "choices": list(dm.choices),
                "dm_notes": dm.dm_notes,
                "memory_suggestions": dm.memory_suggestions,
            },
            "dice_events": dice_events,
            "action_assessment": self._serialize_action_assessment(action_assessment),
            "critic_warnings": critic_warnings,
            "response_warnings": response_warnings,
            "has_pending_review": pending_review_delta > 0,
            "pending_review_delta": pending_review_delta,
            "created_at": created_at,
        }

    @staticmethod
    def _serialize_action_assessment(assessment: ActionAssessment | None) -> dict[str, Any] | None:
        if assessment is None:
            return None
        result = {
            "action_type": assessment.action_type,
            "signals": list(assessment.signals),
            "warnings": list(assessment.warnings),
        }
        if assessment.adjudication is not None:
            result["adjudication"] = assessment.adjudication.to_dict()
        return result

    @staticmethod
    def _stored_assessment(
        player_text: str,
        adjudication_json: Any,
        stored_dice: list[dict[str, Any]],
    ) -> ActionAssessment:
        if isinstance(adjudication_json, str) and adjudication_json.strip():
            try:
                return AdjudicationRecord.from_json(adjudication_json).to_action_assessment()
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass

        action_type = classify_action_text(player_text)
        signals, warnings = action_language_flags(
            player_text,
            action_type=action_type,
            has_manual_roll=bool(stored_dice),
        )
        return ActionAssessment(
            action_type=action_type,
            dice_events=list(stored_dice),
            signals=signals,
            warnings=warnings,
        )

    @staticmethod
    def _pending_review_delta(dm: DMStructuredResponse) -> int:
        return sum(
            1
            for value in (dm.state_delta_json, dm.thread_updates_json)
            if (value or "").strip()
        )

    @staticmethod
    def _parse_dice_events(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            loaded = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(loaded, list):
            return []
        return [item for item in loaded if isinstance(item, dict)]

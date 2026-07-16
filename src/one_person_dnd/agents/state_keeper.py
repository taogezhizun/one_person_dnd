from __future__ import annotations

import sqlite3

from one_person_dnd.engine.dice import DiceEvent
from one_person_dnd.engine.orchestrator import (
    TurnResult,
    persist_raw_turn,
    persist_turn,
    persist_turn_enrichment,
)
from one_person_dnd.engine.parser import DMStructuredResponse


class StateKeeperAgent:
    def persist(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        player_text: str,
        dm_raw: str,
        dm_struct: DMStructuredResponse,
        recalled_world: list[dict],
        dice_events: list[DiceEvent],
        recalled_context: list[dict] | None = None,
    ) -> TurnResult:
        return persist_turn(
            conn,
            session_id=session_id,
            player_text=player_text,
            dm_raw=dm_raw,
            dm_struct=dm_struct,
            recalled_world=recalled_world,
            recalled_context=recalled_context,
            dice_events=dice_events,
        )

    def persist_raw(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        player_text: str,
        dm_raw: str,
        dice_events: list[DiceEvent],
    ) -> tuple[int, list[DiceEvent]]:
        """Phase 1: durably record the raw turn the player already saw. See
        engine.orchestrator.persist_raw_turn for the persistence contract."""
        return persist_raw_turn(
            conn,
            session_id=session_id,
            player_text=player_text,
            dm_raw=dm_raw,
            dice_events=dice_events,
        )

    def persist_enrichment(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        turn_index: int,
        dm_struct: DMStructuredResponse,
    ) -> None:
        """Phase 2: best-effort enrichment writes for an already-persisted raw
        turn. Caller is responsible for commit/rollback around this call."""
        persist_turn_enrichment(
            conn,
            session_id=session_id,
            turn_index=turn_index,
            dm_struct=dm_struct,
        )

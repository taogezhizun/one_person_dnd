from __future__ import annotations

import sqlite3

from one_person_dnd.engine.dice import DiceEvent
from one_person_dnd.engine.orchestrator import TurnResult, persist_turn
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

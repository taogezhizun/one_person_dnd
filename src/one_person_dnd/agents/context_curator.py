from __future__ import annotations

import sqlite3

from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.builder import build_context_pack
from one_person_dnd.context.pack import ContextPack
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction


class ContextCuratorAgent:
    def run(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        assessment: ActionAssessment,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> ContextPack:
        return build_context_pack(
            conn,
            action=action,
            assessment=assessment,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )

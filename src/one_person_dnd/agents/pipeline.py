from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace

from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.agents.context_curator import ContextCuratorAgent
from one_person_dnd.agents.continuity_critic import ContinuityCriticAgent
from one_person_dnd.agents.dungeon_master import DungeonMasterAgent
from one_person_dnd.agents.response_evaluator import ResponseEvaluatorAgent
from one_person_dnd.agents.state_keeper import StateKeeperAgent
from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.selection import select_recent_turn_messages
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction
from one_person_dnd.engine.dice import DiceEvent
from one_person_dnd.engine.orchestrator import TurnResult
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import ChatMessage

logger = logging.getLogger("one_person_dnd.agents.pipeline")


class TurnPipeline:
    def __init__(
        self,
        *,
        dm_client,
        action_judge: ActionJudgeAgent | None = None,
        context_curator: ContextCuratorAgent | None = None,
        critic: ContinuityCriticAgent | None = None,
        response_evaluator: ResponseEvaluatorAgent | None = None,
        state_keeper: StateKeeperAgent | None = None,
    ) -> None:
        self.action_judge = action_judge or ActionJudgeAgent()
        self.context_curator = context_curator or ContextCuratorAgent()
        self.dm = DungeonMasterAgent(dm_client)
        self.critic = critic or ContinuityCriticAgent()
        self.response_evaluator = response_evaluator or ResponseEvaluatorAgent()
        self.state_keeper = state_keeper or StateKeeperAgent()

    def prepare_messages(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> tuple[list[ChatMessage], list[dict], list[dict], list[DiceEvent], ActionAssessment]:
        assessment = self.action_judge.run(action)
        pack = self.context_curator.run(
            conn,
            action=action,
            assessment=assessment,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )
        recent = select_recent_turn_messages(
            conn,
            session_id=action.session_id,
            limit=memory_cfg.history_turns_for_prompt,
        )
        messages = self.dm.build_messages(pack, player_text=action.text, recent_messages=recent)
        return messages, pack.recalled_world, pack.recalled_context, pack.dice_events, assessment

    def run_non_streaming(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> TurnResult:
        messages, recalled_world, recalled_context, dice_events, action_assessment = self.prepare_messages(
            conn,
            action=action,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )
        dm_raw, _repaired = self.dm.run_non_streaming(messages, repair=True)
        critic_result = self.critic.run(dm_raw)
        response_result = self.response_evaluator.run(parse_dm_text(dm_raw))
        if self.critic.should_repair(critic_result.warnings) or self.response_evaluator.should_repair(
            response_result.warnings
        ):
            repair_warnings = list(critic_result.warnings) + list(response_result.warnings)
            logger.info(
                "playability_repair_attempt session=%s warnings=%s",
                action.session_id,
                ",".join(repair_warnings),
            )
            dm_raw = self.dm.repair_non_streaming(
                messages,
                self._build_playability_repair_prompt(
                    dm_raw,
                    critic_warnings=critic_result.warnings,
                    response_warnings=response_result.warnings,
                ),
            )
        return self.persist_dm_output(
            conn,
            action=action,
            dm_raw=dm_raw,
            recalled_world=recalled_world,
            recalled_context=recalled_context,
            dice_events=dice_events,
            action_assessment=action_assessment,
        )

    def persist_dm_output(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        dm_raw: str,
        recalled_world: list[dict],
        dice_events: list[DiceEvent],
        recalled_context: list[dict] | None = None,
        action_assessment: ActionAssessment | None = None,
    ) -> TurnResult:
        critic_result = self.critic.run(dm_raw)
        dm_struct = parse_dm_text(dm_raw)
        if "malformed_state_delta" in critic_result.warnings:
            logger.debug(
                "critic_suppressed_state_delta session=%s warnings=%s",
                action.session_id,
                ",".join(critic_result.warnings),
            )
            dm_struct = replace(dm_struct, state_delta_json="")
        response_result = self.response_evaluator.run(dm_struct)
        result = self.state_keeper.persist(
            conn,
            session_id=action.session_id,
            player_text=action.text,
            dm_raw=dm_raw,
            dm_struct=dm_struct,
            recalled_world=recalled_world,
            recalled_context=recalled_context,
            dice_events=dice_events,
        )
        conn.commit()
        return replace(
            result,
            action_assessment=action_assessment,
            critic_warnings=list(critic_result.warnings),
            response_warnings=list(response_result.warnings),
        )

    def _build_playability_repair_prompt(
        self,
        dm_raw: str,
        *,
        critic_warnings: list[str],
        response_warnings: list[str],
    ) -> str:
        if response_warnings:
            return self.response_evaluator.build_repair_prompt(
                dm_raw,
                list(critic_warnings or []) + list(response_warnings or []),
            )
        return self.critic.build_repair_prompt(dm_raw, critic_warnings)

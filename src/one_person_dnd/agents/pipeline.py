from __future__ import annotations

import logging
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, replace

from one_person_dnd.adjudication import (
    ActionAdjudicator,
    AdjudicationRecord,
    AdjudicationRequest,
    AdjudicationStoreBusy,
    AdjudicationStoreCorrupt,
)
from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.agents.context_curator import ContextCuratorAgent
from one_person_dnd.agents.continuity_critic import ContinuityCriticAgent
from one_person_dnd.agents.dungeon_master import DungeonMasterAgent
from one_person_dnd.agents.response_evaluator import ResponseEvaluatorAgent
from one_person_dnd.agents.state_keeper import StateKeeperAgent
from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.selection import select_recent_turn_messages
from one_person_dnd.db.repos import adjudication_records, turn_logs
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction
from one_person_dnd.engine.dice import DiceEvent
from one_person_dnd.engine.orchestrator import TurnResult
from one_person_dnd.engine.parser import DMStructuredResponse, parse_dm_text
from one_person_dnd.llm import ChatMessage

logger = logging.getLogger("one_person_dnd.agents.pipeline")

_GENERATION_CLAIM_MIN_LEASE_SECONDS = 300
_GENERATION_CLAIM_TIMEOUT_MULTIPLIER = 4
_GENERATION_CLAIM_OVERHEAD_SECONDS = 180
_GENERATION_CLAIM_POLL_SECONDS = 0.025
_GENERATION_CLAIM_WAIT_SECONDS = 30.0


def _generation_claim_lease_seconds(dm_client) -> int:
    try:
        timeout_seconds = float(getattr(dm_client, "request_timeout_seconds", 60.0))
    except (TypeError, ValueError):
        timeout_seconds = 60.0
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        timeout_seconds = 60.0
    return max(
        _GENERATION_CLAIM_MIN_LEASE_SECONDS,
        math.ceil(
            timeout_seconds * _GENERATION_CLAIM_TIMEOUT_MULTIPLIER
            + _GENERATION_CLAIM_OVERHEAD_SECONDS
        ),
    )


def _is_sqlite_busy_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).casefold() for marker in ("locked", "busy")
    )


@dataclass(frozen=True)
class PreparedTurn:
    action: PlayerAction
    messages: list[ChatMessage]
    recalled_world: list[dict]
    recalled_context: list[dict]
    dice_events: list[DiceEvent]
    action_assessment: ActionAssessment
    adjudication: AdjudicationRecord
    completed_result: TurnResult | None = None
    claim_token: str | None = None


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
        adjudicator: ActionAdjudicator | None = None,
    ) -> None:
        self.action_judge = action_judge or ActionJudgeAgent()
        self.context_curator = context_curator or ContextCuratorAgent()
        self.dm = DungeonMasterAgent(dm_client)
        self.critic = critic or ContinuityCriticAgent()
        self.response_evaluator = response_evaluator or ResponseEvaluatorAgent()
        self.state_keeper = state_keeper or StateKeeperAgent()
        self.adjudicator = adjudicator
        self._generation_claim_lease_seconds = _generation_claim_lease_seconds(dm_client)
        self._active_claims: dict[tuple[int, str], str] = {}

    def prepare_turn(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> PreparedTurn:
        """Freeze and commit mechanics before building any LLM request."""
        effective_action = action
        if not (action.attempt_id or "").strip():
            effective_action = replace(action, attempt_id=uuid.uuid4().hex)

        adjudicator = self.adjudicator or ActionAdjudicator(conn=conn)
        adjudication = adjudicator.adjudicate(
            AdjudicationRequest(
                attempt_id=effective_action.attempt_id,
                action=effective_action,
            )
        )
        # Replayability is provided by the durable record, not an RNG seed.
        # This commit is deliberately before context assembly or any LLM call.
        try:
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("裁决记录暂时无法提交到 SQLite") from exc
            raise
        assessment = adjudication.to_action_assessment()

        completed_row = turn_logs.get_by_attempt(
            conn,
            session_id=effective_action.session_id,
            attempt_id=adjudication.attempt_id,
        )
        if completed_row is not None:
            return PreparedTurn(
                action=effective_action,
                messages=[],
                recalled_world=[],
                recalled_context=[],
                dice_events=list(assessment.dice_events),
                action_assessment=assessment,
                adjudication=adjudication,
                completed_result=self._completed_result(completed_row, assessment),
            )

        claim_token, completed_row = self._claim_generation_or_wait(
            conn,
            session_id=effective_action.session_id,
            attempt_id=adjudication.attempt_id,
        )
        if completed_row is not None:
            return PreparedTurn(
                action=effective_action,
                messages=[],
                recalled_world=[],
                recalled_context=[],
                dice_events=list(assessment.dice_events),
                action_assessment=assessment,
                adjudication=adjudication,
                completed_result=self._completed_result(completed_row, assessment),
            )

        try:
            pack = self.context_curator.run(
                conn,
                action=effective_action,
                assessment=assessment,
                memory_cfg=memory_cfg,
                state_block=state_block,
                cheat_prompt=cheat_prompt,
            )
            recent = select_recent_turn_messages(
                conn,
                session_id=effective_action.session_id,
                limit=memory_cfg.history_turns_for_prompt,
            )
            messages = self.dm.build_messages(
                pack,
                player_text=effective_action.text,
                recent_messages=recent,
            )
        except Exception as exc:
            assert claim_token is not None
            self._release_active_claim_best_effort(
                conn,
                session_id=effective_action.session_id,
                attempt_id=adjudication.attempt_id,
                claim_token=claim_token,
            )
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("构建回合上下文时 SQLite 暂时繁忙") from exc
            raise
        return PreparedTurn(
            action=effective_action,
            messages=messages,
            recalled_world=pack.recalled_world,
            recalled_context=pack.recalled_context,
            dice_events=pack.dice_events,
            action_assessment=assessment,
            adjudication=adjudication,
            claim_token=claim_token,
        )

    def renew_generation_claim(
        self,
        conn: sqlite3.Connection,
        *,
        prepared: PreparedTurn,
    ) -> bool:
        """Extend a prepared turn's lease, for example during a long SSE stream."""
        token = prepared.claim_token
        if not token:
            return False
        try:
            renewed = adjudication_records.renew_claim(
                conn,
                session_id=prepared.action.session_id,
                attempt_id=prepared.adjudication.attempt_id,
                claim_token=token,
                lease_seconds=self._generation_claim_lease_seconds,
            )
            conn.commit()
            return renewed
        except Exception as exc:
            conn.rollback()
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("生成租约暂时无法续期") from exc
            raise

    def release_generation_claim(
        self,
        conn: sqlite3.Connection,
        *,
        prepared: PreparedTurn,
    ) -> bool:
        """Release a prepared turn after provider/stream failure so retry is immediate."""
        token = prepared.claim_token
        if not token:
            return False
        key = (prepared.action.session_id, prepared.adjudication.attempt_id)
        try:
            released = adjudication_records.release_claim(
                conn,
                session_id=key[0],
                attempt_id=key[1],
                claim_token=token,
            )
            conn.commit()
            return released
        except Exception as exc:
            conn.rollback()
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("生成租约暂时无法释放") from exc
            raise
        finally:
            if self._active_claims.get(key) == token:
                self._active_claims.pop(key, None)

    def prepare_messages(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> tuple[list[ChatMessage], list[dict], list[dict], list[DiceEvent], ActionAssessment]:
        """Compatibility projection; new callers should use prepare_turn()."""
        prepared = self.prepare_turn(
            conn,
            action=action,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )
        return (
            prepared.messages,
            prepared.recalled_world,
            prepared.recalled_context,
            prepared.dice_events,
            prepared.action_assessment,
        )

    def run_non_streaming(
        self,
        conn: sqlite3.Connection,
        *,
        action: PlayerAction,
        memory_cfg: MemoryConfig,
        state_block: str = "",
        cheat_prompt: str = "",
    ) -> TurnResult:
        prepared = self.prepare_turn(
            conn,
            action=action,
            memory_cfg=memory_cfg,
            state_block=state_block,
            cheat_prompt=cheat_prompt,
        )
        if prepared.completed_result is not None:
            return prepared.completed_result

        try:
            dm_raw, _repaired = self.dm.run_non_streaming(prepared.messages, repair=True)
            critic_result = self.critic.run(dm_raw, prepared.action_assessment)
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
                if not self.renew_generation_claim(conn, prepared=prepared):
                    raise AdjudicationStoreCorrupt("生成租约已失效，拒绝发起修复请求")
                dm_raw = self.dm.repair_non_streaming(
                    prepared.messages,
                    self._build_playability_repair_prompt(
                        dm_raw,
                        critic_warnings=critic_result.warnings,
                        response_warnings=response_result.warnings,
                        action_assessment=prepared.action_assessment,
                    ),
                )
            return self.persist_dm_output(
                conn,
                action=prepared.action,
                dm_raw=dm_raw,
                recalled_world=prepared.recalled_world,
                recalled_context=prepared.recalled_context,
                dice_events=prepared.dice_events,
                action_assessment=prepared.action_assessment,
            )
        except Exception:
            try:
                self.release_generation_claim(conn, prepared=prepared)
            except Exception:
                logger.exception(
                    "turn_generation_claim_release_failed session=%s attempt=%s",
                    prepared.action.session_id,
                    prepared.adjudication.attempt_id,
                )
            raise

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
        """
        Two-phase persistence so a player never sees a completed DM turn on
        screen that then silently vanishes after a refresh.

        Phase 1 (raw, durable): commit player_text + raw dm_text + dice_events via
        state_keeper.persist_raw(). This is the exact turn the player already saw
        streamed to them, so it must land before anything else is attempted.

        Phase 2 (enrichment, best-effort): critic/response-evaluator checks, the
        parsed choices, state-delta/thread-update review requests, story journal,
        and summary rollup. If anything here raises (sqlite lock, unexpected
        dm_struct shape, rollup error, ...), it is logged and swallowed -- the
        already-committed raw turn from phase 1 is never erased or hidden, we just
        degrade to a best-effort parsed narration with no warnings/review deltas.
        """
        adjudication = action_assessment.adjudication if action_assessment else None
        claim_key = (
            (action.session_id, adjudication.attempt_id)
            if adjudication is not None
            else None
        )
        claim_token = self._active_claims.get(claim_key) if claim_key else None
        if claim_token:
            self._renew_active_claim(
                conn,
                session_id=claim_key[0],
                attempt_id=claim_key[1],
                claim_token=claim_token,
            )
        try:
            turn_index, safe_dice_events = self.state_keeper.persist_raw(
                conn,
                session_id=action.session_id,
                player_text=action.text,
                dm_raw=dm_raw,
                dice_events=dice_events,
                attempt_id=adjudication.attempt_id if adjudication else None,
                adjudication_json=adjudication.to_json() if adjudication else None,
            )
        except Exception as exc:
            if claim_key and claim_token:
                self._release_active_claim_best_effort(
                    conn,
                    session_id=claim_key[0],
                    attempt_id=claim_key[1],
                    claim_token=claim_token,
                )
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("完成回合时 SQLite 暂时繁忙") from exc
            raise
        if claim_key:
            self._active_claims.pop(claim_key, None)

        try:
            critic_result = self.critic.run(dm_raw, action_assessment)
            dm_struct = parse_dm_text(dm_raw)
            if "malformed_state_delta" in critic_result.warnings:
                logger.debug(
                    "critic_suppressed_state_delta session=%s warnings=%s",
                    action.session_id,
                    ",".join(critic_result.warnings),
                )
                dm_struct = replace(dm_struct, state_delta_json="")
            if "malformed_thread_updates" in critic_result.warnings:
                logger.debug(
                    "critic_suppressed_thread_updates session=%s warnings=%s",
                    action.session_id,
                    ",".join(critic_result.warnings),
                )
                dm_struct = replace(dm_struct, thread_updates_json="")
            response_result = self.response_evaluator.run(dm_struct)
            self.state_keeper.persist_enrichment(
                conn,
                session_id=action.session_id,
                turn_index=turn_index,
                dm_struct=dm_struct,
            )
            conn.commit()
            critic_warnings = list(critic_result.warnings)
            response_warnings = list(response_result.warnings)
        except Exception:
            conn.rollback()
            logger.exception(
                "turn_enrichment_failed session=%s turn=%s; raw turn log already committed",
                action.session_id,
                turn_index,
            )
            try:
                dm_struct = parse_dm_text(dm_raw)
            except Exception:
                dm_struct = DMStructuredResponse(narration=dm_raw, choices=[], dm_notes="", memory_suggestions="")
            critic_warnings = []
            response_warnings = []

        return TurnResult(
            turn_index=turn_index,
            dm_raw_text=dm_raw,
            dm=dm_struct,
            recalled_world=recalled_world,
            dice_events=safe_dice_events,
            recalled_context=list(recalled_context or []),
            action_assessment=action_assessment,
            critic_warnings=critic_warnings,
            response_warnings=response_warnings,
        )

    def _claim_generation_or_wait(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        attempt_id: str,
    ) -> tuple[str | None, dict | None]:
        claim_token = uuid.uuid4().hex
        deadline = time.monotonic() + _GENERATION_CLAIM_WAIT_SECONDS
        while True:
            try:
                acquired = adjudication_records.try_claim(
                    conn,
                    session_id=session_id,
                    attempt_id=attempt_id,
                    claim_token=claim_token,
                    lease_seconds=self._generation_claim_lease_seconds,
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                if _is_sqlite_busy_error(exc):
                    raise AdjudicationStoreBusy("生成租约暂时无法获取") from exc
                raise
            if acquired:
                self._active_claims[(session_id, attempt_id)] = claim_token
                return claim_token, None

            completed_row = turn_logs.get_by_attempt(
                conn,
                session_id=session_id,
                attempt_id=attempt_id,
            )
            if completed_row is not None:
                return None, completed_row
            if adjudication_records.get_by_attempt(
                conn,
                session_id=session_id,
                attempt_id=attempt_id,
            ) is None:
                raise AdjudicationStoreCorrupt("裁决记录在等待生成时消失")
            if time.monotonic() >= deadline:
                raise AdjudicationStoreBusy("同一回合仍在生成，请稍后重试")
            time.sleep(_GENERATION_CLAIM_POLL_SECONDS)

    def _renew_active_claim(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        attempt_id: str,
        claim_token: str,
    ) -> None:
        try:
            renewed = adjudication_records.renew_claim(
                conn,
                session_id=session_id,
                attempt_id=attempt_id,
                claim_token=claim_token,
                lease_seconds=self._generation_claim_lease_seconds,
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("生成租约暂时无法续期") from exc
            raise
        if not renewed:
            raise AdjudicationStoreCorrupt("生成租约已失效，拒绝写入重复回合")

    def _release_active_claim_best_effort(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: int,
        attempt_id: str,
        claim_token: str,
    ) -> None:
        try:
            adjudication_records.release_claim(
                conn,
                session_id=session_id,
                attempt_id=attempt_id,
                claim_token=claim_token,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                "turn_generation_claim_release_failed session=%s attempt=%s",
                session_id,
                attempt_id,
            )
        finally:
            self._active_claims.pop((session_id, attempt_id), None)

    def _completed_result(self, row: dict, assessment: ActionAssessment) -> TurnResult:
        dm_raw = str(row.get("dm_text") or "")
        try:
            dm_struct = parse_dm_text(dm_raw)
        except Exception:
            dm_struct = DMStructuredResponse(
                narration=dm_raw,
                choices=[],
                dm_notes="",
                memory_suggestions="",
            )
        critic_result = self.critic.run(dm_raw, assessment)
        response_result = self.response_evaluator.run(dm_struct)
        return TurnResult(
            turn_index=int(row["turn_index"]),
            dm_raw_text=dm_raw,
            dm=dm_struct,
            recalled_world=[],
            dice_events=list(assessment.dice_events),
            recalled_context=[],
            action_assessment=assessment,
            critic_warnings=list(critic_result.warnings),
            response_warnings=list(response_result.warnings),
            replayed=True,
        )

    def _build_playability_repair_prompt(
        self,
        dm_raw: str,
        *,
        critic_warnings: list[str],
        response_warnings: list[str],
        action_assessment: ActionAssessment | None = None,
    ) -> str:
        if response_warnings:
            prompt = self.response_evaluator.build_repair_prompt(
                dm_raw,
                list(critic_warnings or []) + list(response_warnings or []),
            )
            adjudication = action_assessment.adjudication if action_assessment else None
            if adjudication is not None and adjudication.check is not None:
                check = adjudication.check
                outcome = "成功" if check.outcome == "success" else "失败"
                prompt += (
                    "\n【不可变系统结算】\n"
                    f"{check.ability}{' / ' + check.skill if check.skill else ''}，"
                    f"DC {check.dc}，总值 {check.total}，结果{outcome}。"
                    "重写时不得重掷、修改数值或叙述相反结果。\n"
                )
            return prompt
        return self.critic.build_repair_prompt(dm_raw, critic_warnings, action_assessment)

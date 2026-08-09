import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.adjudication import (
    ActionAdjudicator,
    AdjudicationStoreBusy,
    AdjudicationStoreCorrupt,
    AttemptConflict,
    SequenceRoller,
)
from one_person_dnd.agents.pipeline import TurnPipeline
from one_person_dnd.agents.state_keeper import StateKeeperAgent
from one_person_dnd.config import MemoryConfig
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import (
    adjudication_records,
    campaigns,
    character_sheets,
    sessions,
    state_change_requests,
    turn_logs,
    world_bible,
)
from one_person_dnd.db.schema import init_db
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.llm import ChatMessage


class FakeDMClient:
    def chat(self, messages: list[ChatMessage]) -> str:
        return "\n".join(
            [
                "===NARRATION===",
                "你推开门，屋内传来潮湿木头的气味。",
                "===CHOICES===",
                "- 进入房间",
                "- 退后观察",
                "===DM_NOTES===",
                "保持悬念。",
                "===MEMORY===",
                "玩家发现一扇潮湿木门。",
            ]
        )


class MalformedStateDeltaClient:
    def chat(self, messages: list[ChatMessage]) -> str:
        return "\n".join(
            [
                "===NARRATION===",
                "你被陷阱擦伤。",
                "===CHOICES===",
                "- 检查伤口",
                "- 继续前进",
                "===DM_NOTES===",
                "state delta malformed",
                "===MEMORY===",
                "陷阱擦伤了玩家。",
                "===STATE_DELTA===",
                '{"party":[{"hp":7}',
            ]
        )


class OneChoiceDMClient:
    def chat(self, messages: list[ChatMessage]) -> str:
        return "\n".join(
            [
                "===NARRATION===",
                "门后只有一条过窄的路。",
                "===CHOICES===",
                "- 继续向前",
                "===DM_NOTES===",
                "choice count warning",
                "===MEMORY===",
                "玩家发现一条过窄的路。",
            ]
        )


class RepairableOneChoiceDMClient:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        if len(self.calls) == 1:
            return "\n".join(
                [
                    "===NARRATION===",
                    "门后只有一条过窄的路。",
                    "===CHOICES===",
                    "- 继续向前",
                    "===DM_NOTES===",
                    "choice count warning",
                    "===MEMORY===",
                    "玩家发现一条过窄的路。",
                ]
            )
        return "\n".join(
            [
                "===NARRATION===",
                "门后只有一条过窄的路，墙缝里吹出冰冷的风。",
                "===CHOICES===",
                "- 侧身继续向前",
                "- 停下检查墙缝",
                "- 返回门厅寻找其他入口",
                "===DM_NOTES===",
                "critic repair kept the same situation.",
                "===MEMORY===",
                "玩家发现一条过窄、带冷风的路。",
            ]
        )


class RepairableBadChoicesDMClient:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        if len(self.calls) == 1:
            return "\n".join(
                [
                    "===NARRATION===",
                    "守卫握紧钥匙，等待你的下一步。",
                    "===CHOICES===",
                    "- 继续",
                    "- 继续",
                    "- 成功说服守卫交出钥匙",
                    "===DM_NOTES===",
                    "bad next actions",
                    "===MEMORY===",
                    "玩家正在和守卫交涉。",
                ]
            )
        return "\n".join(
            [
                "===NARRATION===",
                "守卫把钥匙往身后藏了藏，目光仍然警惕。",
                "===CHOICES===",
                "- 询问钥匙对应哪一扇门",
                "- 观察守卫腰间是否还有备用钥匙",
                "- 后退一步，寻找绕开守卫的路线",
                "===DM_NOTES===",
                "response evaluator repair kept agency with the player.",
                "===MEMORY===",
                "玩家尝试从守卫处获得钥匙线索。",
            ]
        )


class FailingDMClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[ChatMessage]) -> str:
        self.calls += 1
        raise RuntimeError("simulated provider failure")


class UnexpectedDMClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[ChatMessage]) -> str:
        self.calls += 1
        raise AssertionError("completed attempts must not call the LLM again")


class BarrierDMClient:
    """Hold the first provider call open so a duplicate request can race it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.first_call_barrier = threading.Barrier(2)
        self.second_call_started = threading.Event()
        self.release = threading.Event()

    def chat(self, messages: list[ChatMessage]) -> str:
        with self._lock:
            self.calls += 1
            call_number = self.calls
        if call_number == 1:
            self.first_call_barrier.wait(timeout=2)
        else:
            self.second_call_started.set()
        if not self.release.wait(timeout=3):
            raise AssertionError("test did not release the provider call")
        return "\n".join(
            [
                "===NARRATION===",
                "锁舌弹开，门后露出一条向下的石阶。",
                "===CHOICES===",
                "- 沿石阶向下",
                "- 检查门锁结构",
                "- 退回门厅",
                "===DM_NOTES===",
                "并发请求只应生成一次。",
                "===MEMORY===",
                "玩家打开了通往地下的门。",
            ]
        )


class TestTurnPipeline(unittest.TestCase):
    def _conn(self) -> tuple[tempfile.TemporaryDirectory, sqlite3.Connection, int, int]:
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        campaign_id = campaigns.create_campaign(conn, "测试战役")
        session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
        conn.commit()
        return tmp, conn, campaign_id, session_id

    def test_non_streaming_pipeline_persists_turn(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我推开门",
                manual_tags=[],
                extra_context="",
            )
            result = TurnPipeline(dm_client=FakeDMClient()).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            self.assertEqual(result.turn_index, 0)
            self.assertEqual(result.dm.choices, ["进入房间", "退后观察"])
            self.assertEqual(result.recalled_world, [])
            self.assertTrue(result.recalled_context)
            self.assertEqual(result.response_warnings, [])
            row = conn.execute("SELECT COUNT(*) AS c FROM turn_logs WHERE session_id = ?", (session_id,)).fetchone()
            self.assertEqual(int(row["c"]), 1)
        finally:
            conn.close()
            tmp.cleanup()

    def test_non_streaming_result_includes_action_assessment_for_ui(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我成功说服守卫交出钥匙",
                manual_tags=[],
                extra_context="",
            )

            result = TurnPipeline(dm_client=FakeDMClient()).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            self.assertIsNotNone(result.action_assessment)
            self.assertEqual(result.action_assessment.action_type, "social")
            self.assertIn("declared_success", result.action_assessment.warnings)
            self.assertIn("dm_should_adjudicate_outcome", result.action_assessment.signals)
        finally:
            conn.close()
            tmp.cleanup()

    def test_prepare_messages_returns_context_preview_and_dice_events(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=campaign_id,
                type="Location",
                title="门厅",
                content="潮湿木门通向旧储藏室。",
                tags="门厅,木门",
            )
            conn.commit()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我调查木门并掷 1d20+2",
                manual_tags=["木门"],
                extra_context="",
            )

            messages, recalled_world, recalled_context, dice_events, assessment = TurnPipeline(
                dm_client=FakeDMClient()
            ).prepare_messages(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            self.assertGreaterEqual(len(messages), 3)
            self.assertEqual(recalled_world[0]["title"], "门厅")
            self.assertTrue(any(item["kind"] == "world_bible" for item in recalled_context))
            self.assertTrue(any(item["kind"] == "action_assessment" for item in recalled_context))
            self.assertEqual(len(dice_events), 1)
            self.assertEqual(assessment.action_type, "exploration")
        finally:
            conn.close()
            tmp.cleanup()

    def test_adjudication_is_committed_before_llm_and_linked_with_turn(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"level":1,"abilities":{"DEX":14},"skill_proficiencies":[]}]}',
            )
            conn.commit()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我尝试开锁",
                attempt_id="committed-before-llm",
            )

            class InspectingDMClient(FakeDMClient):
                def __init__(self, db_path: Path) -> None:
                    self.db_path = db_path
                    self.saw_record = False
                    self.saw_turn = False

                def chat(self, messages: list[ChatMessage]) -> str:
                    probe = get_connection(self.db_path)
                    try:
                        self.saw_record = adjudication_records.get_by_attempt(
                            probe,
                            session_id=session_id,
                            attempt_id=action.attempt_id,
                        ) is not None
                        self.saw_turn = turn_logs.get_by_attempt(
                            probe,
                            session_id=session_id,
                            attempt_id=action.attempt_id,
                        ) is not None
                    finally:
                        probe.close()
                    return super().chat(messages)

            client = InspectingDMClient(Path(tmp.name) / "test.sqlite3")
            result = TurnPipeline(
                dm_client=client,
                adjudicator=ActionAdjudicator(conn=conn, roller=SequenceRoller([13])),
            ).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())

            self.assertTrue(client.saw_record)
            self.assertFalse(client.saw_turn)
            linked = adjudication_records.get_by_attempt(
                conn,
                session_id=session_id,
                attempt_id=action.attempt_id,
            )
            self.assertEqual(linked["turn_index"], result.turn_index)
            stored_turn = turn_logs.get_by_attempt(
                conn,
                session_id=session_id,
                attempt_id=action.attempt_id,
            )
            self.assertIsNotNone(stored_turn)
            self.assertIn('"outcome":"success"', stored_turn["adjudication_json"])
        finally:
            conn.close()
            tmp.cleanup()

    def test_provider_failure_retry_reuses_frozen_roll(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"level":1,"abilities":{"DEX":10}}]}',
            )
            conn.commit()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我尝试开锁",
                attempt_id="retry-after-provider-error",
            )
            first_roller = SequenceRoller([7])
            with self.assertRaisesRegex(RuntimeError, "provider failure"):
                TurnPipeline(
                    dm_client=FailingDMClient(),
                    adjudicator=ActionAdjudicator(conn=conn, roller=first_roller),
                ).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())

            second_roller = SequenceRoller([20])
            result = TurnPipeline(
                dm_client=FakeDMClient(),
                adjudicator=ActionAdjudicator(conn=conn, roller=second_roller),
            ).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())

            self.assertEqual(first_roller.calls, 1)
            self.assertEqual(second_roller.calls, 0)
            self.assertEqual(result.action_assessment.adjudication.check.selected_d20, 7)
            self.assertEqual(len(turn_logs.list_all_for_session(conn, session_id=session_id)), 1)
        finally:
            conn.close()
            tmp.cleanup()

    def test_completed_attempt_replays_without_llm_or_duplicate_turn(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我尝试说服守卫",
                attempt_id="already-completed",
            )
            first = TurnPipeline(
                dm_client=FakeDMClient(),
                adjudicator=ActionAdjudicator(conn=conn, roller=SequenceRoller([16])),
            ).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())

            unexpected = UnexpectedDMClient()
            replay = TurnPipeline(
                dm_client=unexpected,
                adjudicator=ActionAdjudicator(conn=conn, roller=SequenceRoller([1])),
            ).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())

            self.assertEqual(unexpected.calls, 0)
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.turn_index, first.turn_index)
            self.assertEqual(replay.dm_raw_text, first.dm_raw_text)
            self.assertEqual(len(turn_logs.list_all_for_session(conn, session_id=session_id)), 1)
        finally:
            conn.close()
            tmp.cleanup()

    def test_concurrent_same_attempt_calls_llm_once_and_replays_to_loser(self) -> None:
        tmp, first_conn, campaign_id, session_id = self._conn()
        second_conn = get_connection(Path(tmp.name) / "test.sqlite3")
        client = BarrierDMClient()
        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text="我尝试开锁",
            attempt_id="concurrent-same-attempt",
        )

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(
                    TurnPipeline(dm_client=client).run_non_streaming,
                    first_conn,
                    action=action,
                    memory_cfg=MemoryConfig(),
                )
                client.first_call_barrier.wait(timeout=2)
                second_future = executor.submit(
                    TurnPipeline(dm_client=client).run_non_streaming,
                    second_conn,
                    action=action,
                    memory_cfg=MemoryConfig(),
                )

                duplicate_reached_provider = client.second_call_started.wait(timeout=0.3)
                client.release.set()
                outcomes: list[object] = []
                errors: list[BaseException] = []
                for future in (first_future, second_future):
                    try:
                        outcomes.append(future.result(timeout=3))
                    except BaseException as exc:  # asserted below for a clearer RED failure
                        errors.append(exc)

            self.assertFalse(duplicate_reached_provider)
            self.assertEqual(errors, [])
            self.assertEqual(client.calls, 1)
            self.assertEqual(len(outcomes), 2)
            first_result, second_result = outcomes
            self.assertEqual(first_result.turn_index, second_result.turn_index)
            self.assertEqual(first_result.dm_raw_text, second_result.dm_raw_text)
            self.assertEqual(sum(result.replayed for result in outcomes), 1)
            self.assertEqual(
                len(turn_logs.list_all_for_session(first_conn, session_id=session_id)),
                1,
            )
            ledger = adjudication_records.get_by_attempt(
                first_conn,
                session_id=session_id,
                attempt_id=action.attempt_id,
            )
            self.assertIsNone(ledger["claim_token"])
            self.assertIsNone(ledger["claim_expires_at"])
        finally:
            client.release.set()
            second_conn.close()
            first_conn.close()
            tmp.cleanup()

    def test_prepared_turn_claim_supports_sse_renew_release_and_bounded_wait(self) -> None:
        tmp, first_conn, campaign_id, session_id = self._conn()
        second_conn = get_connection(Path(tmp.name) / "test.sqlite3")
        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text="我尝试开锁",
            attempt_id="stream-claim",
        )
        owner = TurnPipeline(dm_client=FakeDMClient())
        try:
            prepared = owner.prepare_turn(
                first_conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )
            self.assertIsNotNone(prepared.claim_token)
            self.assertTrue(
                owner.renew_generation_claim(first_conn, prepared=prepared)
            )

            contender_client = UnexpectedDMClient()
            with patch(
                "one_person_dnd.agents.pipeline._GENERATION_CLAIM_WAIT_SECONDS",
                0,
            ):
                with self.assertRaises(AdjudicationStoreBusy):
                    TurnPipeline(dm_client=contender_client).run_non_streaming(
                        second_conn,
                        action=action,
                        memory_cfg=MemoryConfig(),
                    )
            self.assertEqual(contender_client.calls, 0)

            self.assertTrue(
                owner.release_generation_claim(first_conn, prepared=prepared)
            )
            stored = adjudication_records.get_by_attempt(
                first_conn,
                session_id=session_id,
                attempt_id=action.attempt_id,
            )
            self.assertIsNone(stored["claim_token"])
            self.assertIsNone(stored["claim_expires_at"])
        finally:
            second_conn.close()
            first_conn.close()
            tmp.cleanup()

    def test_generation_claim_lease_covers_configured_provider_timeout(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()

        class LongTimeoutClient(FakeDMClient):
            request_timeout_seconds = 600.0

        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text="我尝试开锁",
            attempt_id="long-provider-timeout",
        )
        pipeline = TurnPipeline(dm_client=LongTimeoutClient())
        try:
            prepared = pipeline.prepare_turn(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )
            row = conn.execute(
                """
                SELECT claim_expires_at - unixepoch() AS lease_remaining
                FROM adjudication_records
                WHERE session_id = ? AND attempt_id = ?
                """,
                (session_id, action.attempt_id),
            ).fetchone()

            self.assertGreaterEqual(int(row["lease_remaining"]), 2400)
            pipeline.release_generation_claim(conn, prepared=prepared)
        finally:
            conn.close()
            tmp.cleanup()

    def test_sqlite_lock_while_claiming_is_a_typed_busy_error_before_llm(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        client = UnexpectedDMClient()
        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text="我尝试开锁",
            attempt_id="locked-generation-claim",
        )
        try:
            with (
                patch(
                    "one_person_dnd.agents.pipeline.adjudication_records.try_claim",
                    side_effect=sqlite3.OperationalError("database is locked"),
                ),
                self.assertRaises(AdjudicationStoreBusy),
            ):
                TurnPipeline(dm_client=client).run_non_streaming(
                    conn,
                    action=action,
                    memory_cfg=MemoryConfig(),
                )

            self.assertEqual(client.calls, 0)
        finally:
            conn.close()
            tmp.cleanup()

    def test_context_failure_releases_generation_claim_for_immediate_retry(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text="我尝试开锁",
            attempt_id="context-failure",
        )

        class FailingContextCurator:
            def run(self, *args, **kwargs):
                raise RuntimeError("simulated context failure")

        try:
            with self.assertRaisesRegex(RuntimeError, "context failure"):
                TurnPipeline(
                    dm_client=UnexpectedDMClient(),
                    context_curator=FailingContextCurator(),
                ).run_non_streaming(conn, action=action, memory_cfg=MemoryConfig())

            stored = adjudication_records.get_by_attempt(
                conn,
                session_id=session_id,
                attempt_id=action.attempt_id,
            )
            self.assertIsNone(stored["claim_token"])
            result = TurnPipeline(dm_client=FakeDMClient()).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )
            self.assertEqual(result.turn_index, 0)
        finally:
            conn.close()
            tmp.cleanup()

    def test_attempt_id_reuse_with_changed_action_fails_before_llm(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            original = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我尝试开锁",
                attempt_id="conflicting-attempt",
            )
            first_pipeline = TurnPipeline(
                dm_client=FailingDMClient(),
                adjudicator=ActionAdjudicator(conn=conn, roller=SequenceRoller([10])),
            )
            with self.assertRaises(RuntimeError):
                first_pipeline.run_non_streaming(conn, action=original, memory_cfg=MemoryConfig())

            changed = replace(original, text="我尝试说服守卫")
            unexpected = UnexpectedDMClient()
            with self.assertRaises(AttemptConflict):
                TurnPipeline(dm_client=unexpected).run_non_streaming(
                    conn,
                    action=changed,
                    memory_cfg=MemoryConfig(),
                )
            self.assertEqual(unexpected.calls, 0)
        finally:
            conn.close()
            tmp.cleanup()

    def test_malformed_state_delta_is_not_enqueued_for_player_review(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我继续前进",
                manual_tags=[],
                extra_context="",
            )

            result = TurnPipeline(dm_client=MalformedStateDeltaClient()).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            pending = state_change_requests.list_pending(conn, session_id=session_id)
            self.assertEqual(result.turn_index, 0)
            self.assertEqual(pending, [])
        finally:
            conn.close()
            tmp.cleanup()

    def test_non_streaming_result_includes_critic_warnings_for_ui(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我继续向前",
                manual_tags=[],
                extra_context="",
            )

            result = TurnPipeline(dm_client=OneChoiceDMClient()).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            self.assertIn("choice_count_out_of_range", result.critic_warnings)
        finally:
            conn.close()
            tmp.cleanup()

    def test_non_streaming_repairs_unplayable_dm_response_once_before_persisting(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            client = RepairableOneChoiceDMClient()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我继续向前",
                manual_tags=[],
                extra_context="",
            )

            result = TurnPipeline(dm_client=client).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            row = conn.execute(
                "SELECT dm_text FROM turn_logs WHERE session_id = ? AND turn_index = 0",
                (session_id,),
            ).fetchone()
            self.assertEqual(len(client.calls), 2)
            self.assertIn("choice_count_out_of_range", client.calls[1][-1].content)
            self.assertEqual(
                result.dm.choices,
                ["侧身继续向前", "停下检查墙缝", "返回门厅寻找其他入口"],
            )
            self.assertNotIn("choice_count_out_of_range", result.critic_warnings)
            self.assertIn("返回门厅寻找其他入口", row["dm_text"])
            self.assertNotIn("- 继续向前\n===DM_NOTES===", row["dm_text"])
        finally:
            conn.close()
            tmp.cleanup()

    def test_non_streaming_does_not_repair_after_losing_generation_claim(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            client = RepairableOneChoiceDMClient()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我继续向前",
                attempt_id="lost-before-repair",
            )
            pipeline = TurnPipeline(dm_client=client)

            with (
                patch.object(pipeline, "renew_generation_claim", return_value=False),
                self.assertRaises(AdjudicationStoreCorrupt),
            ):
                pipeline.run_non_streaming(
                    conn,
                    action=action,
                    memory_cfg=MemoryConfig(),
                )

            self.assertEqual(len(client.calls), 1)
            self.assertEqual(
                turn_logs.list_all_for_session(conn, session_id=session_id),
                [],
            )
        finally:
            conn.close()
            tmp.cleanup()

    def test_non_streaming_repairs_bad_next_action_choices_once_before_persisting(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            client = RepairableBadChoicesDMClient()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我试着和守卫谈谈钥匙",
                manual_tags=[],
                extra_context="",
            )

            result = TurnPipeline(dm_client=client).run_non_streaming(
                conn,
                action=action,
                memory_cfg=MemoryConfig(),
            )

            row = conn.execute(
                "SELECT dm_text FROM turn_logs WHERE session_id = ? AND turn_index = 0",
                (session_id,),
            ).fetchone()
            self.assertEqual(len(client.calls), 2)
            self.assertIn("duplicate_choices", client.calls[1][-1].content)
            self.assertIn("non_actionable_choice", client.calls[1][-1].content)
            self.assertIn("choice_declares_outcome", client.calls[1][-1].content)
            self.assertEqual(
                result.dm.choices,
                ["询问钥匙对应哪一扇门", "观察守卫腰间是否还有备用钥匙", "后退一步，寻找绕开守卫的路线"],
            )
            self.assertEqual(result.response_warnings, [])
            self.assertIn("观察守卫腰间是否还有备用钥匙", row["dm_text"])
            self.assertNotIn("- 继续\n- 继续", row["dm_text"])
        finally:
            conn.close()
            tmp.cleanup()


class FailingEnrichmentStateKeeper(StateKeeperAgent):
    """Simulates a phase-2 failure (e.g. sqlite lock, rollup bug) after the raw
    turn has already been committed by phase 1."""

    def persist_enrichment(self, conn, *, session_id, turn_index, dm_struct):
        raise RuntimeError("simulated enrichment failure")


class TestTurnPipelineRawPersistenceRobustness(unittest.TestCase):
    """
    Guards the streaming-turn invariant: once the DM narration has been streamed
    to the player, the raw turn (player_text + raw dm_text + dice_events) must be
    durably recorded even if enrichment (parsed choices, state-delta/thread-update
    review requests, story journal, rollup) subsequently raises. A refresh must
    never show fewer turns than the player already saw on screen.
    """

    def _conn(self) -> tuple[tempfile.TemporaryDirectory, sqlite3.Connection, int, int]:
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        campaign_id = campaigns.create_campaign(conn, "测试战役")
        session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
        conn.commit()
        return tmp, conn, campaign_id, session_id

    def test_raw_turn_is_committed_even_when_enrichment_raises(self) -> None:
        tmp, conn, campaign_id, session_id = self._conn()
        try:
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我推开门",
                manual_tags=[],
                extra_context="",
            )
            dm_raw = FakeDMClient().chat([])
            pipeline = TurnPipeline(dm_client=FakeDMClient(), state_keeper=FailingEnrichmentStateKeeper())

            result = pipeline.persist_dm_output(
                conn,
                action=action,
                dm_raw=dm_raw,
                recalled_world=[],
                dice_events=[],
            )

            # The raw turn (what the player already saw streamed) must be durably
            # persisted even though phase-2 enrichment raised.
            row = conn.execute(
                "SELECT player_text, dm_text FROM turn_logs WHERE session_id = ? AND turn_index = ?",
                (session_id, result.turn_index),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["player_text"], "我推开门")
            self.assertEqual(row["dm_text"], dm_raw)

            # No pending review requests were queued since enrichment never ran.
            pending = state_change_requests.list_pending(conn, session_id=session_id)
            self.assertEqual(pending, [])

            # The pipeline degrades gracefully rather than propagating the failure:
            # a best-effort parsed narration with no critic/response warnings.
            self.assertEqual(result.critic_warnings, [])
            self.assertEqual(result.response_warnings, [])
            self.assertEqual(result.dm.narration, "你推开门，屋内传来潮湿木头的气味。")
        finally:
            conn.close()
            tmp.cleanup()

    def test_raw_turn_rolls_back_when_attempt_cannot_be_linked(self) -> None:
        tmp, conn, _campaign_id, session_id = self._conn()
        try:
            with self.assertRaisesRegex(RuntimeError, "could not be bound"):
                StateKeeperAgent().persist_raw(
                    conn,
                    session_id=session_id,
                    player_text="我尝试开锁",
                    dm_raw="不会被提交",
                    dice_events=[],
                    attempt_id="missing-ledger-attempt",
                    adjudication_json="{}",
                )

            count = conn.execute(
                "SELECT COUNT(*) FROM turn_logs WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn.close()
            tmp.cleanup()

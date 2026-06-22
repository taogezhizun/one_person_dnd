import sqlite3
import tempfile
import unittest
from pathlib import Path

from one_person_dnd.agents.pipeline import TurnPipeline
from one_person_dnd.config import MemoryConfig
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, sessions, state_change_requests, world_bible
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

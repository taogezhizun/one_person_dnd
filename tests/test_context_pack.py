import sqlite3
import tempfile
import unittest
from pathlib import Path

from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.adjudication import ActionAdjudicator, AdjudicationRequest, SequenceRoller
from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.builder import build_context_pack
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, plot_threads, sessions, story_journal, world_bible
from one_person_dnd.db.schema import init_db
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.engine.prompt_builder import build_dm_messages_from_context_pack


class TestContextPack(unittest.TestCase):
    def _conn(self) -> tuple[tempfile.TemporaryDirectory, sqlite3.Connection]:
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.sqlite3"
        init_db(db_path)
        return tmp, get_connection(db_path)

    def test_builds_context_pack_with_world_and_scene(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="乌鸦酒馆",
            )
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=campaign_id,
                type="Location",
                title="乌鸦酒馆",
                content="港口区的旧酒馆，老板知道走私线索。",
                tags="酒馆,港口区",
            )
            conn.commit()

            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我在酒馆观察可疑的人",
                manual_tags=["酒馆"],
                extra_context="我保持低调。",
            )
            assessment = ActionJudgeAgent().run(action)
            pack = build_context_pack(conn, action=action, assessment=assessment, memory_cfg=MemoryConfig())

            kinds = [b.kind for b in pack.blocks]
            self.assertIn("world_bible", kinds)
            self.assertIn("scene_state", kinds)
            self.assertIn("action_assessment", kinds)
            self.assertEqual(pack.recalled_world[0]["title"], "乌鸦酒馆")
            self.assertEqual(pack.action_text, action.text)
        finally:
            conn.close()
            tmp.cleanup()

    def test_builds_context_pack_with_authoritative_character_sheet(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="门厅",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"name":"艾拉","race":"人类","class":"游侠","hp":8,"max_hp":12,"gold":15,"inventory":["短弓"]}]}',
            )
            conn.commit()

            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我查看门后的动静",
                manual_tags=[],
                extra_context="",
            )
            assessment = ActionJudgeAgent().run(action)
            pack = build_context_pack(conn, action=action, assessment=assessment, memory_cfg=MemoryConfig())
            character_blocks = [b for b in pack.blocks if b.kind == "character_state"]

            self.assertTrue(character_blocks)
            self.assertIn("艾拉", character_blocks[0].content)
            self.assertIn("HP：8/12", character_blocks[0].content)
            self.assertIn("物品：短弓", character_blocks[0].content)
            self.assertEqual(character_blocks[0].source, "character_sheets")
        finally:
            conn.close()
            tmp.cleanup()

    def test_open_thread_context_includes_canonical_id_for_updates(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="门厅",
            )
            thread_id = plot_threads.create_thread(
                conn,
                session_id=session_id,
                title="失踪的信使",
                priority=3,
                next_step="追查码头脚印",
            )
            conn.commit()
            action = PlayerAction(campaign_id=campaign_id, session_id=session_id, text="我追查信使")

            pack = build_context_pack(
                conn,
                action=action,
                assessment=ActionJudgeAgent().run(action),
                memory_cfg=MemoryConfig(),
            )

            thread_block = next(block for block in pack.blocks if block.kind == "plot_threads")
            self.assertIn(f"[#{thread_id} · P3]", thread_block.content)
            self.assertIn("失踪的信使", thread_block.content)
        finally:
            conn.close()
            tmp.cleanup()

    def test_resolved_adjudication_is_injected_as_authoritative_context(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="锁门前",
            )
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
                attempt_id="context-check",
            )
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([13])).adjudicate(
                AdjudicationRequest(attempt_id=action.attempt_id, action=action)
            )

            pack = build_context_pack(
                conn,
                action=action,
                assessment=record.to_action_assessment(),
                memory_cfg=MemoryConfig(),
            )

            assessment_block = next(block for block in pack.blocks if block.kind == "action_assessment")
            self.assertIn("adjudication_status: resolved", assessment_block.content)
            self.assertIn("ability_skill: DEX", assessment_block.content)
            self.assertIn("authoritative_total: 15; outcome: success", assessment_block.content)
            self.assertIn("do not reroll", assessment_block.content)
        finally:
            conn.close()
            tmp.cleanup()

    def test_recalled_context_explains_included_blocks(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="乌鸦酒馆",
            )
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=campaign_id,
                type="Location",
                title="乌鸦酒馆",
                content="港口区的旧酒馆，老板知道走私线索。",
                tags="酒馆,港口区",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"name":"艾拉","hp":8,"max_hp":12,"conditions":["隐匿"]}]}',
            )
            conn.commit()

            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我在酒馆观察并掷 1d20+3",
                manual_tags=["酒馆"],
                extra_context="我站在阴影里。",
            )
            assessment = ActionJudgeAgent().run(action)
            pack = build_context_pack(
                conn,
                action=action,
                assessment=assessment,
                memory_cfg=MemoryConfig(),
                state_block=action.extra_context,
            )

            recalled = pack.recalled_context
            titles = [item["title"] for item in recalled]
            self.assertIn("WorldBible 1", titles)
            self.assertIn("Character Sheet", titles)
            self.assertIn("Turn Extra Context", titles)
            self.assertIn("Action Assessment", titles)
            self.assertTrue(all(item["reason"] for item in recalled))
            self.assertTrue(all(len(item["preview"]) <= 140 for item in recalled))
            world_item = next(item for item in recalled if item["title"] == "WorldBible 1")
            self.assertEqual(world_item["kind"], "world_bible")
            self.assertEqual(world_item["source"], "world_bible")
            self.assertIn("标签", world_item["reason"])
        finally:
            conn.close()
            tmp.cleanup()

    def test_context_budget_keeps_core_blocks_and_skips_low_priority_memory(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="钟楼门厅",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"name":"艾拉","hp":8,"max_hp":12,"conditions":["隐匿"]}]}',
            )
            story_journal.insert_story_journal_entry(
                conn,
                session_id=session_id,
                scene_id="old-scene",
                summary="旧剧情摘要：" + ("很久以前的码头支线。" * 80),
                open_threads="旧支线",
                key_facts="旧事实",
            )
            conn.commit()

            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我检查钟楼门厅",
                manual_tags=[],
                extra_context="",
            )
            assessment = ActionJudgeAgent().run(action)
            pack = build_context_pack(
                conn,
                action=action,
                assessment=assessment,
                memory_cfg=MemoryConfig(story_journal_for_prompt=12, context_chars_for_prompt=260),
            )

            kinds = [b.kind for b in pack.blocks]
            self.assertIn("scene_state", kinds)
            self.assertIn("character_state", kinds)
            self.assertIn("action_assessment", kinds)
            self.assertNotIn("story_memory", kinds)
            self.assertLessEqual(sum(len(b.content) for b in pack.blocks), 260)

            skipped = [item for item in pack.recalled_context if item.get("status") == "skipped"]
            self.assertTrue(skipped)
            self.assertEqual(skipped[0]["kind"], "story_memory")
            self.assertIn("预算", skipped[0]["reason"])
            included = [item for item in pack.recalled_context if item.get("status") == "included"]
            self.assertTrue(any(item["kind"] == "character_state" for item in included))
        finally:
            conn.close()
            tmp.cleanup()

    def test_tiny_context_budget_still_injects_frozen_adjudication_into_prompt(self) -> None:
        tmp, conn = self._conn()
        try:
            campaign_id = campaigns.create_campaign(conn, "极小预算测试")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="机关门前",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"name":"艾拉","level":1,"abilities":{"DEX":14}}]}',
            )
            conn.commit()
            action = PlayerAction(
                campaign_id=campaign_id,
                session_id=session_id,
                text="我尝试开锁",
                attempt_id="tiny-budget-check",
            )
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([13])).adjudicate(
                AdjudicationRequest(attempt_id=action.attempt_id, action=action)
            )

            pack = build_context_pack(
                conn,
                action=action,
                assessment=record.to_action_assessment(),
                memory_cfg=MemoryConfig(context_chars_for_prompt=1),
            )

            assessment_blocks = [block for block in pack.blocks if block.kind == "action_assessment"]
            self.assertEqual(len(assessment_blocks), 1)
            self.assertIn("authoritative_total: 15; outcome: success", assessment_blocks[0].content)
            recalled_assessment = next(
                item for item in pack.recalled_context if item["kind"] == "action_assessment"
            )
            self.assertEqual(recalled_assessment["status"], "included")

            messages = build_dm_messages_from_context_pack(pack)
            self.assertIn("authoritative_total: 15; outcome: success", messages[1].content)
        finally:
            conn.close()
            tmp.cleanup()

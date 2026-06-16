import tempfile
import unittest
from pathlib import Path

from one_person_dnd.config import LLMConfig, MemoryConfig
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, sessions
from one_person_dnd.db.schema import init_db
from one_person_dnd.engine import orchestrator
from one_person_dnd.llm import ChatMessage


class RecordingClient:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def chat(self, messages: list[ChatMessage]) -> str:
        self.messages = list(messages)
        return "\n".join(
            [
                "===NARRATION===",
                "艾拉谨慎地检查门厅。",
                "===CHOICES===",
                "- 继续搜索",
                "- 退回走廊",
                "===DM_NOTES===",
                "ok",
                "===MEMORY===",
                "艾拉检查门厅。",
            ]
        )


class TestOrchestratorLegacyEntry(unittest.TestCase):
    def _db_with_character(self) -> tuple[tempfile.TemporaryDirectory, Path, int, int]:
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"name":"艾拉","race":"人类","class":"游侠","hp":8,"max_hp":12,"inventory":["短弓"]}]}',
            )
            conn.commit()
        finally:
            conn.close()
        return tmp, db_path, campaign_id, session_id

    def test_run_turn_uses_context_pack_character_summary(self) -> None:
        tmp, db_path, campaign_id, session_id = self._db_with_character()
        client = RecordingClient()
        original_factory = orchestrator.create_llm_client
        orchestrator.create_llm_client = lambda _cfg: client
        try:
            result = orchestrator.run_turn(
                db_path=db_path,
                llm_cfg=LLMConfig(base_url="http://example.test/v1", api_key="k", model="m"),
                campaign_id=campaign_id,
                session_id=session_id,
                player_text="我检查门厅并掷 1d20+2",
                state_block="只记录这回合的脚步声",
                tags=[],
                memory_cfg=MemoryConfig(),
            )

            prompt_text = "\n\n".join(m.content for m in client.messages)
            self.assertIn("名称：艾拉", prompt_text)
            self.assertIn("HP：8/12", prompt_text)
            self.assertIn("物品：短弓", prompt_text)
            self.assertIn("action_type:", prompt_text)
            self.assertEqual(len(result.dice_events), 1)
        finally:
            orchestrator.create_llm_client = original_factory
            tmp.cleanup()

    def test_old_turn_message_builder_is_not_exported(self) -> None:
        self.assertFalse(hasattr(orchestrator, "build_turn_messages_and_preview"))

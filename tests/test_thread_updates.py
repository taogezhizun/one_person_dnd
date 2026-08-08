import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, plot_threads, sessions
from one_person_dnd.db.schema import init_db
from one_person_dnd.domain.thread_updates import (
    apply_thread_updates_json,
    preview_thread_updates_json,
    validate_thread_updates_json,
)
from one_person_dnd.engine.guardrails import GuardrailError


class TestThreadUpdates(unittest.TestCase):
    def test_validation_rejects_null_existing_thread_id(self) -> None:
        with self.assertRaisesRegex(GuardrailError, "id 必须是正整数"):
            validate_thread_updates_json('{"updates":[{"id":null,"status":"closed"}]}')

    def test_validation_rejects_non_positive_existing_thread_id(self) -> None:
        for invalid_id in (0, -1):
            with self.subTest(invalid_id=invalid_id):
                payload = json.dumps({"updates": [{"id": invalid_id, "status": "closed"}]})
                with self.assertRaisesRegex(GuardrailError, "id 必须是正整数"):
                    validate_thread_updates_json(payload)

    def test_validation_rejects_non_integer_existing_thread_id(self) -> None:
        for invalid_id in ("7", 1.5, True, [], {}):
            with self.subTest(invalid_id=invalid_id):
                payload = json.dumps({"updates": [{"id": invalid_id, "status": "closed"}]})
                with self.assertRaisesRegex(GuardrailError, "id 必须是正整数"):
                    validate_thread_updates_json(payload)

    def test_validation_returns_normalized_updates_without_applying(self) -> None:
        updates = validate_thread_updates_json('{"updates":[{"id":7,"status":"closed"}]}')

        self.assertEqual(updates, [{"id": 7, "status": "closed"}])

    def _conn(self) -> tuple[tempfile.TemporaryDirectory, sqlite3.Connection, int, int]:
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        campaign_id = campaigns.create_campaign(conn, "测试战役")
        session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
        conn.commit()
        return tmp, conn, campaign_id, session_id

    def test_preview_thread_updates_summarizes_updates_and_creates(self) -> None:
        payload = {
            "updates": [
                {"id": 7, "summary": "学徒最后出现在乌鸦酒馆。", "next_step": "询问老板娘。"},
                {"title": "查明银钥匙来历", "priority": 2, "tags": "支线,钥匙"},
            ]
        }

        preview = preview_thread_updates_json(json.dumps(payload, ensure_ascii=False))

        self.assertTrue(preview.ok)
        self.assertEqual(preview.summary, "将更新剧情线")
        self.assertIn("#7 更新：学徒最后出现在乌鸦酒馆。；下一步：询问老板娘。", preview.lines)
        self.assertIn("新建：查明银钥匙来历（P2，支线,钥匙）", preview.lines)

    def test_apply_thread_updates_updates_existing_and_creates_new_thread(self) -> None:
        tmp, conn, _campaign_id, session_id = self._conn()
        try:
            thread_id = plot_threads.create_thread(
                conn,
                session_id=session_id,
                title="寻找失踪的学徒",
                priority=1,
                summary="刚接到委托。",
                next_step="去学院。",
                tags="主线",
            )
            conn.commit()
            payload = {
                "updates": [
                    {
                        "id": thread_id,
                        "summary": "学徒最后出现在乌鸦酒馆。",
                        "next_step": "询问老板娘。",
                    },
                    {
                        "title": "查明银钥匙来历",
                        "priority": 2,
                        "summary": "钥匙上有乌鸦徽记。",
                        "next_step": "找铁匠辨认。",
                        "tags": "支线,钥匙",
                    },
                ]
            }

            applied = apply_thread_updates_json(
                conn,
                session_id=session_id,
                delta_json_text=json.dumps(payload, ensure_ascii=False),
            )
            conn.commit()

            self.assertEqual(applied, ["updated:1", "created:2"])
            rows = plot_threads.list_threads(conn, session_id=session_id, status="open", limit=20)
            by_title = {r["title"]: r for r in rows}
            self.assertEqual(by_title["寻找失踪的学徒"]["summary"], "学徒最后出现在乌鸦酒馆。")
            self.assertEqual(by_title["寻找失踪的学徒"]["next_step"], "询问老板娘。")
            self.assertEqual(by_title["寻找失踪的学徒"]["tags"], "主线")
            self.assertEqual(by_title["查明银钥匙来历"]["priority"], 2)
            self.assertEqual(by_title["查明银钥匙来历"]["summary"], "钥匙上有乌鸦徽记。")
        finally:
            conn.close()
            tmp.cleanup()

    def test_invalid_thread_update_status_is_rejected(self) -> None:
        preview = preview_thread_updates_json('{"updates":[{"title":"坏状态","status":"paused"}]}')

        self.assertFalse(preview.ok)
        self.assertEqual(preview.summary, "无法预览剧情线更新")
        self.assertIn("status 必须是 open 或 closed", preview.lines[0])

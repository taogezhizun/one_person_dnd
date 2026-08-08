import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from one_person_dnd.db import schema
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import adjudication_records, campaigns, sessions, turn_logs


class TestAdjudicationRepo(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "one_person_dnd.sqlite3"
        schema.init_db(self.db_path)
        self.conn = get_connection(self.db_path)
        campaign_id = campaigns.create_campaign(self.conn, "裁决测试")
        self.session_id = sessions.create_session(
            self.conn,
            campaign_id=campaign_id,
            title="第一章",
            current_scene="石门前",
        )
        self.other_session_id = sessions.create_session(
            self.conn,
            campaign_id=campaign_id,
            title="第二章",
            current_scene="塔顶",
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_record_can_commit_before_turn_log_and_reopen_for_replay(self) -> None:
        record_json = json.dumps({"resolution": "check", "roll": 14, "total": 17})
        record_id = adjudication_records.create(
            self.conn,
            session_id=self.session_id,
            attempt_id="attempt-before-llm",
            fingerprint="sha256:abc",
            record_json=record_json,
        )
        self.conn.commit()
        self.conn.close()

        self.conn = get_connection(self.db_path)
        restored = adjudication_records.get_by_attempt(
            self.conn,
            session_id=self.session_id,
            attempt_id="attempt-before-llm",
        )
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["id"], record_id)
        self.assertEqual(restored["fingerprint"], "sha256:abc")
        self.assertEqual(restored["record_json"], record_json)
        self.assertIsNone(restored["turn_index"])
        self.assertIsNone(restored["completed_at"])
        self.assertEqual(turn_logs.list_all_for_session(self.conn, session_id=self.session_id), [])

    def test_attempt_keys_are_unique_per_session(self) -> None:
        adjudication_records.create(
            self.conn,
            session_id=self.session_id,
            attempt_id="same-key",
            fingerprint="fp-1",
            record_json="{}",
        )
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            adjudication_records.create(
                self.conn,
                session_id=self.session_id,
                attempt_id="same-key",
                fingerprint="fp-2",
                record_json="{}",
            )
        self.conn.rollback()

        adjudication_records.create(
            self.conn,
            session_id=self.other_session_id,
            attempt_id="same-key",
            fingerprint="fp-other-session",
            record_json="{}",
        )
        self.conn.commit()
        self.assertIsNotNone(
            adjudication_records.get_by_attempt(
                self.conn,
                session_id=self.other_session_id,
                attempt_id="same-key",
            )
        )

    def test_mark_completed_is_idempotent_but_will_not_rebind(self) -> None:
        adjudication_records.create(
            self.conn,
            session_id=self.session_id,
            attempt_id="complete-me",
            fingerprint="fp",
            record_json='{"degree":"success"}',
        )

        self.assertTrue(
            adjudication_records.mark_completed(
                self.conn,
                session_id=self.session_id,
                attempt_id="complete-me",
                turn_index=4,
            )
        )
        self.assertTrue(
            adjudication_records.mark_completed(
                self.conn,
                session_id=self.session_id,
                attempt_id="complete-me",
                turn_index=4,
            )
        )
        self.assertFalse(
            adjudication_records.mark_completed(
                self.conn,
                session_id=self.session_id,
                attempt_id="complete-me",
                turn_index=5,
            )
        )
        self.assertFalse(
            adjudication_records.mark_completed(
                self.conn,
                session_id=self.session_id,
                attempt_id="missing",
                turn_index=4,
            )
        )

        restored = adjudication_records.get_by_session_turn(
            self.conn,
            session_id=self.session_id,
            turn_index=4,
        )
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["attempt_id"], "complete-me")
        self.assertIsNotNone(restored["completed_at"])
        self.assertIsNone(
            adjudication_records.get_by_session_turn(
                self.conn,
                session_id=self.session_id,
                turn_index=5,
            )
        )

    def test_turn_log_attempt_partial_unique_index_is_session_scoped(self) -> None:
        for turn_index in (0, 1):
            turn_logs.insert_turn_log(
                self.conn,
                session_id=self.session_id,
                turn_index=turn_index,
                player_text=f"legacy-{turn_index}",
                dm_text="ok",
                dice_events_json="[]",
            )
        turn_logs.insert_turn_log(
            self.conn,
            session_id=self.session_id,
            turn_index=2,
            player_text="new",
            dm_text="ok",
            dice_events_json="[]",
            attempt_id="attempt-1",
            adjudication_json='{"roll":14}',
        )
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            turn_logs.insert_turn_log(
                self.conn,
                session_id=self.session_id,
                turn_index=3,
                player_text="duplicate attempt",
                dm_text="must fail",
                dice_events_json="[]",
                attempt_id="attempt-1",
                adjudication_json="{}",
            )
        self.conn.rollback()

        turn_logs.insert_turn_log(
            self.conn,
            session_id=self.other_session_id,
            turn_index=0,
            player_text="same attempt, other session",
            dm_text="ok",
            dice_events_json="[]",
            attempt_id="attempt-1",
            adjudication_json="{}",
        )
        linked = turn_logs.get_by_attempt(
            self.conn,
            session_id=self.session_id,
            attempt_id="attempt-1",
        )
        self.assertIsNotNone(linked)
        assert linked is not None
        self.assertEqual(linked["turn_index"], 2)

    def test_turn_log_snapshot_round_trip_supports_new_and_legacy_json(self) -> None:
        turn_logs.insert_turn_log(
            self.conn,
            session_id=self.session_id,
            turn_index=0,
            player_text="开锁",
            dm_text="锁舌弹开。",
            dice_events_json='[{"total":17}]',
            attempt_id="snapshot-attempt",
            adjudication_json='{"dc":15,"degree":"success"}',
        )
        self.conn.commit()

        captured = json.loads(
            json.dumps(turn_logs.list_all_for_session(self.conn, session_id=self.session_id))
        )
        self.assertEqual(captured[0]["attempt_id"], "snapshot-attempt")
        self.assertIn("success", captured[0]["adjudication_json"])

        turn_logs.delete_all_for_session(self.conn, session_id=self.session_id)
        turn_logs.bulk_insert(self.conn, session_id=self.session_id, rows=captured)
        restored = turn_logs.get_by_session_turn(
            self.conn,
            session_id=self.session_id,
            turn_index=0,
        )
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["attempt_id"], "snapshot-attempt")
        self.assertIn("success", restored["adjudication_json"])

        legacy_capture = [dict(captured[0])]
        legacy_capture[0].pop("attempt_id")
        legacy_capture[0].pop("adjudication_json")
        turn_logs.delete_all_for_session(self.conn, session_id=self.session_id)
        turn_logs.bulk_insert(self.conn, session_id=self.session_id, rows=legacy_capture)
        restored_legacy = turn_logs.get_by_session_turn(
            self.conn,
            session_id=self.session_id,
            turn_index=0,
        )
        self.assertIsNotNone(restored_legacy)
        assert restored_legacy is not None
        self.assertIsNone(restored_legacy["attempt_id"])
        self.assertIsNone(restored_legacy["adjudication_json"])

    def test_delete_all_for_session_is_scoped(self) -> None:
        for session_id in (self.session_id, self.other_session_id):
            adjudication_records.create(
                self.conn,
                session_id=session_id,
                attempt_id="attempt",
                fingerprint=f"fp-{session_id}",
                record_json="{}",
            )

        adjudication_records.delete_all_for_session(self.conn, session_id=self.session_id)
        self.assertIsNone(
            adjudication_records.get_by_attempt(
                self.conn,
                session_id=self.session_id,
                attempt_id="attempt",
            )
        )
        self.assertIsNotNone(
            adjudication_records.get_by_attempt(
                self.conn,
                session_id=self.other_session_id,
                attempt_id="attempt",
            )
        )


class TestAdjudicationSchemaMigration(unittest.TestCase):
    def test_v9_migrates_sequentially_to_v10(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "v9.sqlite3"
            conn = get_connection(db_path)
            try:
                for version in range(1, 10):
                    getattr(schema, f"_apply_schema_v{version}")(conn)
                conn.execute("PRAGMA user_version = 9")
                conn.commit()
            finally:
                conn.close()

            schema.init_db(db_path)
            conn = get_connection(db_path)
            try:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 10)
                turn_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(turn_logs)").fetchall()
                }
                self.assertIn("attempt_id", turn_columns)
                self.assertIn("adjudication_json", turn_columns)
                table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'adjudication_records'"
                ).fetchone()
                self.assertIsNotNone(table)
                partial_index = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'idx_turn_logs_unique_attempt'"
                ).fetchone()
                self.assertIsNotNone(partial_index)
                assert partial_index is not None
                self.assertIn("WHERE attempt_id IS NOT NULL", partial_index["sql"])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

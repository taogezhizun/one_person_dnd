import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, session_snapshots, sessions
from one_person_dnd.db.schema import init_db
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import saves


class TestSaveSnapshotRoutes(unittest.TestCase):
    def test_restore_creates_safety_snapshot_before_overwriting_current_state(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        paths = AppPaths(root, app_dir, root / "api_config.ini", app_dir / "one_person_dnd.sqlite3")
        init_db(paths.db_path)

        conn = get_connection(paths.db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "雾港")
            session_id = sessions.create_session(
                conn,
                campaign_id=campaign_id,
                title="第一章",
                current_scene="最新场景",
            )
            sessions.update_session_sidebar(
                conn,
                campaign_id=campaign_id,
                session_id=session_id,
                current_scene="最新场景",
                session_state="最新状态",
                pinned_world_notes="最新规则",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text=json.dumps({"party": [{"name": "现在的角色", "hp": 3}]}, ensure_ascii=False),
            )
            target_snapshot_id = session_snapshots.create_snapshot(
                conn,
                session_id=session_id,
                snapshot_name="进入遗迹前",
                turn_index=2,
                current_scene="旧场景",
                session_state="旧状态",
                pinned_world_notes="旧规则",
                character_sheet_json=json.dumps({"party": [{"name": "过去的角色", "hp": 10}]}, ensure_ascii=False),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.saves.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
            ):
                response = saves.saves_session_restore(
                    session_id=session_id,
                    snapshot_id=target_snapshot_id,
                )

            self.assertEqual(response.status_code, 303)
            conn = get_connection(paths.db_path)
            try:
                snapshots = session_snapshots.list_snapshots(conn, session_id=session_id)
                self.assertEqual(len(snapshots), 2)
                safety = session_snapshots.get_snapshot(conn, snapshot_id=int(snapshots[0]["id"]))
                self.assertIsNotNone(safety)
                assert safety is not None
                self.assertEqual(safety["snapshot_name"], "恢复前自动备份 · 进入遗迹前")
                self.assertEqual(safety["current_scene"], "最新场景")
                self.assertEqual(safety["session_state"], "最新状态")
                self.assertIn("现在的角色", safety["character_sheet_json"])

                current = sessions.get_session_sidebar(conn, session_id)
                self.assertEqual(current["current_scene"], "旧场景")
                self.assertEqual(current["session_state"], "旧状态")
                self.assertEqual(current["pinned_world_notes"], "旧规则")
                self.assertIn("过去的角色", character_sheets.get_character_sheet(conn, session_id=session_id))
            finally:
                conn.close()
        finally:
            tmp.cleanup()

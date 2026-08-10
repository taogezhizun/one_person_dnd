import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from one_person_dnd.db import get_connection
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.app import create_app
from one_person_dnd.web.localization import LOCALE_COOKIE


class TestLocaleNeutralPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        app_dir = root / ".one_person_dnd"
        self.paths = AppPaths(
            project_root=root,
            app_dir=app_dir,
            config_path=root / "api_config.ini",
            db_path=app_dir / "one_person_dnd.sqlite3",
        )
        self.path_patches = [
            patch("one_person_dnd.web.app.ensure_app_dirs", return_value=self.paths),
            patch("one_person_dnd.web.routes.common.ensure_app_dirs", return_value=self.paths),
            patch("one_person_dnd.web.routes.memory.ensure_app_dirs", return_value=self.paths),
            patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=self.paths),
        ]
        for path_patch in self.path_patches:
            path_patch.start()
            self.addCleanup(path_patch.stop)
        self.client = TestClient(create_app())
        self.client.cookies.set(LOCALE_COOKIE, "en")

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()

    def test_english_ui_does_not_localize_system_save_defaults(self) -> None:
        response = self.client.post(
            "/saves/campaign/new",
            data={"name": "English UI Campaign"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        conn = get_connection(self.paths.db_path)
        try:
            campaign = conn.execute(
                "SELECT id FROM campaigns WHERE name = ?",
                ("English UI Campaign",),
            ).fetchone()
            self.assertIsNotNone(campaign)
            campaign_id = int(campaign["id"])
            default_session = conn.execute(
                "SELECT title, current_scene FROM sessions WHERE campaign_id = ? ORDER BY id LIMIT 1",
                (campaign_id,),
            ).fetchone()
            self.assertEqual(tuple(default_session), ("默认会话", "起始"))
        finally:
            conn.close()

        response = self.client.post(
            "/saves/session/new",
            data={"title": "Second Chapter", "current_scene": ""},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        conn = get_connection(self.paths.db_path)
        try:
            second_session = conn.execute(
                "SELECT id, current_scene FROM sessions WHERE campaign_id = ? ORDER BY id DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()
            second_session_id = int(second_session["id"])
            self.assertEqual(second_session["current_scene"], "起始")
        finally:
            conn.close()

        response = self.client.post(
            "/saves/session/snapshot",
            data={"session_id": second_session_id, "snapshot_name": ""},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        conn = get_connection(self.paths.db_path)
        try:
            snapshot = conn.execute(
                "SELECT id, snapshot_name FROM session_snapshots WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (second_session_id,),
            ).fetchone()
            snapshot_id = int(snapshot["id"])
            self.assertEqual(snapshot["snapshot_name"], "手动快照")
        finally:
            conn.close()

        response = self.client.post(
            "/saves/session/restore",
            data={"session_id": second_session_id, "snapshot_id": snapshot_id},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        response = self.client.post(
            "/saves/session/fork",
            data={"session_id": second_session_id, "snapshot_id": snapshot_id, "fork_title": ""},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        conn = get_connection(self.paths.db_path)
        try:
            names = {
                row["snapshot_name"]
                for row in conn.execute(
                    "SELECT snapshot_name FROM session_snapshots WHERE session_id = ?",
                    (second_session_id,),
                ).fetchall()
            }
            self.assertIn("恢复前自动备份 · 手动快照", names)
            fork = conn.execute(
                "SELECT title FROM sessions WHERE parent_session_id = ? ORDER BY id DESC LIMIT 1",
                (second_session_id,),
            ).fetchone()
            self.assertEqual(fork["title"], "手动快照-分叉")
        finally:
            conn.close()

    def test_english_ui_does_not_localize_world_bible_content(self) -> None:
        self.client.post(
            "/saves/campaign/new",
            data={"name": "World Campaign"},
            follow_redirects=False,
        )
        response = self.client.post(
            "/memory/world/new",
            data={
                "type": "Location",
                "title": "Moonlit Harbor",
                "location_geo": "A harbor under twin moons",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

        conn = get_connection(self.paths.db_path)
        try:
            entry = conn.execute(
                "SELECT content FROM world_bible_entries WHERE title = ?",
                ("Moonlit Harbor",),
            ).fetchone()
            self.assertEqual(entry["content"], "地理：A harbor under twin moons")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

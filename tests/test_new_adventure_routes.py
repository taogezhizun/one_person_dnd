import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.config import load_app_state
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, sessions, world_bible
from one_person_dnd.db.schema import init_db
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import new_adventure


class TestNewAdventureRoutes(unittest.TestCase):
    def test_apply_creates_independent_campaign_and_first_session(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        paths = AppPaths(root, app_dir, root / "api_config.ini", app_dir / "one_person_dnd.sqlite3")
        init_db(paths.db_path)

        conn = get_connection(paths.db_path)
        try:
            old_campaign_id = campaigns.create_campaign(conn, "旧冒险")
            old_session_id = sessions.create_session(
                conn,
                campaign_id=old_campaign_id,
                title="旧章节",
                current_scene="旧城门",
            )
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=old_campaign_id,
                type="Rule",
                title="旧规则",
                content="旧冒险保持原样。",
                tags="旧",
            )
            character_sheets.upsert_character_sheet(
                conn,
                session_id=old_session_id,
                json_text=json.dumps({"party": [{"name": "旧角色"}]}, ensure_ascii=False),
            )
            conn.commit()
        finally:
            conn.close()

        preview = {
            "adventure_name": "模型原名",
            "chapter_title": "模型章节",
            "opening_scene": "潮汐钟楼下",
            "world_bible_entries": [
                {
                    "type": "Location",
                    "title": "潮汐钟楼",
                    "content": "钟声会改变海面高度。",
                    "tags": "钟楼,潮汐",
                }
            ],
            "character_sheet": {"party": [{"name": "新角色", "hp": 10}]},
        }
        try:
            with patch("one_person_dnd.web.routes.new_adventure.ensure_app_dirs", return_value=paths):
                response = new_adventure.new_apply(
                    preview_json=json.dumps(preview, ensure_ascii=False),
                    adventure_name="玩家改名后的冒险",
                    chapter_title="第一章·潮声",
                )

            self.assertEqual(response.status_code, 303)
            conn = get_connection(paths.db_path)
            try:
                all_campaigns = campaigns.list_campaigns(conn)
                self.assertEqual(len(all_campaigns), 2)
                new_campaign = next(item for item in all_campaigns if item["name"] == "玩家改名后的冒险")
                new_session_id = sessions.get_first_session_id(conn, int(new_campaign["id"]))
                self.assertIsNotNone(new_session_id)
                assert new_session_id is not None
                self.assertEqual(sessions.get_session_title(conn, new_session_id), "第一章·潮声")
                self.assertEqual(sessions.get_session_scene_id(conn, new_session_id), "潮汐钟楼下")
                self.assertIn("新角色", character_sheets.get_character_sheet(conn, session_id=new_session_id))
                self.assertEqual(
                    world_bible.list_world_bible_entries(conn, campaign_id=int(new_campaign["id"]))[0]["title"],
                    "潮汐钟楼",
                )

                self.assertEqual(campaigns.get_campaign_name(conn, old_campaign_id), "旧冒险")
                self.assertEqual(sessions.get_session_title(conn, old_session_id), "旧章节")
                self.assertEqual(
                    world_bible.list_world_bible_entries(conn, campaign_id=old_campaign_id)[0]["title"],
                    "旧规则",
                )
                self.assertIn("旧角色", character_sheets.get_character_sheet(conn, session_id=old_session_id))
            finally:
                conn.close()

            state = load_app_state(paths.config_path)
            self.assertEqual(state.active_campaign_id, int(new_campaign["id"]))
            self.assertEqual(state.active_session_id, new_session_id)
        finally:
            tmp.cleanup()

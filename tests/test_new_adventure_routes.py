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


class _GeneratedAdventureClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return json.dumps(
            {
                "adventure_name": "雾港疑云",
                "chapter_title": "第一章·潮声",
                "opening_scene": "雾港码头",
                "world_bible_entries": [],
                "character_sheet": {
                    "party": [
                        {
                            "name": "阿洛",
                            "race": "人类",
                            "class": "游侠",
                            "level": "3",
                            "abilities": {"STR": 12, "DEX": 15, "WIS": 14},
                            "skill_proficiencies": ["Perception", "Stealth", "Perception"],
                        }
                    ],
                    "notes": "从码头开始",
                },
            },
            ensure_ascii=False,
        )


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
                stored_sheet = json.loads(
                    character_sheets.get_character_sheet(conn, session_id=new_session_id)
                )
                self.assertEqual(stored_sheet["party"][0]["name"], "新角色")
                self.assertEqual(stored_sheet["party"][0]["level"], 1)
                self.assertEqual(
                    stored_sheet["party"][0]["abilities"],
                    {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
                )
                self.assertEqual(stored_sheet["party"][0]["skill_proficiencies"], [])
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

    def test_generate_emits_rules_ready_character_schema_and_source_form(self) -> None:
        client = _GeneratedAdventureClient()
        with (
            patch("one_person_dnd.web.routes.new_adventure.load_active_llm_config", return_value=object()),
            patch("one_person_dnd.web.routes.new_adventure.create_llm_client", return_value=client),
            patch("one_person_dnd.web.routes.new_adventure.templates.TemplateResponse") as template_response,
        ):
            template_response.side_effect = lambda *, request, name, context: {"template": name, **context}
            context = new_adventure.new_generate(
                request=object(),
                adventure_brief="  追查幽灵船  ",
                genre="航海奇幻",
                tone="悬疑",
                tech_level="风帆时代",
                themes="探索,谜团",
                character_count=1,
                extra_constraints="不能复活",
                proposed_adventure_name="潮痕",
                proposed_chapter_title="失踪的灯塔",
            )

        self.assertEqual(context["template"], "new_preview.html")
        character = context["preview_obj"]["character_sheet"]["party"][0]
        self.assertEqual(character["level"], 3)
        self.assertEqual(
            character["abilities"],
            {"STR": 12, "DEX": 15, "CON": 10, "INT": 10, "WIS": 14, "CHA": 10},
        )
        self.assertEqual(character["skill_proficiencies"], ["Perception", "Stealth"])

        system_prompt = client.messages[0].content
        self.assertIn('"level":1', system_prompt)
        self.assertIn('"STR":10,"DEX":10,"CON":10,"INT":10,"WIS":10,"CHA":10', system_prompt)
        self.assertIn('"skill_proficiencies"', system_prompt)

        source = json.loads(context["source_form_json"])
        self.assertEqual(source["form_values"]["adventure_brief"], "追查幽灵船")
        self.assertEqual(source["form_values"]["extra_constraints"], "不能复活")
        self.assertEqual(source["proposal"]["adventure_name"], "潮痕")
        self.assertEqual(source["proposal"]["chapter_title"], "失踪的灯塔")

    def test_return_to_edit_restores_all_fields_and_latest_preview_names(self) -> None:
        source_form_json = json.dumps(
            {
                "form_values": {
                    "adventure_brief": "追查幽灵船",
                    "genre": "航海奇幻",
                    "tone": "悬疑",
                    "tech_level": "风帆时代",
                    "themes": "探索,谜团",
                    "character_count": 2,
                    "extra_constraints": "不能复活",
                },
                "proposal": {
                    "adventure_name": "潮痕",
                    "chapter_title": "失踪的灯塔",
                },
            },
            ensure_ascii=False,
        )
        with (
            patch("one_person_dnd.web.routes.new_adventure.load_active_llm_config", return_value=object()),
            patch("one_person_dnd.web.routes.new_adventure.templates.TemplateResponse") as template_response,
        ):
            template_response.side_effect = lambda *, request, name, context: {"template": name, **context}
            context = new_adventure.new_return(
                request=object(),
                source_form_json=source_form_json,
                adventure_name="雾中潮痕",
                chapter_title="第一章·灯塔无光",
            )

        self.assertEqual(context["template"], "new.html")
        self.assertEqual(
            context["form_values"],
            {
                "adventure_brief": "追查幽灵船",
                "genre": "航海奇幻",
                "tone": "悬疑",
                "tech_level": "风帆时代",
                "themes": "探索,谜团",
                "character_count": 2,
                "extra_constraints": "不能复活",
            },
        )
        self.assertEqual(
            context["proposal"],
            {"adventure_name": "雾中潮痕", "chapter_title": "第一章·灯塔无光"},
        )


if __name__ == "__main__":
    unittest.main()

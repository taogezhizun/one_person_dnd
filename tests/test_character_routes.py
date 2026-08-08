import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, plot_threads, sessions, state_change_requests
from one_person_dnd.db.schema import init_db
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import character


class TestCharacterRoutes(unittest.TestCase):
    def _paths_with_sheet(self) -> tuple[tempfile.TemporaryDirectory, AppPaths, int]:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        db_path = app_dir / "one_person_dnd.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"party":[{"name":"艾拉","race":"人类","class":"游侠","hp":8,"max_hp":12,"gold":15,"inventory":["短弓"]}]}',
            )
            conn.commit()
        finally:
            conn.close()
        return tmp, AppPaths(root, app_dir, root / "api_config.ini", db_path), session_id

    def test_character_panel_context_includes_character_summary(self) -> None:
        tmp, paths, session_id = self._paths_with_sheet()
        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character._render_panel(request=object(), session_id=session_id)

            summary = context["character_summary"]
            self.assertEqual(summary.name, "艾拉")
            self.assertEqual(summary.hp, 8)
            self.assertEqual(summary.max_hp, 12)
            self.assertEqual(summary.inventory, ["短弓"])
        finally:
            tmp.cleanup()

    def test_character_panel_context_includes_pending_change_preview(self) -> None:
        tmp, paths, session_id = self._paths_with_sheet()
        conn = get_connection(paths.db_path)
        try:
            state_change_requests.create_request(
                conn,
                session_id=session_id,
                turn_index=3,
                kind="state_delta",
                delta_json_text='{"party":[{"hp":6,"gold":18}]}',
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character._render_panel(request=object(), session_id=session_id)

            pending = context["pending_changes"]
            self.assertEqual(len(pending), 1)
            self.assertEqual(context["pending_count"], 1)
            preview = pending[0]["preview"]
            self.assertTrue(preview.ok)
            self.assertIn("HP：8 -> 6", preview.lines)
            self.assertIn("金币：15 -> 18", preview.lines)
        finally:
            tmp.cleanup()

    def test_character_panel_context_includes_thread_update_preview(self) -> None:
        tmp, paths, session_id = self._paths_with_sheet()
        conn = get_connection(paths.db_path)
        try:
            state_change_requests.create_request(
                conn,
                session_id=session_id,
                turn_index=4,
                kind="thread_updates",
                delta_json_text='{"updates":[{"title":"查明银钥匙来历","priority":2,"tags":"支线,钥匙"}]}',
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character._render_panel(request=object(), session_id=session_id)

            preview = context["pending_changes"][0]["preview"]
            self.assertTrue(preview.ok)
            self.assertEqual(preview.summary, "将更新剧情线")
            self.assertIn("新建：查明银钥匙来历（P2，支线,钥匙）", preview.lines)
        finally:
            tmp.cleanup()

    def test_change_apply_applies_thread_updates_request(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        db_path = app_dir / "one_person_dnd.sqlite3"
        init_db(db_path)
        paths = AppPaths(root, app_dir, root / "api_config.ini", db_path)
        conn = get_connection(db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
            thread_id = plot_threads.create_thread(
                conn,
                session_id=session_id,
                title="寻找失踪的学徒",
                priority=1,
                summary="刚接到委托。",
                next_step="去学院。",
                tags="主线",
            )
            request_id = state_change_requests.create_request(
                conn,
                session_id=session_id,
                turn_index=4,
                kind="thread_updates",
                delta_json_text='{"updates":[{"id":%d,"summary":"学徒最后出现在乌鸦酒馆。","next_step":"询问老板娘。"}]}' % thread_id,
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character.change_apply(request=object(), request_id=request_id)

            self.assertEqual(context["notice_message"], "已应用剧情线更新。")
            conn = get_connection(db_path)
            try:
                updated = plot_threads.get_thread(conn, session_id=session_id, thread_id=thread_id)
                req = state_change_requests.get_request(conn, request_id=request_id, session_id=session_id)
            finally:
                conn.close()
            self.assertEqual(updated["summary"], "学徒最后出现在乌鸦酒馆。")
            self.assertEqual(updated["next_step"], "询问老板娘。")
            self.assertEqual(req["status"], "applied")
        finally:
            tmp.cleanup()

    def test_change_apply_rejects_thread_update_with_null_id_without_500(self) -> None:
        tmp, paths, session_id = self._paths_with_sheet()
        conn = get_connection(paths.db_path)
        try:
            campaign_id = conn.execute(
                "SELECT campaign_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()["campaign_id"]
            request_id = state_change_requests.create_request(
                conn,
                session_id=session_id,
                turn_index=5,
                kind="thread_updates",
                delta_json_text='{"updates":[{"id":null,"status":"closed"}]}',
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch(
                    "one_person_dnd.web.routes.character.get_current_campaign_session",
                    return_value=(campaign_id, session_id),
                ),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character.change_apply(request=object(), request_id=request_id)

            self.assertEqual(context["notice_message"], "已拒绝：id 必须是正整数")
            self.assertEqual(context["pending_count"], 0)
            conn = get_connection(paths.db_path)
            try:
                rejected = state_change_requests.get_request(
                    conn,
                    request_id=request_id,
                    session_id=session_id,
                )
            finally:
                conn.close()
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(rejected["error_text"], "id 必须是正整数")
        finally:
            tmp.cleanup()

    def test_quick_adjust_updates_top_level_legacy_character_sheet(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        db_path = app_dir / "one_person_dnd.sqlite3"
        init_db(db_path)
        paths = AppPaths(root, app_dir, root / "api_config.ini", db_path)
        conn = get_connection(db_path)
        try:
            campaign_id = campaigns.create_campaign(conn, "测试战役")
            session_id = sessions.create_session(conn, campaign_id=campaign_id, title="第一章", current_scene="门厅")
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text='{"name":"独行者","hp":6,"gold":2,"inventory":["匕首"]}',
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                character.character_quick_adjust(
                    request=object(),
                    hp_delta=2,
                    gold_delta=3,
                    reason="测试",
                )

            conn = get_connection(db_path)
            try:
                updated = character_sheets.get_character_sheet(conn, session_id=session_id)
            finally:
                conn.close()
            self.assertIn('"name": "独行者"', updated)
            self.assertIn('"hp": 8', updated)
            self.assertIn('"gold": 5', updated)
            self.assertNotIn('"party"', updated)
        finally:
            tmp.cleanup()

    def test_quick_state_updates_conditions_and_notes_without_erasing_stats(self) -> None:
        tmp, paths, session_id = self._paths_with_sheet()
        conn = get_connection(paths.db_path)
        try:
            campaign_id = conn.execute("SELECT campaign_id FROM sessions WHERE id = ?", (session_id,)).fetchone()["campaign_id"]
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character.character_quick_state(
                    request=object(),
                    conditions_text="中毒\n隐匿",
                    notes_text="害怕深水。",
                )

            self.assertEqual(context["notice_message"], "已保存状态、物品与备注。")
            conn = get_connection(paths.db_path)
            try:
                updated = character_sheets.get_character_sheet(conn, session_id=session_id)
            finally:
                conn.close()
            self.assertIn('"conditions": [', updated)
            self.assertIn('"中毒"', updated)
            self.assertIn('"隐匿"', updated)
            self.assertIn('"notes": "害怕深水。"', updated)
            self.assertIn('"hp": 8', updated)
            self.assertIn('"gold": 15', updated)
            self.assertIn('"inventory": [', updated)
            self.assertIn('"短弓"', updated)
        finally:
            tmp.cleanup()

    def test_quick_state_updates_inventory_as_structured_character_items(self) -> None:
        tmp, paths, session_id = self._paths_with_sheet()
        conn = get_connection(paths.db_path)
        try:
            campaign_id = conn.execute("SELECT campaign_id FROM sessions WHERE id = ?", (session_id,)).fetchone()["campaign_id"]
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.character.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.character.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.character.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = character.character_quick_state(
                    request=object(),
                    conditions_text="中毒",
                    inventory_text="短弓\n专属的有无穷魔力的魔法戒指",
                    notes_text="戒指放在口袋里。",
                )

            summary = context["character_summary"]
            self.assertEqual(summary.inventory, ["短弓", "专属的有无穷魔力的魔法戒指"])
            conn = get_connection(paths.db_path)
            try:
                updated = character_sheets.get_character_sheet(conn, session_id=session_id)
            finally:
                conn.close()
            self.assertIn('"inventory": [', updated)
            self.assertIn('"专属的有无穷魔力的魔法戒指"', updated)
        finally:
            tmp.cleanup()

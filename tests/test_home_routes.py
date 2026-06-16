import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import app_settings, campaigns, llm_profiles, sessions
from one_person_dnd.db.schema import init_db
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import saves
from one_person_dnd.web.routes.common import ACTIVE_LLM_PROFILE_KEY


class TestHomeRoutes(unittest.TestCase):
    def test_home_uses_active_db_profile_for_llm_configured_status(self) -> None:
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
            profile_id = llm_profiles.create_profile(
                conn,
                name="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com/v1",
                api_key="k",
                model="deepseek-chat",
                timeout_seconds=60.0,
            )
            app_settings.set(conn, ACTIVE_LLM_PROFILE_KEY, str(profile_id))
            conn.commit()
        finally:
            conn.close()

        try:
            with (
                patch("one_person_dnd.web.routes.common.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.saves.get_current_campaign_session", return_value=(campaign_id, session_id)),
                patch("one_person_dnd.web.routes.saves.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = saves.home(request=object())

            self.assertTrue(context["llm_configured"])
        finally:
            tmp.cleanup()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import llm_profiles
from one_person_dnd.db.schema import init_db
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.routes import models


class TestModelsRoutes(unittest.TestCase):
    def _paths(self) -> tuple[tempfile.TemporaryDirectory, AppPaths]:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        app_dir = root / ".one_person_dnd"
        app_dir.mkdir()
        db_path = app_dir / "one_person_dnd.sqlite3"
        init_db(db_path)
        return tmp, AppPaths(
            project_root=root,
            app_dir=app_dir,
            config_path=root / "api_config.ini",
            db_path=db_path,
        )

    def test_create_deepseek_profile_applies_provider_defaults(self) -> None:
        tmp, paths = self._paths()
        try:
            with patch("one_person_dnd.web.routes.models.ensure_app_dirs", return_value=paths):
                response = models.models_create(
                    name="DeepSeek",
                    provider="deepseek",
                    base_url="",
                    api_key="k",
                    model="",
                    timeout_seconds=60.0,
                )

            conn = get_connection(paths.db_path)
            try:
                profile = llm_profiles.get_profile_by_name(conn, "DeepSeek")
            finally:
                conn.close()

            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertEqual(profile["provider"], "deepseek")
            self.assertEqual(profile["base_url"], "https://api.deepseek.com/v1")
            self.assertEqual(profile["model"], "deepseek-chat")
            self.assertEqual(response.headers["location"], "/models?created=1")
        finally:
            tmp.cleanup()

    def test_models_page_passes_provider_presets_to_template(self) -> None:
        tmp, paths = self._paths()
        try:
            with (
                patch("one_person_dnd.web.routes.models.ensure_default_llm_profile_from_ini"),
                patch("one_person_dnd.web.routes.models.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.models.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = models.models_page(request=object())

            preset_ids = [p.id for p in context["provider_presets"]]
            self.assertIn("openai_compat", preset_ids)
            self.assertIn("deepseek", preset_ids)
        finally:
            tmp.cleanup()

    def test_models_template_has_provider_select_and_preset_script(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")

        self.assertIn("data-provider-select", template)
        self.assertIn("data-base-url", template)
        self.assertIn("data-default-model", template)

    def test_models_page_exposes_created_state_and_next_adventure_cta(self) -> None:
        tmp, paths = self._paths()
        try:
            with (
                patch("one_person_dnd.web.routes.models.ensure_default_llm_profile_from_ini"),
                patch("one_person_dnd.web.routes.models.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.web.routes.models.templates.TemplateResponse") as template_response,
            ):
                template_response.side_effect = lambda *, request, name, context: context
                context = models.models_page(request=object(), created=1)

            self.assertTrue(context["created"])
            template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")
            self.assertIn("models.created.title", template)
            self.assertIn("models.created.body", template)
            self.assertIn("#model-profile-{{ active_id }}", template)
            self.assertIn("models.test_connection_cta", template)
            self.assertIn('href="/new"', template)
            self.assertIn("models.create_new_adventure", template)
        finally:
            tmp.cleanup()

    def test_update_keeps_existing_api_key_when_edit_field_is_blank(self) -> None:
        tmp, paths = self._paths()
        conn = get_connection(paths.db_path)
        try:
            profile_id = llm_profiles.create_profile(
                conn,
                name="DeepSeek",
                provider="deepseek",
                base_url="https://api.deepseek.com/v1",
                api_key="secret-key",
                model="deepseek-chat",
                timeout_seconds=60.0,
            )
            conn.commit()
        finally:
            conn.close()

        try:
            with patch("one_person_dnd.web.routes.models.ensure_app_dirs", return_value=paths):
                models.models_update(
                    profile_id=profile_id,
                    name="DeepSeek Updated",
                    provider="deepseek",
                    base_url="https://api.deepseek.com/v1",
                    api_key="",
                    model="deepseek-chat",
                    timeout_seconds=45.0,
                )

            conn = get_connection(paths.db_path)
            try:
                updated = llm_profiles.get_profile(conn, profile_id)
            finally:
                conn.close()
            self.assertEqual(updated["api_key"], "secret-key")
            self.assertEqual(updated["name"], "DeepSeek Updated")
            self.assertEqual(float(updated["timeout_seconds"]), 45.0)
        finally:
            tmp.cleanup()

    def test_models_template_browses_profiles_before_progressive_creation(self) -> None:
        template = Path("src/one_person_dnd/web/templates/models.html").read_text(encoding="utf-8")
        css = Path("src/one_person_dnd/web/static/style.css").read_text(encoding="utf-8")

        self.assertIn("model-quickstart", template)
        self.assertIn("models.quickstart.title", template)
        self.assertIn('name="provider" value="deepseek"', template)
        self.assertIn('name="base_url" value="https://api.deepseek.com/v1"', template)
        self.assertIn('name="model" value="deepseek-chat"', template)
        self.assertIn('name="timeout_seconds" value="60.0"', template)
        self.assertLess(template.index("models.existing.title"), template.index("models.add.summary"))
        self.assertLess(template.index("models.quickstart.title"), template.index("models.custom.summary"))
        self.assertIn(".model-quickstart", css)
        self.assertIn(".model-quickstart__grid", css)

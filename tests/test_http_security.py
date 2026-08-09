import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from one_person_dnd.config import ServerConfig
from one_person_dnd.launcher import main
from one_person_dnd.paths import AppPaths
from one_person_dnd.web.app import create_app


class TestUnsafeWriteProtection(unittest.TestCase):
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
            patch("one_person_dnd.web.routes.saves.ensure_app_dirs", return_value=self.paths),
        ]
        for path_patch in self.path_patches:
            path_patch.start()
            self.addCleanup(path_patch.stop)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()

    def test_cross_origin_post_is_rejected_without_creating_campaign(self) -> None:
        response = self.client.post(
            "/saves/campaign/new",
            data={"name": "cross-origin-campaign"},
            headers={"Origin": "https://evil.example"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        saves_page = self.client.get("/saves")
        self.assertNotIn("cross-origin-campaign", saves_page.text)

    def test_cross_site_fetch_post_is_rejected_without_creating_campaign(self) -> None:
        response = self.client.post(
            "/saves/campaign/new",
            data={"name": "cross-site-fetch-campaign"},
            headers={"Sec-Fetch-Site": "cross-site"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)
        saves_page = self.client.get("/saves")
        self.assertNotIn("cross-site-fetch-campaign", saves_page.text)

    def test_same_origin_post_still_creates_campaign(self) -> None:
        response = self.client.post(
            "/saves/campaign/new",
            data={"name": "same-origin-campaign"},
            headers={
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        saves_page = self.client.get("/saves")
        self.assertIn("same-origin-campaign", saves_page.text)

    def test_legacy_local_post_without_browser_security_headers_still_creates_campaign(self) -> None:
        response = self.client.post(
            "/saves/campaign/new",
            data={"name": "legacy-local-campaign"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        saves_page = self.client.get("/saves")
        self.assertIn("legacy-local-campaign", saves_page.text)


class TestLauncherNetworkSafety(unittest.TestCase):
    def test_non_loopback_host_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            paths = AppPaths(
                project_root=root,
                app_dir=root / ".one_person_dnd",
                config_path=root / "api_config.ini",
                db_path=root / ".one_person_dnd" / "one_person_dnd.sqlite3",
            )
            stderr = io.StringIO()
            with (
                patch("one_person_dnd.launcher.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.launcher.load_server_config", return_value=ServerConfig()),
                patch("one_person_dnd.launcher.create_app", return_value=object()),
                patch("one_person_dnd.launcher.uvicorn.run") as run_server,
                redirect_stderr(stderr),
                self.assertRaises(SystemExit) as raised,
            ):
                main(["--host", "0.0.0.0", "--no-browser"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--allow-non-loopback", stderr.getvalue())
        run_server.assert_not_called()

    def test_explicit_opt_in_allows_non_loopback_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            paths = AppPaths(
                project_root=root,
                app_dir=root / ".one_person_dnd",
                config_path=root / "api_config.ini",
                db_path=root / ".one_person_dnd" / "one_person_dnd.sqlite3",
            )
            app = object()
            with (
                patch("one_person_dnd.launcher.ensure_app_dirs", return_value=paths),
                patch("one_person_dnd.launcher.load_server_config", return_value=ServerConfig()),
                patch("one_person_dnd.launcher.create_app", return_value=app),
                patch("one_person_dnd.launcher.uvicorn.run") as run_server,
            ):
                result = main(
                    [
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8123",
                        "--no-browser",
                        "--allow-non-loopback",
                    ]
                )

        self.assertEqual(result, 0)
        run_server.assert_called_once_with(app, host="0.0.0.0", port=8123, log_level="info")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    project_root: Path
    app_dir: Path
    config_path: Path
    db_path: Path


def get_app_paths() -> AppPaths:
    """
    Prefer project-local config for portability:

    - Config: <project_root>/api_config.ini
    - Runtime data (DB): <project_root>/.one_person_dnd/one_person_dnd.sqlite3
    """
    # one_person_dnd/paths.py -> project_root is its parent directory
    project_root = Path(__file__).resolve().parent.parent
    app_dir = project_root / ".one_person_dnd"

    return AppPaths(
        project_root=project_root,
        app_dir=app_dir,
        config_path=project_root / "api_config.ini",
        db_path=app_dir / "one_person_dnd.sqlite3",
    )


def ensure_app_dirs() -> AppPaths:
    paths = get_app_paths()
    paths.app_dir.mkdir(parents=True, exist_ok=True)
    return paths


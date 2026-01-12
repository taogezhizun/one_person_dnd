from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from one_person_dnd.config import AppState, load_app_state, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import campaigns, sessions
from one_person_dnd.paths import ensure_app_dirs

WEB_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def ensure_default_campaign_session() -> tuple[int, int]:
    """
    Ensure at least one campaign + one session exists.
    Return (campaign_id, session_id) of the first ones.
    """
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        campaign_id = campaigns.get_first_campaign_id(conn)
        if campaign_id is None:
            campaign_id = campaigns.create_campaign(conn, "默认战役")
            session_id = sessions.create_session(
                conn, campaign_id=campaign_id, title="默认会话", current_scene="起始"
            )
            conn.commit()
            return campaign_id, session_id

        session_id = sessions.get_first_session_id(conn, campaign_id)
        if session_id is None:
            session_id = sessions.create_session(
                conn, campaign_id=campaign_id, title="默认会话", current_scene="起始"
            )
            conn.commit()
            return campaign_id, session_id
        return campaign_id, session_id
    finally:
        conn.close()


def get_current_campaign_session() -> tuple[int, int]:
    """
    Determine the currently selected (campaign_id, session_id) from api_config.ini [app].
    Falls back to the first campaign/session, creating defaults if necessary.
    """
    paths = ensure_app_dirs()
    default_campaign_id, _default_session_id = ensure_default_campaign_session()
    state = load_app_state(paths.config_path)

    conn = get_connection(paths.db_path)
    try:
        campaign_id = state.active_campaign_id or default_campaign_id
        if not campaigns.campaign_exists(conn, campaign_id):
            campaign_id = default_campaign_id

        session_id = state.active_session_id
        if session_id is not None:
            if sessions.session_exists_under_campaign(conn, session_id=session_id, campaign_id=campaign_id):
                return campaign_id, session_id

        session_id = sessions.get_first_session_id(conn, campaign_id)
        if session_id is None:
            session_id = sessions.create_session(
                conn, campaign_id=campaign_id, title="默认会话", current_scene="起始"
            )
            conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return campaign_id, session_id


from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.config import AppState, load_llm_config, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import campaigns, sessions
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_llm_config(paths.config_path)
    campaign_id, session_id = get_current_campaign_session()

    conn = get_connection(paths.db_path)
    try:
        campaign_name = campaigns.get_campaign_name(conn, campaign_id) or ""
        session_title = sessions.get_session_title(conn, session_id) or ""
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "llm_configured": llm_cfg is not None,
            "config_filename": paths.config_path.name,
            "campaign_id": campaign_id,
            "session_id": session_id,
            "campaign_name": campaign_name,
            "session_title": session_title,
        },
    )


@router.get("/saves", response_class=HTMLResponse)
def saves(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    current_campaign_id, current_session_id = get_current_campaign_session()

    conn = get_connection(paths.db_path)
    try:
        campaigns_list = campaigns.list_campaigns(conn)
        sessions_list = sessions.list_sessions(conn, current_campaign_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="saves.html",
        context={
            "campaigns": campaigns_list,
            "sessions": sessions_list,
            "current_campaign_id": current_campaign_id,
            "current_session_id": current_session_id,
        },
    )


@router.post("/saves/campaign/new")
def saves_campaign_new(name: str = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        campaign_id = campaigns.create_campaign(conn, name.strip())
        session_id = sessions.create_session(
            conn, campaign_id=campaign_id, title="默认会话", current_scene="起始"
        )
        conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/campaign/select")
def saves_campaign_select(campaign_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        session_id = sessions.get_first_session_id(conn, campaign_id)
        if session_id is None:
            session_id = sessions.create_session(
                conn, campaign_id=campaign_id, title="默认会话", current_scene="起始"
            )
            conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/campaign/enter")
def saves_campaign_enter(campaign_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        session_id = sessions.get_first_session_id(conn, campaign_id)
        if session_id is None:
            session_id = sessions.create_session(
                conn, campaign_id=campaign_id, title="默认会话", current_scene="起始"
            )
            conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/game", status_code=303)


@router.post("/saves/session/new")
def saves_session_new(title: str = Form(...), current_scene: str = Form("起始")) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, _session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        session_id = sessions.create_session(
            conn,
            campaign_id=campaign_id,
            title=title.strip(),
            current_scene=(current_scene or "").strip(),
        )
        conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/session/select")
def saves_session_select(session_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, _old = get_current_campaign_session()
    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/session/enter")
def saves_session_enter(session_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        campaign_id = sessions.get_session_campaign_id(conn, session_id)
        if campaign_id is None:
            campaign_id, session_id2 = get_current_campaign_session()
            save_app_state(
                paths.config_path,
                AppState(active_campaign_id=campaign_id, active_session_id=session_id2),
            )
            return RedirectResponse(url="/game", status_code=303)
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/game", status_code=303)


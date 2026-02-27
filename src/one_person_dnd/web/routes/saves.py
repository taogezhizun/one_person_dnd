from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.config import AppState, load_llm_config, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import (
    campaigns,
    character_sheets,
    manual_change_logs,
    session_snapshots,
    sessions,
)
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
        snapshots_map: dict[int, list[dict]] = {}
        for s in sessions_list:
            sid = int(s["id"])
            snapshots_map[sid] = session_snapshots.list_snapshots(conn, session_id=sid, limit=5)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="saves.html",
        context={
            "campaigns": campaigns_list,
            "sessions": sessions_list,
            "snapshots_map": snapshots_map,
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


@router.post("/saves/session/snapshot")
def saves_session_snapshot(
    session_id: int = Form(...),
    snapshot_name: str = Form(""),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, _current_session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        if not sessions.session_exists_under_campaign(conn, session_id=session_id, campaign_id=campaign_id):
            return RedirectResponse(url="/saves", status_code=303)
        srow = sessions.get_session_sidebar(conn, session_id)
        if srow is None:
            return RedirectResponse(url="/saves", status_code=303)
        row = conn.execute(
            "SELECT COALESCE(MAX(turn_index), -1) AS max_turn FROM turn_logs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        turn_index = max(0, int(row["max_turn"] if row is not None else 0))
        session_snapshots.create_snapshot(
            conn,
            session_id=session_id,
            snapshot_name=(snapshot_name or "").strip() or "手动快照",
            turn_index=turn_index,
            current_scene=(srow["current_scene"] or "").strip(),
            session_state=(srow["session_state"] or "").strip(),
            pinned_world_notes=(srow["pinned_world_notes"] or "").strip(),
            character_sheet_json=character_sheets.get_character_sheet(conn, session_id=session_id),
        )
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="snapshot_create",
            detail_json_text=json.dumps(
                {"snapshot_name": (snapshot_name or "").strip() or "手动快照", "turn_index": turn_index},
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/session/restore")
def saves_session_restore(
    session_id: int = Form(...),
    snapshot_id: int = Form(...),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, _current_session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        if not sessions.session_exists_under_campaign(conn, session_id=session_id, campaign_id=campaign_id):
            return RedirectResponse(url="/saves", status_code=303)
        snap = session_snapshots.get_snapshot(conn, snapshot_id=snapshot_id)
        if not snap or int(snap["session_id"]) != int(session_id):
            return RedirectResponse(url="/saves", status_code=303)
        sessions.update_session_from_snapshot(
            conn,
            campaign_id=campaign_id,
            session_id=session_id,
            current_scene=(snap.get("current_scene") or "").strip(),
            session_state=(snap.get("session_state") or "").strip(),
            pinned_world_notes=(snap.get("pinned_world_notes") or "").strip(),
        )
        character_sheets.upsert_character_sheet(
            conn,
            session_id=session_id,
            json_text=(snap.get("character_sheet_json") or "").strip(),
        )
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="snapshot_restore",
            detail_json_text=json.dumps(
                {"snapshot_id": int(snapshot_id), "snapshot_name": (snap.get("snapshot_name") or "")},
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/game", status_code=303)


@router.post("/saves/session/fork")
def saves_session_fork(
    session_id: int = Form(...),
    snapshot_id: int = Form(...),
    fork_title: str = Form(""),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, _current_session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        if not sessions.session_exists_under_campaign(conn, session_id=session_id, campaign_id=campaign_id):
            return RedirectResponse(url="/saves", status_code=303)
        snap = session_snapshots.get_snapshot(conn, snapshot_id=snapshot_id)
        if not snap or int(snap["session_id"]) != int(session_id):
            return RedirectResponse(url="/saves", status_code=303)

        new_title = (fork_title or "").strip() or f"{(snap.get('snapshot_name') or '分叉').strip()}-分叉"
        new_session_id = sessions.create_session(
            conn,
            campaign_id=campaign_id,
            title=new_title,
            current_scene=(snap.get("current_scene") or "").strip(),
            parent_session_id=session_id,
        )
        sessions.update_session_from_snapshot(
            conn,
            campaign_id=campaign_id,
            session_id=new_session_id,
            current_scene=(snap.get("current_scene") or "").strip(),
            session_state=(snap.get("session_state") or "").strip(),
            pinned_world_notes=(snap.get("pinned_world_notes") or "").strip(),
        )
        character_sheets.upsert_character_sheet(
            conn,
            session_id=new_session_id,
            json_text=(snap.get("character_sheet_json") or "").strip(),
        )
        manual_change_logs.insert_log(
            conn,
            session_id=new_session_id,
            actor="player",
            change_type="snapshot_fork",
            detail_json_text=json.dumps(
                {
                    "source_session_id": int(session_id),
                    "snapshot_id": int(snapshot_id),
                    "snapshot_name": (snap.get("snapshot_name") or ""),
                },
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=new_session_id))
    return RedirectResponse(url="/game", status_code=303)


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


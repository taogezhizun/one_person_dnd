from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from one_person_dnd.config import AppState, load_llm_config, load_memory_config, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import campaigns, sessions, turn_logs
from one_person_dnd.engine import run_turn
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import LLMClientError
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()


@router.get("/game", response_class=HTMLResponse)
def game(request: Request) -> HTMLResponse:
    campaign_id, session_id = get_current_campaign_session()
    paths = ensure_app_dirs()

    conn = get_connection(paths.db_path)
    try:
        campaign_name = campaigns.get_campaign_name(conn, campaign_id) or ""
        s = sessions.get_session_sidebar(conn, session_id)
        session_title = s["title"] if s else ""
        current_scene = s["current_scene"] if s else ""
        session_state = s["session_state"] if s and "session_state" in s.keys() else ""
        pinned_world_notes = s["pinned_world_notes"] if s and "pinned_world_notes" in s.keys() else ""

        rows = turn_logs.list_turn_logs(conn, session_id=session_id, limit=50)
        turns = []
        for r in rows[::-1]:
            dm = parse_dm_text((r.get("dm_text") or "").strip())
            turns.append(
                {
                    "turn_index": int(r["turn_index"]),
                    "player_text": (r.get("player_text") or ""),
                    "dm": dm,
                    "created_at": (r.get("created_at") or ""),
                }
            )
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="game.html",
        context={
            "campaign_id": campaign_id,
            "session_id": session_id,
            "campaign_name": campaign_name,
            "session_title": session_title,
            "current_scene": current_scene,
            "session_state": session_state or "",
            "pinned_world_notes": pinned_world_notes or "",
            "turns": turns,
        },
    )


@router.post("/game/turn", response_class=HTMLResponse)
def game_turn(
    request: Request,
    campaign_id: int = Form(...),
    session_id: int = Form(...),
    player_text: str = Form(...),
    tags: str = Form(""),
    state_block: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_llm_config(paths.config_path)
    if llm_cfg is None:
        return templates.TemplateResponse(
            request=request,
            name="partials/test_result.html",
            context={"ok": False, "message": "LLM 未配置，请先在 /setup 配置。"},
        )

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))

    conn = get_connection(paths.db_path)
    try:
        srow = sessions.get_session_sidebar(conn, session_id)
        session_title = srow["title"] if srow else ""
        current_scene = srow["current_scene"] if srow else ""
        session_state = srow["session_state"] if srow and "session_state" in srow.keys() else ""
        pinned_world_notes = srow["pinned_world_notes"] if srow and "pinned_world_notes" in srow.keys() else ""
    finally:
        conn.close()

    state_parts = []
    if current_scene:
        state_parts.append(f"当前场景：{current_scene}")
    if session_title:
        state_parts.append(f"会话：{session_title}")
    if pinned_world_notes:
        state_parts.append("【置顶世界设定】\n" + pinned_world_notes)
    if session_state:
        state_parts.append("【主角/队伍状态】\n" + session_state)
    if (state_block or "").strip():
        state_parts.append("【本回合额外上下文】\n" + (state_block or "").strip())
    merged_state_block = "\n\n".join(state_parts).strip()

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    try:
        memory_cfg = load_memory_config(paths.config_path)
        result = run_turn(
            db_path=paths.db_path,
            llm_cfg=llm_cfg,
            campaign_id=campaign_id,
            session_id=session_id,
            player_text=player_text,
            state_block=merged_state_block,
            tags=tag_list or None,
            memory_cfg=memory_cfg,
        )

        return templates.TemplateResponse(
            request=request,
            name="partials/chat_turn_append.html",
            context={
                "turn": {
                    "turn_index": result.turn_index,
                    "player_text": player_text,
                    "dm": result.dm,
                },
                "recalled_world": result.recalled_world,
            },
        )
    except LLMClientError as e:
        return templates.TemplateResponse(
            request=request,
            name="partials/chat_turn_error_append.html",
            context={"player_text": player_text, "message": str(e)},
        )


@router.post("/game/session/update", response_class=HTMLResponse)
def game_session_update(
    request: Request,
    campaign_id: int = Form(...),
    session_id: int = Form(...),
    current_scene: str = Form(""),
    session_state: str = Form(""),
    pinned_world_notes: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        sessions.update_session_sidebar(
            conn,
            campaign_id=campaign_id,
            session_id=session_id,
            current_scene=(current_scene or "").strip(),
            session_state=(session_state or "").strip(),
            pinned_world_notes=(pinned_world_notes or "").strip(),
        )
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="partials/save_ok.html",
        context={"message": "已保存"},
    )


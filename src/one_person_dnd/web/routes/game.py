from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from one_person_dnd.config import AppState, load_llm_config, load_memory_config, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import campaigns, sessions, turn_logs
from one_person_dnd.engine.orchestrator import build_turn_messages_and_preview, persist_turn
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import LLMClientError, create_llm_client
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()
logger = logging.getLogger("one_person_dnd.web")


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
        # Keep non-streaming endpoint for fallback/compat.
        # We build messages/persist via orchestrator to share logic with streaming.
        conn = get_connection(paths.db_path)
        try:
            t0 = time.perf_counter()
            messages, recalled_world = build_turn_messages_and_preview(
                conn,
                campaign_id=campaign_id,
                session_id=session_id,
                player_text=player_text,
                state_block=merged_state_block,
                tags=tag_list or None,
                memory_cfg=memory_cfg,
            )
            t_prompt = time.perf_counter()
            msg_count = len(messages)
            prompt_chars = sum(len(m.content or "") for m in messages)

            client = create_llm_client(llm_cfg)
            dm_raw = client.chat(messages)
            t_llm = time.perf_counter()
            dm_struct = parse_dm_text(dm_raw)
            t_parse = time.perf_counter()

            result = persist_turn(
                conn,
                session_id=session_id,
                player_text=player_text,
                dm_raw=dm_raw,
                dm_struct=dm_struct,
                recalled_world=recalled_world,
            )
            conn.commit()
            t_persist = time.perf_counter()

            logger.info(
                "turn_done web_non_stream session=%s turn=%s prompt_chars=%s msg_count=%s prompt_ms=%s llm_ms=%s parse_ms=%s persist_ms=%s total_ms=%s",
                session_id,
                result.turn_index,
                prompt_chars,
                msg_count,
                int((t_prompt - t0) * 1000),
                int((t_llm - t_prompt) * 1000),
                int((t_parse - t_llm) * 1000),
                int((t_persist - t_parse) * 1000),
                int((t_persist - t0) * 1000),
            )
        finally:
            conn.close()

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


@router.post("/game/turn/stream")
def game_turn_stream(
    request: Request,
    campaign_id: int = Form(...),
    session_id: int = Form(...),
    player_text: str = Form(...),
    tags: str = Form(""),
    state_block: str = Form(""),
):
    """
    Server->browser SSE stream. Emits:
      event: delta  data: {"text": "..."}
      event: final  data: {"turn": {...}, "recalled_world":[...]}
      event: error  data: {"message":"..."}
    """
    from starlette.responses import StreamingResponse

    paths = ensure_app_dirs()
    llm_cfg = load_llm_config(paths.config_path)
    if llm_cfg is None:
        return StreamingResponse(
            iter([('event: error\ndata: {"message":"LLM 未配置，请先在 /setup 配置。"}\n\n').encode("utf-8")]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))

    # Load session sidebar info and inject into state for DM (same as non-streaming).
    conn0 = get_connection(paths.db_path)
    try:
        srow = sessions.get_session_sidebar(conn0, session_id)
        session_title = srow["title"] if srow else ""
        current_scene = srow["current_scene"] if srow else ""
        session_state = srow["session_state"] if srow and "session_state" in srow.keys() else ""
        pinned_world_notes = srow["pinned_world_notes"] if srow and "pinned_world_notes" in srow.keys() else ""
    finally:
        conn0.close()

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
    memory_cfg = load_memory_config(paths.config_path)

    def _sse(event: str, payload: dict) -> bytes:
        data = json.dumps(payload, ensure_ascii=False)
        return f"event: {event}\ndata: {data}\n\n".encode("utf-8")

    def _gen():
        t0 = time.perf_counter()
        first_token_ms: int | None = None
        dm_parts: list[str] = []
        try:
            conn = get_connection(paths.db_path)
            try:
                messages, recalled_world = build_turn_messages_and_preview(
                    conn,
                    campaign_id=campaign_id,
                    session_id=session_id,
                    player_text=player_text,
                    state_block=merged_state_block,
                    tags=tag_list or None,
                    memory_cfg=memory_cfg,
                )
                t_prompt = time.perf_counter()
                msg_count = len(messages)
                prompt_chars = sum(len(m.content or "") for m in messages)

                client = create_llm_client(llm_cfg)
                for delta in client.chat_stream_sse(messages):
                    if first_token_ms is None:
                        first_token_ms = int((time.perf_counter() - t0) * 1000)
                    dm_parts.append(delta)
                    yield _sse("delta", {"text": delta})

                dm_raw = "".join(dm_parts)
                t_llm = time.perf_counter()
                dm_struct = parse_dm_text(dm_raw)
                t_parse = time.perf_counter()

                result = persist_turn(
                    conn,
                    session_id=session_id,
                    player_text=player_text,
                    dm_raw=dm_raw,
                    dm_struct=dm_struct,
                    recalled_world=recalled_world,
                )
                conn.commit()
                t_persist = time.perf_counter()

                logger.info(
                    "turn_done web_stream session=%s turn=%s prompt_chars=%s msg_count=%s first_token_ms=%s prompt_ms=%s llm_ms=%s parse_ms=%s persist_ms=%s total_ms=%s",
                    session_id,
                    result.turn_index,
                    prompt_chars,
                    msg_count,
                    first_token_ms if first_token_ms is not None else -1,
                    int((t_prompt - t0) * 1000),
                    int((t_llm - t_prompt) * 1000),
                    int((t_parse - t_llm) * 1000),
                    int((t_persist - t_parse) * 1000),
                    int((t_persist - t0) * 1000),
                )

                yield _sse(
                    "final",
                    {
                        "turn": {
                            "turn_index": result.turn_index,
                            "player_text": player_text,
                            "dm": {
                                "narration": result.dm.narration,
                                "choices": result.dm.choices,
                                "dm_notes": result.dm.dm_notes,
                                "memory_suggestions": result.dm.memory_suggestions,
                            },
                        },
                        "recalled_world": result.recalled_world,
                    },
                )
            finally:
                conn.close()
        except GeneratorExit:
            # client disconnected / cancelled; do not persist partial results
            return
        except LLMClientError as e:
            yield _sse("error", {"message": str(e)})
        except Exception as e:
            yield _sse("error", {"message": f"stream failed: {e}"})

    return StreamingResponse(_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


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


from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import character_sheets, state_change_requests
from one_person_dnd.engine.guardrails import GuardrailError, validate_state_delta_json
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()

def _render_panel(request: Request, *, session_id: int, notice_message: str = "") -> HTMLResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        sheet = character_sheets.get_character_sheet(conn, session_id=session_id)
        pending = state_change_requests.list_pending(conn, session_id=session_id, limit=50)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="partials/character_panel.html",
        context={
            "session_id": session_id,
            "character_sheet": sheet,
            "pending_changes": pending,
            "notice_message": notice_message,
        },
    )


@router.get("/character/panel", response_class=HTMLResponse)
def character_panel(request: Request) -> HTMLResponse:
    _campaign_id, session_id = get_current_campaign_session()
    return _render_panel(request, session_id=session_id)


@router.post("/character/save", response_class=HTMLResponse)
def character_save(
    request: Request,
    character_sheet: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=(character_sheet or "").strip())
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="partials/save_ok.html",
        context={"message": "角色卡已保存"},
    )


def _deep_merge(base: Any, delta: Any) -> Any:
    if isinstance(base, dict) and isinstance(delta, dict):
        out = dict(base)
        for k, v in delta.items():
            if k in out:
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
        return out
    # for lists/scalars: replace
    return delta


@router.post("/character/change/apply")
def change_apply(request: Request, request_id: int = Form(...)) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        req = state_change_requests.get_request(conn, request_id=int(request_id), session_id=session_id)
        if req is None:
            return _render_panel(request, session_id=session_id, notice_message="未找到该变更请求（可能已处理）。")

        kind = (req.get("kind") or "").strip()
        if kind != "state_delta":
            # For MVP we only auto-apply state_delta. Thread updates stay manual in /threads.
            state_change_requests.set_status(
                conn, request_id=int(request_id), session_id=session_id, status="rejected", error_text="暂不支持自动应用该类型"
            )
            conn.commit()
            return _render_panel(request, session_id=session_id, notice_message="已拒绝：暂不支持自动应用该类型。")

        delta_text = (req.get("delta_json_text") or "").strip()
        try:
            delta = validate_state_delta_json(delta_text)
        except GuardrailError as e:
            state_change_requests.set_status(
                conn, request_id=int(request_id), session_id=session_id, status="rejected", error_text=str(e)
            )
            conn.commit()
            return _render_panel(request, session_id=session_id, notice_message=f"已拒绝：{e}")

        base_text = character_sheets.get_character_sheet(conn, session_id=session_id).strip()
        base_obj: dict[str, Any] = {}
        if base_text:
            try:
                base_loaded = json.loads(base_text)
                if isinstance(base_loaded, dict):
                    base_obj = base_loaded
            except Exception:
                base_obj = {}

        merged = _deep_merge(base_obj, delta)
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=json.dumps(merged, ensure_ascii=False, indent=2))
        state_change_requests.set_status(conn, request_id=int(request_id), session_id=session_id, status="applied")
        conn.commit()
    finally:
        conn.close()

    return _render_panel(request, session_id=session_id, notice_message="已应用变更。")


@router.post("/character/change/reject")
def change_reject(request: Request, request_id: int = Form(...)) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        state_change_requests.set_status(conn, request_id=int(request_id), session_id=session_id, status="rejected")
        conn.commit()
    finally:
        conn.close()
    return _render_panel(request, session_id=session_id, notice_message="已拒绝变更。")


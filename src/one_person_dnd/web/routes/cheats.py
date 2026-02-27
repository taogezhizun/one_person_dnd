from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import manual_change_logs, session_cheats
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()


def _is_truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


@router.post("/cheats/save", response_class=HTMLResponse)
def cheats_save(
    request: Request,
    session_id: int = Form(...),
    enabled: str = Form(""),
    cheat_prompt: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, current_session_id = get_current_campaign_session()
    target_session_id = current_session_id
    enabled_bool = _is_truthy(enabled)
    prompt = (cheat_prompt or "").strip()

    conn = get_connection(paths.db_path)
    try:
        session_cheats.upsert_cheat(
            conn,
            session_id=target_session_id,
            enabled=enabled_bool,
            cheat_prompt=prompt,
        )
        manual_change_logs.insert_log(
            conn,
            session_id=target_session_id,
            actor="player",
            change_type="cheat_update",
            detail_json_text=json.dumps(
                {
                    "requested_session_id": int(session_id),
                    "effective_session_id": target_session_id,
                    "enabled": enabled_bool,
                    "cheat_prompt": prompt,
                },
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="partials/save_ok.html",
        context={"message": "金手指设置已保存"},
    )


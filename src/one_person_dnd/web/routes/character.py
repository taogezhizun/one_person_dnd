from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import character_sheets, manual_change_logs, state_change_requests
from one_person_dnd.domain.characters import summarize_character_sheet
from one_person_dnd.domain.state_changes import StateChangePreview, merge_state_delta, preview_state_delta
from one_person_dnd.domain.thread_updates import apply_thread_updates_json, preview_thread_updates_json
from one_person_dnd.engine.guardrails import GuardrailError, validate_state_delta_json
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()


def _to_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _extract_quick_stats(sheet_text: str) -> dict[str, int | None]:
    summary = summarize_character_sheet(sheet_text)
    return {"hp": summary.hp, "gold": summary.gold}


def _has_top_level_character_fields(obj: dict[str, Any]) -> bool:
    return any(
        key in obj
        for key in (
            "name",
            "race",
            "ancestry",
            "species",
            "class",
            "job",
            "profession",
            "background",
            "goal",
            "hp",
            "max_hp",
            "hp_max",
            "gold",
            "inventory",
            "abilities",
            "ability_scores",
            "conditions",
            "notes",
        )
    )


def _primary_character_target(obj: dict[str, Any]) -> dict[str, Any]:
    party = obj.get("party")
    if isinstance(party, list):
        if party and isinstance(party[0], dict):
            return party[0]
        if not party:
            party.append({})
            return party[0]

    if _has_top_level_character_fields(obj):
        return obj

    obj["party"] = [{}]
    return obj["party"][0]


def _split_text_list(value: str) -> list[str]:
    normalized = (value or "").replace("，", ",")
    parts: list[str] = []
    for line in normalized.splitlines():
        for item in line.split(","):
            item = item.strip()
            if item:
                parts.append(item)
    return parts


def _with_change_previews(sheet_text: str, pending: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in pending:
        row = dict(item)
        if (row.get("kind") or "").strip() == "state_delta":
            row["preview"] = preview_state_delta(sheet_text, row.get("delta_json_text") or "")
        elif (row.get("kind") or "").strip() == "thread_updates":
            row["preview"] = preview_thread_updates_json(row.get("delta_json_text") or "")
        else:
            row["preview"] = StateChangePreview(
                ok=True,
                summary="剧情线更新建议",
                lines=["暂不支持自动应用，请到剧情线页面手动处理。"],
            )
        out.append(row)
    return out


def _render_panel(request: Request, *, session_id: int, notice_message: str = "") -> HTMLResponse:
    paths = ensure_app_dirs()
    conn = get_connection(paths.db_path)
    try:
        sheet = character_sheets.get_character_sheet(conn, session_id=session_id)
        pending = _with_change_previews(sheet, state_change_requests.list_pending(conn, session_id=session_id, limit=50))
        character_summary = summarize_character_sheet(sheet)
        quick_stats = _extract_quick_stats(sheet)
    finally:
        conn.close()
    pending_count = len(pending)

    return templates.TemplateResponse(
        request=request,
        name="partials/character_panel.html",
        context={
            "session_id": session_id,
            "character_sheet": sheet,
            "character_summary": character_summary,
            "quick_stats": quick_stats,
            "pending_changes": pending,
            "pending_count": pending_count,
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
        saved_text = (character_sheet or "").strip()
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=saved_text)
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="character_sheet_save",
            detail_json_text=json.dumps(
                {"length": len(saved_text)},
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="partials/save_ok.html",
        context={"message": "角色卡已保存"},
    )


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
        if kind == "thread_updates":
            try:
                applied = apply_thread_updates_json(
                    conn,
                    session_id=session_id,
                    delta_json_text=(req.get("delta_json_text") or "").strip(),
                )
            except GuardrailError as e:
                state_change_requests.set_status(
                    conn, request_id=int(request_id), session_id=session_id, status="rejected", error_text=str(e)
                )
                conn.commit()
                return _render_panel(request, session_id=session_id, notice_message=f"已拒绝：{e}")

            state_change_requests.set_status(conn, request_id=int(request_id), session_id=session_id, status="applied")
            manual_change_logs.insert_log(
                conn,
                session_id=session_id,
                actor="player",
                change_type="apply_thread_updates",
                detail_json_text=json.dumps(
                    {"request_id": int(request_id), "applied": applied},
                    ensure_ascii=False,
                ),
            )
            conn.commit()
            return _render_panel(request, session_id=session_id, notice_message="已应用剧情线更新。")

        if kind != "state_delta":
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

        merged = merge_state_delta(base_obj, delta)
        merged_text = json.dumps(merged, ensure_ascii=False, indent=2)
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=merged_text)
        state_change_requests.set_status(conn, request_id=int(request_id), session_id=session_id, status="applied")
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="apply_state_delta",
            detail_json_text=json.dumps(
                {"request_id": int(request_id), "delta": delta},
                ensure_ascii=False,
            ),
        )
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


@router.post("/character/quick_adjust", response_class=HTMLResponse)
def character_quick_adjust(
    request: Request,
    hp_delta: int = Form(0),
    gold_delta: int = Form(0),
    reason: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        raw = character_sheets.get_character_sheet(conn, session_id=session_id).strip()
        try:
            obj = json.loads(raw) if raw else {}
        except Exception:
            obj = {}
        if not isinstance(obj, dict):
            obj = {}

        member = _primary_character_target(obj)
        current_hp = _to_int(member.get("hp")) or 0
        current_gold = _to_int(member.get("gold")) or 0
        new_hp = current_hp + int(hp_delta or 0)
        new_gold = current_gold + int(gold_delta or 0)
        member["hp"] = new_hp
        member["gold"] = new_gold

        updated = json.dumps(obj, ensure_ascii=False, indent=2)
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=updated)
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="quick_adjust",
            detail_json_text=json.dumps(
                {
                    "hp_delta": int(hp_delta or 0),
                    "gold_delta": int(gold_delta or 0),
                    "from": {"hp": current_hp, "gold": current_gold},
                    "to": {"hp": new_hp, "gold": new_gold},
                    "reason": (reason or "").strip(),
                },
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return _render_panel(request, session_id=session_id, notice_message="已应用快速改值。")


@router.post("/character/quick_state", response_class=HTMLResponse)
def character_quick_state(
    request: Request,
    conditions_text: str = Form(""),
    notes_text: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        raw = character_sheets.get_character_sheet(conn, session_id=session_id).strip()
        try:
            obj = json.loads(raw) if raw else {}
        except Exception:
            obj = {}
        if not isinstance(obj, dict):
            obj = {}

        member = _primary_character_target(obj)
        member["conditions"] = _split_text_list(conditions_text)
        member["notes"] = (notes_text or "").strip()

        updated = json.dumps(obj, ensure_ascii=False, indent=2)
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=updated)
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="quick_state",
            detail_json_text=json.dumps(
                {
                    "conditions": member["conditions"],
                    "notes_length": len(member["notes"]),
                },
                ensure_ascii=False,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return _render_panel(request, session_id=session_id, notice_message="已保存状态备注。")

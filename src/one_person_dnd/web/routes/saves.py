from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.config import AppState, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import (
    adjudication_records,
    campaigns,
    character_sheets,
    manual_change_logs,
    plot_threads,
    session_snapshots,
    sessions,
    state_change_requests,
    story_journal,
    summaries,
    turn_logs,
)
from one_person_dnd.domain.characters import summarize_character_sheet
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, load_active_llm_config, templates

router = APIRouter()


def _capture_narrative_json(conn, *, session_id: int) -> str:
    """
    Serialize the session's entire current narrative (all turn_logs,
    story_journal_entries, plot_threads, session_summaries rows) so a later
    restore can transactionally replace the session's narrative with this
    exact captured set, not just scene/character state. See
    `_restore_narrative` for the inverse operation.
    """
    return json.dumps(
        {
            "turn_logs": turn_logs.list_all_for_session(conn, session_id=session_id),
            "story_journal_entries": story_journal.list_all_for_session(conn, session_id=session_id),
            "plot_threads": plot_threads.list_all_for_session(conn, session_id=session_id),
            "session_summaries": summaries.list_all_for_session(conn, session_id=session_id),
        },
        ensure_ascii=False,
    )


def _normalize_restored_adjudication_json(raw: object) -> tuple[str | None, str | None]:
    """Return snapshot JSON plus its canonical fingerprint when replay-safe.

    Early v10 snapshots used ``fingerprint`` inside the serialized record.
    The current domain object requires ``request_fingerprint``. Normalize that
    compatibility key before restoring either turn history or the ledger so a
    valid old record remains readable and replayable after a rewind.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    try:
        record = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw, None
    if not isinstance(record, dict):
        return raw, None

    fingerprint = record.get("request_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        legacy_fingerprint = record.get("fingerprint")
        if not isinstance(legacy_fingerprint, str) or not legacy_fingerprint.strip():
            return raw, None
        fingerprint = legacy_fingerprint.strip()
        record["request_fingerprint"] = fingerprint
        raw = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw, fingerprint.strip()


def _restore_narrative(conn, *, session_id: int, narrative_json: str) -> None:
    """
    Replace the session's turn_logs/story_journal_entries/plot_threads/
    session_summaries with a snapshot's captured narrative, and drop pending
    state_change_requests (they may reference turn/thread state that no
    longer exists after the rewind). The adjudication ledger is rebuilt only
    from restored turn logs whose adjudication JSON carries its original
    fingerprint; old records without one are skipped rather than assigned a
    fabricated replay identity. Applied/rejected requests are left intact as
    an audit trail. Caller owns the transaction (commit/rollback).
    """
    data = json.loads(narrative_json)
    adjudication_records.delete_all_for_session(conn, session_id=session_id)
    turn_logs.delete_all_for_session(conn, session_id=session_id)
    restored_turn_rows: list[dict] = []
    for original_turn in data.get("turn_logs", []):
        turn = dict(original_turn)
        normalized_json, _fingerprint = _normalize_restored_adjudication_json(
            turn.get("adjudication_json")
        )
        if normalized_json is not None:
            turn["adjudication_json"] = normalized_json
        restored_turn_rows.append(turn)
    turn_logs.bulk_insert(conn, session_id=session_id, rows=restored_turn_rows)
    for turn in turn_logs.list_all_for_session(conn, session_id=session_id):
        attempt_id = turn.get("attempt_id")
        record_json, fingerprint = _normalize_restored_adjudication_json(
            turn.get("adjudication_json")
        )
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            continue
        if not isinstance(record_json, str) or not record_json.strip():
            continue
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            continue
        adjudication_records.create(
            conn,
            session_id=session_id,
            attempt_id=attempt_id,
            fingerprint=fingerprint.strip(),
            record_json=record_json,
            turn_index=int(turn["turn_index"]),
        )
    story_journal.delete_all_for_session(conn, session_id=session_id)
    story_journal.bulk_insert(conn, session_id=session_id, rows=data.get("story_journal_entries", []))
    plot_threads.delete_all_for_session(conn, session_id=session_id)
    plot_threads.bulk_insert(conn, session_id=session_id, rows=data.get("plot_threads", []))
    summaries.delete_all_for_session(conn, session_id=session_id)
    summaries.bulk_insert(conn, session_id=session_id, rows=data.get("session_summaries", []))
    state_change_requests.delete_all_pending_for_session(conn, session_id=session_id)


def _create_session_snapshot(
    conn,
    *,
    session_id: int,
    snapshot_name: str,
) -> tuple[int, int] | None:
    session_row = sessions.get_session_sidebar(conn, session_id)
    if session_row is None:
        return None
    row = conn.execute(
        "SELECT COALESCE(MAX(turn_index), -1) AS max_turn FROM turn_logs WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    turn_index = max(0, int(row["max_turn"] if row is not None else 0))
    snapshot_id = session_snapshots.create_snapshot(
        conn,
        session_id=session_id,
        snapshot_name=snapshot_name,
        turn_index=turn_index,
        current_scene=(session_row["current_scene"] or "").strip(),
        session_state=(session_row["session_state"] or "").strip(),
        pinned_world_notes=(session_row["pinned_world_notes"] or "").strip(),
        character_sheet_json=character_sheets.get_character_sheet(conn, session_id=session_id),
        narrative_json=_capture_narrative_json(conn, session_id=session_id),
    )
    return snapshot_id, turn_index


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_active_llm_config()
    campaign_id, session_id = get_current_campaign_session()

    conn = get_connection(paths.db_path)
    try:
        campaign_name = campaigns.get_campaign_name(conn, campaign_id) or ""
        session_title = sessions.get_session_title(conn, session_id) or ""
        session_row = sessions.get_session_sidebar(conn, session_id)
        current_scene = (session_row["current_scene"] or "").strip() if session_row else ""
        current_session = next(
            (item for item in sessions.list_sessions(conn, campaign_id) if int(item["id"]) == int(session_id)),
            {},
        )
        last_played_at = current_session.get("last_played_at") or current_session.get("created_at") or ""
        character = summarize_character_sheet(
            character_sheets.get_character_sheet(conn, session_id=session_id)
        )
        recent_turns = turn_logs.list_turn_logs(conn, session_id=session_id, limit=1)
        latest_narration = ""
        if recent_turns:
            latest_narration = parse_dm_text((recent_turns[0].get("dm_text") or "").strip()).narration.strip()
        journal_entries = story_journal.list_story_journal_entries(conn, session_id=session_id, limit=1)
        latest_story = latest_narration or (journal_entries[0].get("summary") if journal_entries else "") or ""
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
            "current_scene": current_scene,
            "last_played_at": last_played_at,
            "character": character,
            "latest_story": latest_story,
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
            snapshots_map[sid] = session_snapshots.list_snapshots(conn, session_id=sid, limit=50)
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
        final_snapshot_name = (snapshot_name or "").strip() or "手动快照"
        result = _create_session_snapshot(
            conn,
            session_id=session_id,
            snapshot_name=final_snapshot_name,
        )
        if result is None:
            return RedirectResponse(url="/saves", status_code=303)
        _snapshot_id, turn_index = result
        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="snapshot_create",
            detail_json_text=json.dumps(
                {"snapshot_name": final_snapshot_name, "turn_index": turn_index},
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
        target_name = (snap.get("snapshot_name") or "未命名快照").strip()
        safety_result = _create_session_snapshot(
            conn,
            session_id=session_id,
            snapshot_name=f"恢复前自动备份 · {target_name}",
        )
        if safety_result is None:
            return RedirectResponse(url="/saves", status_code=303)
        safety_snapshot_id, safety_turn_index = safety_result
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

        # Full rewind: replace turn_logs/story_journal_entries/plot_threads/
        # session_summaries with the snapshot's captured narrative, so the
        # whole session narrative (not just scene/character state) matches
        # the restored point. Snapshots taken before this feature existed
        # have narrative_json IS NULL; for those we deliberately fall back to
        # the legacy state-only restore above and leave turn_logs etc. alone
        # rather than deleting narrative we never captured a replacement for.
        narrative_json = snap.get("narrative_json")
        narrative_restored = bool(narrative_json)
        if narrative_restored:
            _restore_narrative(conn, session_id=session_id, narrative_json=narrative_json)

        manual_change_logs.insert_log(
            conn,
            session_id=session_id,
            actor="player",
            change_type="snapshot_restore",
            detail_json_text=json.dumps(
                {
                    "snapshot_id": int(snapshot_id),
                    "snapshot_name": target_name,
                    "safety_snapshot_id": safety_snapshot_id,
                    "safety_turn_index": safety_turn_index,
                    "narrative_restored": narrative_restored,
                },
                ensure_ascii=False,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
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

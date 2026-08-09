from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.adjudication import AdjudicationStoreCorrupt
from one_person_dnd.agents.pipeline import TurnPipeline
from one_person_dnd.config import AppState, load_memory_config, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import (
    app_settings,
    campaigns,
    plot_threads,
    session_cheats,
    sessions,
    state_change_requests,
    turn_logs,
    world_bible,
)
from one_person_dnd.engine.dice import roll_expr
from one_person_dnd.engine.orchestrator import ensure_dm_protocol_output
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.llm import LLMClientError, create_llm_client
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, load_active_llm_config, templates
from one_person_dnd.web.turn_errors import TURN_DOMAIN_ERRORS, public_turn_error
from one_person_dnd.web.turn_presenter import TurnPresenter

router = APIRouter()
logger = logging.getLogger("one_person_dnd.web")
WORLD_SETUP_SKIP_KEY_PREFIX = "world_setup_prompt_skipped.session."
turn_presenter = TurnPresenter()
_claim_clock = time.monotonic
_STREAM_CLAIM_RENEW_SECONDS = 60.0


def _world_setup_skip_key(session_id: int) -> str:
    return f"{WORLD_SETUP_SKIP_KEY_PREFIX}{session_id}"


def _world_setup_prompt_state(
    conn,
    *,
    campaign_id: int,
    session_id: int,
    pinned_world_notes: str,
) -> dict:
    has_world = world_bible.has_world_bible_entries(conn, campaign_id=campaign_id)
    has_pinned = bool((pinned_world_notes or "").strip())
    skipped = app_settings.get(conn, _world_setup_skip_key(session_id)) == "1"
    return {
        "show": not has_world and not has_pinned and not skipped,
        "has_world_bible": has_world,
        "has_pinned_world_notes": has_pinned,
        "skipped": skipped,
    }


def _build_turn_prompt_overrides(
    *,
    cheat_enabled: bool,
    cheat_prompt: str,
    state_block: str,
) -> tuple[str, str]:
    """
    Return only per-turn route overrides.

    Session title, current scene, pinned notes, and authoritative character state
    are read once by ContextPack assembly. Keeping the route override limited to
    the optional form field prevents duplicate prompt blocks.
    """
    turn_context = (state_block or "").strip()
    effective_cheat_prompt = (cheat_prompt or "").strip() if cheat_enabled else ""
    return turn_context, effective_cheat_prompt


def _turn_attempt_id(value: object) -> str:
    """Use a browser-stable id when present and a server id for legacy clients."""
    cleaned = value.strip() if isinstance(value, str) else ""
    return cleaned[:128] if cleaned else uuid.uuid4().hex


@router.get("/game", response_class=HTMLResponse)
def game(request: Request) -> HTMLResponse:
    campaign_id, session_id = get_current_campaign_session()
    paths = ensure_app_dirs()
    llm_configured = load_active_llm_config() is not None

    conn = get_connection(paths.db_path)
    try:
        campaign_name = campaigns.get_campaign_name(conn, campaign_id) or ""
        sessions_list = sessions.list_sessions(conn, campaign_id)
        s = sessions.get_session_sidebar(conn, session_id)
        session_title = s["title"] if s else ""
        current_scene = s["current_scene"] if s else ""
        session_state = s["session_state"] if s and "session_state" in s.keys() else ""
        pinned_world_notes = s["pinned_world_notes"] if s and "pinned_world_notes" in s.keys() else ""
        world_setup_prompt = _world_setup_prompt_state(
            conn,
            campaign_id=campaign_id,
            session_id=session_id,
            pinned_world_notes=pinned_world_notes or "",
        )
        world_bible_entries = world_bible.list_world_bible_entries(conn, campaign_id=campaign_id, limit=8)
        pending_count = len(state_change_requests.list_pending(conn, session_id=session_id, limit=200))
        open_threads = plot_threads.list_open_threads(conn, session_id=session_id, limit=6)
        cheat_cfg = session_cheats.get_cheat(conn, session_id=session_id) or {}
        cheat_enabled = bool(int(cheat_cfg.get("enabled") or 0))
        cheat_prompt = (cheat_cfg.get("cheat_prompt") or "").strip()

        rows = turn_logs.list_turn_logs(conn, session_id=session_id, limit=50)
        turns = turn_presenter.present_history(
            rows,
            campaign_id=campaign_id,
            session_id=session_id,
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
            "world_setup_prompt": world_setup_prompt,
            "world_bible_entries": world_bible_entries,
            "sessions_list": sessions_list,
            "pending_count": pending_count,
            "open_threads": open_threads,
            "cheat_enabled": cheat_enabled,
            "cheat_prompt": cheat_prompt,
            "llm_configured": llm_configured,
            "turns": turns,
        },
    )


@router.post("/game/world-setup/skip")
def game_world_setup_skip(
    campaign_id: int = Form(...),
    session_id: int = Form(...),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))

    conn = get_connection(paths.db_path)
    try:
        app_settings.set(conn, _world_setup_skip_key(session_id), "1")
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(url="/game", status_code=303)


@router.post("/game/turn", response_class=HTMLResponse)
def game_turn(
    request: Request,
    campaign_id: int = Form(...),
    session_id: int = Form(...),
    player_text: str = Form(...),
    attempt_id: str = Form(""),
    tags: str = Form(""),
    state_block: str = Form(""),
) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_active_llm_config()
    if llm_cfg is None:
        return templates.TemplateResponse(
            request=request,
            name="partials/test_result.html",
            context={"ok": False, "message": "LLM 未配置，请先在 /models 配置。"},
            headers={"X-Turn-Accepted": "0"},
        )

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))

    conn = get_connection(paths.db_path)
    try:
        cheat_cfg = session_cheats.get_cheat(conn, session_id=session_id) or {}
        cheat_enabled = bool(int(cheat_cfg.get("enabled") or 0))
        cheat_prompt = (cheat_cfg.get("cheat_prompt") or "").strip()
    finally:
        conn.close()

    turn_context, effective_cheat_prompt = _build_turn_prompt_overrides(
        cheat_enabled=cheat_enabled,
        cheat_prompt=cheat_prompt,
        state_block=state_block,
    )

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    try:
        memory_cfg = load_memory_config(paths.config_path)
        client = create_llm_client(llm_cfg)
        action = PlayerAction(
            campaign_id=campaign_id,
            session_id=session_id,
            text=player_text,
            manual_tags=tag_list,
            extra_context=(state_block or "").strip(),
            attempt_id=_turn_attempt_id(attempt_id),
        )
        conn = get_connection(paths.db_path)
        try:
            result = TurnPipeline(dm_client=client).run_non_streaming(
                conn,
                action=action,
                memory_cfg=memory_cfg,
                state_block=turn_context,
                cheat_prompt=effective_cheat_prompt,
            )
            logger.info("turn_done web_non_stream session=%s turn=%s", session_id, result.turn_index)
        finally:
            conn.close()

        turn = turn_presenter.present_result(result, player_text=player_text)
        return templates.TemplateResponse(
            request=request,
            name="partials/chat_turn_append.html",
            context={
                "turn": turn,
                "recalled_world": result.recalled_world,
                "recalled_context": list(result.recalled_context or []),
            },
        )
    except LLMClientError as e:
        return templates.TemplateResponse(
            request=request,
            name="partials/chat_turn_error_append.html",
            context={"player_text": player_text, "message": str(e)},
            headers={"X-Turn-Accepted": "0"},
        )
    except TURN_DOMAIN_ERRORS as exc:
        logger.warning("turn_rejected web_non_stream error=%s", type(exc).__name__, exc_info=True)
        public = public_turn_error(exc)
        headers = {"X-Turn-Accepted": "0"}
        if public.retry_after is not None:
            headers["Retry-After"] = public.retry_after
        return templates.TemplateResponse(
            request=request,
            name="partials/chat_turn_error_append.html",
            context={"player_text": player_text, "message": public.message},
            status_code=public.status_code,
            headers=headers,
        )


@router.post("/game/turn/stream")
def game_turn_stream(
    request: Request,
    campaign_id: int = Form(...),
    session_id: int = Form(...),
    player_text: str = Form(...),
    attempt_id: str = Form(""),
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
    llm_cfg = load_active_llm_config()
    if llm_cfg is None:
        return StreamingResponse(
            iter([('event: error\ndata: {"message":"LLM 未配置，请先在 /models 配置。"}\n\n').encode("utf-8")]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))

    # Load only route-scoped prompt overrides. Session sidebar state is read by ContextPack.
    conn0 = get_connection(paths.db_path)
    try:
        cheat_cfg = session_cheats.get_cheat(conn0, session_id=session_id) or {}
        cheat_enabled = bool(int(cheat_cfg.get("enabled") or 0))
        cheat_prompt = (cheat_cfg.get("cheat_prompt") or "").strip()
    finally:
        conn0.close()

    turn_context, effective_cheat_prompt = _build_turn_prompt_overrides(
        cheat_enabled=cheat_enabled,
        cheat_prompt=cheat_prompt,
        state_block=state_block,
    )

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
            pipeline = None
            prepared = None
            try:
                client = create_llm_client(llm_cfg)
                action = PlayerAction(
                    campaign_id=campaign_id,
                    session_id=session_id,
                    text=player_text,
                    manual_tags=tag_list,
                    extra_context=(state_block or "").strip(),
                    attempt_id=_turn_attempt_id(attempt_id),
                )
                pipeline = TurnPipeline(dm_client=client)
                claim_renewed_at = None
                if hasattr(pipeline, "prepare_turn"):
                    prepared = pipeline.prepare_turn(
                        conn,
                        action=action,
                        memory_cfg=memory_cfg,
                        state_block=turn_context,
                        cheat_prompt=effective_cheat_prompt,
                    )
                    if prepared.completed_result is not None:
                        result = prepared.completed_result
                        turn = turn_presenter.present_result(result, player_text=player_text)
                        yield _sse(
                            "final",
                            {
                                "turn": turn,
                                "recalled_world": [],
                                "recalled_context": [],
                                "replayed": True,
                            },
                        )
                        return
                    messages = prepared.messages
                    recalled_world = prepared.recalled_world
                    recalled_context = prepared.recalled_context
                    dice_events = prepared.dice_events
                    action_assessment = prepared.action_assessment
                    action = prepared.action
                    claim_renewed_at = (
                        _claim_clock() if getattr(prepared, "claim_token", None) else None
                    )
                else:
                    # Compatibility for narrow test doubles and older adapters.
                    messages, recalled_world, recalled_context, dice_events, action_assessment = pipeline.prepare_messages(
                        conn,
                        action=action,
                        memory_cfg=memory_cfg,
                        state_block=turn_context,
                        cheat_prompt=effective_cheat_prompt,
                    )
                t_prompt = time.perf_counter()
                msg_count = len(messages)
                prompt_chars = sum(len(m.content or "") for m in messages)

                for delta in client.chat_stream_sse(messages):
                    if claim_renewed_at is not None:
                        now = _claim_clock()
                        if now - claim_renewed_at >= _STREAM_CLAIM_RENEW_SECONDS:
                            if not pipeline.renew_generation_claim(conn, prepared=prepared):
                                raise AdjudicationStoreCorrupt("生成租约已失效")
                            claim_renewed_at = now
                    if first_token_ms is None:
                        first_token_ms = int((time.perf_counter() - t0) * 1000)
                    dm_parts.append(delta)
                    yield _sse("delta", {"text": delta})

                dm_raw = "".join(dm_parts)
                # IMPORTANT(stream): Do NOT trigger a second non-streaming LLM call to "repair protocol".
                # Many providers never close the stream; adding another blocking call here makes the client
                # perceive the SSE as "stuck" (no final event). We keep best-effort parsing downstream.
                dm_raw, repaired = ensure_dm_protocol_output(client, messages, dm_raw, max_retries=0)
                t_llm = time.perf_counter()
                t_parse = time.perf_counter()

                result = pipeline.persist_dm_output(
                    conn,
                    action=action,
                    dm_raw=dm_raw,
                    recalled_world=recalled_world,
                    dice_events=dice_events,
                    recalled_context=recalled_context,
                    action_assessment=action_assessment,
                )
                t_persist = time.perf_counter()

                logger.info(
                    "turn_done web_stream session=%s turn=%s prompt_chars=%s msg_count=%s repaired=%s first_token_ms=%s prompt_ms=%s llm_ms=%s parse_ms=%s persist_ms=%s total_ms=%s",
                    session_id,
                    result.turn_index,
                    prompt_chars,
                    msg_count,
                    1 if repaired else 0,
                    first_token_ms if first_token_ms is not None else -1,
                    int((t_prompt - t0) * 1000),
                    int((t_llm - t_prompt) * 1000),
                    int((t_parse - t_llm) * 1000),
                    int((t_persist - t_parse) * 1000),
                    int((t_persist - t0) * 1000),
                )

                turn = turn_presenter.present_result(result, player_text=player_text)
                yield _sse(
                    "final",
                    {
                        "turn": turn,
                        "recalled_world": result.recalled_world,
                        "recalled_context": list(result.recalled_context or []),
                    },
                )
            finally:
                if (
                    pipeline is not None
                    and prepared is not None
                    and getattr(prepared, "claim_token", None)
                    and hasattr(pipeline, "release_generation_claim")
                ):
                    try:
                        pipeline.release_generation_claim(conn, prepared=prepared)
                    except Exception:
                        logger.exception(
                            "turn_generation_claim_release_failed web_stream session=%s attempt=%s",
                            session_id,
                            getattr(getattr(prepared, "action", None), "attempt_id", ""),
                        )
                conn.close()
        except GeneratorExit:
            # client disconnected / cancelled; do not persist partial results
            return
        except LLMClientError as e:
            yield _sse("error", {"message": str(e)})
        except TURN_DOMAIN_ERRORS as exc:
            logger.warning("turn_rejected web_stream error=%s", type(exc).__name__, exc_info=True)
            yield _sse("error", {"message": public_turn_error(exc).message})
        except Exception as exc:
            logger.exception("turn_failed web_stream")
            yield _sse("error", {"message": public_turn_error(exc).message})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Avoid buffering by reverse proxies / servers (best-effort; harmless locally).
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/game/roll", response_class=HTMLResponse)
def game_roll(
    request: Request,
    roll_expr_text: str = Form(""),
) -> HTMLResponse:
    expr = (roll_expr_text or "").strip()
    if not expr:
        return templates.TemplateResponse(
            request=request,
            name="partials/test_result.html",
            context={"ok": False, "message": "请输入掷骰表达式（例如 d20 / 1d20+5 / 2d6-1）"},
        )
    try:
        event = roll_expr(expr)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="partials/test_result.html",
            context={"ok": False, "message": str(e)},
        )
    return templates.TemplateResponse(
        request=request,
        name="partials/roll_result.html",
        context={"event": event},
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

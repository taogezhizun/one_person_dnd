from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from one_person_dnd.config import (
    AppState,
    LLMConfig,
    load_app_state,
    load_llm_config,
    save_app_state,
    save_llm_config,
)
from one_person_dnd.engine import run_turn
from one_person_dnd.llm import ChatMessage, OpenAICompatClient, LLMClientError
from one_person_dnd.paths import ensure_app_dirs

router = APIRouter()
web_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(web_dir / "templates"))


def _ensure_default_campaign_session() -> tuple[int, int]:
    """
    Ensure at least one campaign + one session exists.
    Return (campaign_id, session_id) of the first ones.
    """
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        row = conn.execute("SELECT id FROM campaigns ORDER BY id LIMIT 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO campaigns(name) VALUES (?)", ("默认战役",))
            campaign_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
                (campaign_id, "默认会话", "起始"),
            )
            session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
            return campaign_id, session_id

        campaign_id = int(row["id"])
        srow = conn.execute(
            "SELECT id FROM sessions WHERE campaign_id = ? ORDER BY id LIMIT 1", (campaign_id,)
        ).fetchone()
        if srow is None:
            conn.execute(
                "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
                (campaign_id, "默认会话", "起始"),
            )
            session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
            return campaign_id, session_id
        return campaign_id, int(srow["id"])
    finally:
        conn.close()


def _get_current_campaign_session() -> tuple[int, int]:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    # Ensure DB has at least one save
    default_campaign_id, default_session_id = _ensure_default_campaign_session()
    state = load_app_state(paths.config_path)

    conn = get_connection(paths.db_path)
    try:
        campaign_id = state.active_campaign_id or default_campaign_id
        crow = conn.execute("SELECT id FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if crow is None:
            campaign_id = default_campaign_id

        session_id = state.active_session_id
        if session_id is not None:
            srow = conn.execute(
                "SELECT id FROM sessions WHERE id = ? AND campaign_id = ?",
                (session_id, campaign_id),
            ).fetchone()
            if srow is not None:
                return campaign_id, int(srow["id"])

        # fallback to first session in that campaign
        srow = conn.execute(
            "SELECT id FROM sessions WHERE campaign_id = ? ORDER BY id LIMIT 1", (campaign_id,)
        ).fetchone()
        if srow is None:
            # create one if needed
            conn.execute(
                "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
                (campaign_id, "默认会话", "起始"),
            )
            session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
        else:
            session_id = int(srow["id"])
    finally:
        conn.close()

    # persist selection
    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return campaign_id, session_id


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_llm_config(paths.config_path)
    campaign_id, session_id = _get_current_campaign_session()

    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        c = conn.execute("SELECT name FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        s = conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)).fetchone()
        campaign_name = c["name"] if c else ""
        session_title = s["title"] if s else ""
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


@router.get("/setup", response_class=HTMLResponse)
def setup_get(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    llm_cfg = load_llm_config(paths.config_path)
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={
            "existing": llm_cfg,
            "config_path": str(paths.config_path),
        },
    )


@router.post("/setup")
def setup_post(
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    timeout_seconds: float = Form(60.0),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    save_llm_config(
        paths.config_path,
        LLMConfig(
            base_url=base_url.strip(),
            api_key=api_key.strip(),
            model=model.strip(),
            timeout_seconds=timeout_seconds,
        ),
    )
    return RedirectResponse(url="/", status_code=303)


@router.post("/setup/test", response_class=HTMLResponse)
def setup_test(
    request: Request,
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    timeout_seconds: float = Form(60.0),
) -> HTMLResponse:
    """
    Best-effort test call. Network may be blocked in some environments; UI should show the error text.
    """
    cfg = LLMConfig(
        base_url=base_url.strip(),
        api_key=api_key.strip(),
        model=model.strip(),
        timeout_seconds=timeout_seconds,
    )
    try:
        client = OpenAICompatClient(cfg)
        resp = client.chat(
            [
                ChatMessage(role="system", content="你是一个连通性测试助手。只回答 OK。"),
                ChatMessage(role="user", content="test"),
            ]
        )
        ok = True
        message = (resp or "").strip() or "OK"
    except LLMClientError as e:
        ok = False
        message = str(e)

    return templates.TemplateResponse(
        request=request,
        name="partials/test_result.html",
        context={"ok": ok, "message": message},
    )


@router.get("/game", response_class=HTMLResponse)
def game(request: Request) -> HTMLResponse:
    campaign_id, session_id = _get_current_campaign_session()
    paths = ensure_app_dirs()

    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        c = conn.execute("SELECT name FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        s = conn.execute(
            "SELECT title, current_scene, session_state, pinned_world_notes FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        campaign_name = c["name"] if c else ""
        session_title = s["title"] if s else ""
        current_scene = s["current_scene"] if s else ""
        session_state = s["session_state"] if s and "session_state" in s.keys() else ""
        pinned_world_notes = s["pinned_world_notes"] if s and "pinned_world_notes" in s.keys() else ""
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

    # Validate and persist current selection
    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))

    # Load session sidebar info and inject into state for DM
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        srow = conn.execute(
            "SELECT title, current_scene, session_state, pinned_world_notes FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
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
        result = run_turn(
            db_path=paths.db_path,
            llm_cfg=llm_cfg,
            campaign_id=campaign_id,
            session_id=session_id,
            player_text=player_text,
            state_block=merged_state_block,
            tags=tag_list or None,
        )

        return templates.TemplateResponse(
            request=request,
            name="partials/turn_result.html",
            context={"dm": result.dm, "recalled_world": result.recalled_world},
        )
    except LLMClientError as e:
        return templates.TemplateResponse(
            request=request,
            name="partials/turn_error.html",
            context={"message": str(e)},
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
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        conn.execute(
            """
            UPDATE sessions
            SET current_scene = ?, session_state = ?, pinned_world_notes = ?
            WHERE id = ? AND campaign_id = ?
            """,
            (
                (current_scene or "").strip(),
                (session_state or "").strip(),
                (pinned_world_notes or "").strip(),
                session_id,
                campaign_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="partials/save_ok.html",
        context={"message": "已保存"},
    )


@router.get("/memory/world", response_class=HTMLResponse)
def world_bible_list(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        campaign_id, _session_id = _get_current_campaign_session()
        rows = conn.execute(
            """
            SELECT id, type, title, tags, updated_at
            FROM world_bible_entries
            WHERE campaign_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 200
            """,
            (campaign_id,),
        ).fetchall()
        entries = [dict(r) for r in rows]
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="world_bible_list.html",
        context={"entries": entries, "campaign_id": campaign_id},
    )


@router.get("/memory/world/new", response_class=HTMLResponse)
def world_bible_new(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="world_bible_new.html", context={})


@router.post("/memory/world/new")
def world_bible_create(
    type: str = Form(...),
    title: str = Form(...),
    tags: str = Form(""),
    # structured template fields (optional)
    location_geo: str = Form(""),
    location_factions: str = Form(""),
    location_resources: str = Form(""),
    location_dangers: str = Form(""),
    location_points: str = Form(""),
    npc_appearance: str = Form(""),
    npc_motivation: str = Form(""),
    npc_secret: str = Form(""),
    npc_relations: str = Form(""),
    npc_combat: str = Form(""),
    org_goal: str = Form(""),
    org_resources: str = Form(""),
    org_enemies: str = Form(""),
    org_influence: str = Form(""),
    rule_hard_constraints: str = Form(""),
    rule_magic: str = Form(""),
    rule_taboos: str = Form(""),
    content_free: str = Form(""),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        campaign_id, _session_id = _get_current_campaign_session()

        t = type.strip()
        lines: list[str] = []
        if content_free.strip():
            lines.append(content_free.strip())

        if t == "Location":
            if location_geo.strip():
                lines.append(f"地理：{location_geo.strip()}")
            if location_factions.strip():
                lines.append(f"势力：{location_factions.strip()}")
            if location_resources.strip():
                lines.append(f"资源：{location_resources.strip()}")
            if location_dangers.strip():
                lines.append(f"危险：{location_dangers.strip()}")
            if location_points.strip():
                lines.append(f"关键地点：{location_points.strip()}")
        elif t == "NPC":
            if npc_appearance.strip():
                lines.append(f"外观：{npc_appearance.strip()}")
            if npc_motivation.strip():
                lines.append(f"动机：{npc_motivation.strip()}")
            if npc_secret.strip():
                lines.append(f"秘密：{npc_secret.strip()}")
            if npc_relations.strip():
                lines.append(f"关系：{npc_relations.strip()}")
            if npc_combat.strip():
                lines.append(f"战斗倾向：{npc_combat.strip()}")
        elif t == "Organization":
            if org_goal.strip():
                lines.append(f"目标：{org_goal.strip()}")
            if org_resources.strip():
                lines.append(f"资源：{org_resources.strip()}")
            if org_enemies.strip():
                lines.append(f"敌对：{org_enemies.strip()}")
            if org_influence.strip():
                lines.append(f"影响范围：{org_influence.strip()}")
        elif t == "Rule":
            if rule_hard_constraints.strip():
                lines.append(f"硬约束：{rule_hard_constraints.strip()}")
            if rule_magic.strip():
                lines.append(f"魔法规则：{rule_magic.strip()}")
            if rule_taboos.strip():
                lines.append(f"禁忌：{rule_taboos.strip()}")

        content = "\n".join(lines).strip() or "（空）"
        conn.execute(
            """
            INSERT INTO world_bible_entries(
              campaign_id, type, title, content, tags, related_locations, related_npcs
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                t,
                title.strip(),
                content,
                tags.strip(),
                "",
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(url="/memory/world", status_code=303)


@router.get("/memory/story", response_class=HTMLResponse)
def story_journal_list(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        _campaign_id, session_id = _get_current_campaign_session()

        rows = conn.execute(
            """
            SELECT id, scene_id, summary, created_at
            FROM story_journal_entries
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 200
            """,
            (session_id,),
        ).fetchall()
        entries = [dict(r) for r in rows]
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="story_list.html",
        context={"entries": entries, "session_id": session_id},
    )


@router.get("/saves", response_class=HTMLResponse)
def saves(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    current_campaign_id, current_session_id = _get_current_campaign_session()

    conn = get_connection(paths.db_path)
    try:
        campaigns = [dict(r) for r in conn.execute("SELECT id, name, created_at FROM campaigns ORDER BY id DESC")]
        sessions = [
            dict(r)
            for r in conn.execute(
                "SELECT id, title, current_scene, created_at FROM sessions WHERE campaign_id = ? ORDER BY id DESC",
                (current_campaign_id,),
            )
        ]
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="saves.html",
        context={
            "campaigns": campaigns,
            "sessions": sessions,
            "current_campaign_id": current_campaign_id,
            "current_session_id": current_session_id,
        },
    )


@router.post("/saves/campaign/new")
def saves_campaign_new(name: str = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        conn.execute("INSERT INTO campaigns(name) VALUES (?)", (name.strip(),))
        campaign_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
            (campaign_id, "默认会话", "起始"),
        )
        session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/campaign/select")
def saves_campaign_select(campaign_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        srow = conn.execute(
            "SELECT id FROM sessions WHERE campaign_id = ? ORDER BY id LIMIT 1", (campaign_id,)
        ).fetchone()
        if srow is None:
            conn.execute(
                "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
                (campaign_id, "默认会话", "起始"),
            )
            session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
        else:
            session_id = int(srow["id"])
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/campaign/enter")
def saves_campaign_enter(campaign_id: int = Form(...)) -> RedirectResponse:
    """
    Select campaign (and a session under it), then jump into /game.
    """
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        srow = conn.execute(
            "SELECT id FROM sessions WHERE campaign_id = ? ORDER BY id LIMIT 1", (campaign_id,)
        ).fetchone()
        if srow is None:
            conn.execute(
                "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
                (campaign_id, "默认会话", "起始"),
            )
            session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
        else:
            session_id = int(srow["id"])
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/game", status_code=303)


@router.post("/saves/session/new")
def saves_session_new(title: str = Form(...), current_scene: str = Form("起始")) -> RedirectResponse:
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    campaign_id, _session_id = _get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        conn.execute(
            "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
            (campaign_id, title.strip(), (current_scene or "").strip()),
        )
        session_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/session/select")
def saves_session_select(session_id: int = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, _old = _get_current_campaign_session()
    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/saves", status_code=303)


@router.post("/saves/session/enter")
def saves_session_enter(session_id: int = Form(...)) -> RedirectResponse:
    """
    Select session (and its campaign), then jump into /game.
    """
    paths = ensure_app_dirs()
    from one_person_dnd.db import get_connection

    conn = get_connection(paths.db_path)
    try:
        row = conn.execute("SELECT campaign_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            # fallback
            campaign_id, session_id2 = _get_current_campaign_session()
            save_app_state(
                paths.config_path,
                AppState(active_campaign_id=campaign_id, active_session_id=session_id2),
            )
            return RedirectResponse(url="/game", status_code=303)
        campaign_id = int(row["campaign_id"])
    finally:
        conn.close()

    save_app_state(paths.config_path, AppState(active_campaign_id=campaign_id, active_session_id=session_id))
    return RedirectResponse(url="/game", status_code=303)


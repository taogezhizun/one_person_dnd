from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import story_journal, world_bible
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, templates

router = APIRouter()


@router.get("/memory/world", response_class=HTMLResponse)
def world_bible_list(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    campaign_id, _session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        entries = world_bible.list_world_bible_entries(conn, campaign_id=campaign_id, limit=200)
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
    campaign_id, _session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
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
        world_bible.insert_world_bible_entry(
            conn,
            campaign_id=campaign_id,
            type=t,
            title=title.strip(),
            content=content,
            tags=tags.strip(),
        )
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(url="/memory/world", status_code=303)


@router.get("/memory/story", response_class=HTMLResponse)
def story_journal_list(request: Request) -> HTMLResponse:
    paths = ensure_app_dirs()
    _campaign_id, session_id = get_current_campaign_session()
    conn = get_connection(paths.db_path)
    try:
        entries = story_journal.list_story_journal_entries(conn, session_id=session_id, limit=200)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="story_list.html",
        context={"entries": entries, "session_id": session_id},
    )


from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import campaigns, story_journal, world_bible
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
        campaign_name = campaigns.get_campaign_name(conn, campaign_id) or ""
    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="world_bible_list.html",
        context={"entries": entries, "campaign_id": campaign_id, "campaign_name": campaign_name},
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

        def append_field(label: str, value: str) -> None:
            cleaned = value.strip()
            if cleaned:
                lines.append(f"{label}：{cleaned}")

        if t == "Location":
            append_field("地理", location_geo)
            append_field("势力", location_factions)
            append_field("资源", location_resources)
            append_field("危险", location_dangers)
            append_field("关键地点", location_points)
        elif t == "NPC":
            append_field("外观", npc_appearance)
            append_field("动机", npc_motivation)
            append_field("秘密", npc_secret)
            append_field("关系", npc_relations)
            append_field("战斗倾向", npc_combat)
        elif t == "Organization":
            append_field("目标", org_goal)
            append_field("资源", org_resources)
            append_field("敌对", org_enemies)
            append_field("影响范围", org_influence)
        elif t == "Rule":
            append_field("硬约束", rule_hard_constraints)
            append_field("魔法规则", rule_magic)
            append_field("禁忌", rule_taboos)

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

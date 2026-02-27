from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import character_sheets, world_bible
from one_person_dnd.llm import ChatMessage, LLMClientError, create_llm_client
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import get_current_campaign_session, load_active_llm_config, templates

router = APIRouter()


@router.get("/new", response_class=HTMLResponse)
def new_get(request: Request) -> HTMLResponse:
    llm_cfg = load_active_llm_config()
    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context={"llm_ready": llm_cfg is not None},
    )


@router.post("/new/generate", response_class=HTMLResponse)
def new_generate(
    request: Request,
    genre: str = Form("奇幻"),
    tone: str = Form("冒险"),
    tech_level: str = Form("中世纪"),
    themes: str = Form("探索,谜团"),
    character_count: int = Form(1),
    extra_constraints: str = Form(""),
) -> HTMLResponse:
    llm_cfg = load_active_llm_config()
    if llm_cfg is None:
        return templates.TemplateResponse(
            request=request,
            name="partials/test_result.html",
            context={"ok": False, "message": "LLM 未配置，请先在 /models 选择或创建一个模型配置。"},
        )

    char_n = max(1, min(4, int(character_count)))
    system = (
        "你是一个 TRPG 向导生成器。请严格输出一个 JSON（不要包含任何解释文本）。\n"
        "JSON 结构：\n"
        "{\n"
        '  \"world_bible_entries\": [\n'
        "    {\"type\":\"Rule|Location|NPC|Organization\",\"title\":\"...\",\"tags\":\"逗号分隔\",\"content\":\"多行文本\"}\n"
        "  ],\n"
        '  \"character_sheet\": {\n'
        "    \"party\": [\n"
        "      {\"name\":\"...\",\"race\":\"...\",\"class\":\"...\",\"background\":\"...\",\"goal\":\"...\",\"hp\":10,\"gold\":5,\"inventory\":[\"...\"]}\n"
        "    ],\n"
        "    \"notes\": \"可选：系统建议/开场钩子\"\n"
        "  }\n"
        "}\n"
        "要求：\n"
        f"- 生成 {char_n} 名角色放在 party 数组。\n"
        "- world_bible_entries 建议 6-10 条，覆盖硬规则、关键地点、关键 NPC、一个组织/势力。\n"
        "- content 使用中文，尽量具体可玩。\n"
    )
    user = (
        f"风格：{genre}\n"
        f"基调：{tone}\n"
        f"科技水平：{tech_level}\n"
        f"主题：{themes}\n"
        f"额外约束：{extra_constraints}\n"
    )

    try:
        client = create_llm_client(llm_cfg)
        raw = client.chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("JSON 根必须是对象")
        entries = obj.get("world_bible_entries") or []
        sheet = obj.get("character_sheet") or {}
        if not isinstance(entries, list) or not isinstance(sheet, dict):
            raise ValueError("JSON 字段类型不正确")
        preview_json = json.dumps(obj, ensure_ascii=False, indent=2)
    except (LLMClientError, ValueError, json.JSONDecodeError) as e:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context={"llm_ready": True, "error": str(e)},
        )

    return templates.TemplateResponse(
        request=request,
        name="new_preview.html",
        context={
            "genre": genre,
            "tone": tone,
            "tech_level": tech_level,
            "themes": themes,
            "character_count": char_n,
            "extra_constraints": extra_constraints,
            "preview_obj": obj,
            "preview_json": preview_json,
        },
    )


@router.post("/new/apply")
def new_apply(preview_json: str = Form(...)) -> RedirectResponse:
    paths = ensure_app_dirs()
    campaign_id, session_id = get_current_campaign_session()

    obj = json.loads(preview_json)
    entries = obj.get("world_bible_entries") or []
    sheet = obj.get("character_sheet") or {}

    conn = get_connection(paths.db_path)
    try:
        for e in entries:
            if not isinstance(e, dict):
                continue
            t = (e.get("type") or "Rule").strip()
            title = (e.get("title") or "").strip()
            content = (e.get("content") or "").strip()
            tags = (e.get("tags") or "").strip()
            if not title or not content:
                continue
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=campaign_id,
                type=t,
                title=title,
                content=content,
                tags=tags,
            )

        # Save character sheet as authoritative JSON
        character_sheets.upsert_character_sheet(conn, session_id=session_id, json_text=json.dumps(sheet, ensure_ascii=False, indent=2))
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(url="/game", status_code=303)


from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from one_person_dnd.config import AppState, save_app_state
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, sessions, world_bible
from one_person_dnd.llm import ChatMessage, LLMClientError, create_llm_client
from one_person_dnd.paths import ensure_app_dirs
from one_person_dnd.web.routes.common import load_active_llm_config, templates

router = APIRouter()


DEFAULT_FORM_VALUES = {
    "adventure_brief": "",
    "genre": "奇幻",
    "tone": "冒险",
    "tech_level": "中世纪",
    "themes": "探索,谜团",
    "character_count": 1,
    "extra_constraints": "",
}

CANONICAL_ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


def _new_context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "llm_ready": load_active_llm_config() is not None,
        "form_values": dict(DEFAULT_FORM_VALUES),
    }
    context.update(overrides)
    return context


def _decode_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("JSON 根必须是对象")
    return obj


def _bounded_text(value: object, fallback: str, *, max_length: int = 120) -> str:
    text = str(value or "").strip()
    return (text or fallback)[:max_length]


def _bounded_int(value: object, fallback: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _normalize_generated_character_sheet(sheet: dict) -> dict:
    party = sheet.get("party")
    if not isinstance(party, list) or not party:
        raise ValueError("生成结果中的角色卡必须包含至少一名 party 角色")

    normalized_party: list[dict] = []
    for member in party:
        if not isinstance(member, dict):
            raise ValueError("生成结果中的 party 角色格式不正确")

        normalized = dict(member)
        raw_abilities = member.get("abilities")
        if not isinstance(raw_abilities, dict):
            raw_abilities = {}
        normalized["level"] = _bounded_int(member.get("level"), 1, minimum=1, maximum=20)
        normalized["abilities"] = {
            ability: _bounded_int(raw_abilities.get(ability), 10, minimum=1, maximum=30)
            for ability in CANONICAL_ABILITIES
        }

        raw_skills = member.get("skill_proficiencies")
        if isinstance(raw_skills, str):
            skill_items = raw_skills.replace("，", ",").split(",")
        elif isinstance(raw_skills, list):
            skill_items = raw_skills
        else:
            skill_items = []
        normalized["skill_proficiencies"] = list(
            dict.fromkeys(str(item).strip() for item in skill_items if str(item).strip())
        )
        normalized_party.append(normalized)

    normalized_sheet = dict(sheet)
    normalized_sheet["party"] = normalized_party
    return normalized_sheet


def _encode_source_form(form_values: dict[str, object], proposal: dict[str, str]) -> str:
    return json.dumps(
        {"form_values": form_values, "proposal": proposal},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode_source_form(raw: str) -> tuple[dict[str, object], dict[str, str]]:
    source = _decode_json_object(raw)
    raw_values = source.get("form_values")
    raw_proposal = source.get("proposal")
    if not isinstance(raw_values, dict) or not isinstance(raw_proposal, dict):
        raise ValueError("返回修改所需的原始表单格式不正确")

    form_values: dict[str, object] = dict(DEFAULT_FORM_VALUES)
    for key in ("adventure_brief", "genre", "tone", "tech_level", "themes", "extra_constraints"):
        if key in raw_values:
            form_values[key] = str(raw_values.get(key) or "").strip()
    form_values["character_count"] = _bounded_int(
        raw_values.get("character_count"),
        int(DEFAULT_FORM_VALUES["character_count"]),
        minimum=1,
        maximum=4,
    )
    proposal = {
        "adventure_name": str(raw_proposal.get("adventure_name") or "").strip()[:120],
        "chapter_title": str(raw_proposal.get("chapter_title") or "").strip()[:120],
    }
    return form_values, proposal


@router.get("/new", response_class=HTMLResponse)
def new_get(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context=_new_context(),
    )


@router.post("/new/propose", response_class=HTMLResponse)
def new_propose(
    request: Request,
    adventure_brief: str = Form(""),
    genre: str = Form("奇幻"),
    tone: str = Form("冒险"),
    tech_level: str = Form("中世纪"),
    themes: str = Form("探索,谜团"),
    character_count: int = Form(1),
    extra_constraints: str = Form(""),
) -> HTMLResponse:
    llm_cfg = load_active_llm_config()
    form_values = {
        "adventure_brief": adventure_brief.strip(),
        "genre": genre.strip() or "奇幻",
        "tone": tone.strip() or "冒险",
        "tech_level": tech_level.strip() or "中世纪",
        "themes": themes.strip() or "探索,谜团",
        "character_count": max(1, min(4, int(character_count))),
        "extra_constraints": extra_constraints.strip(),
    }
    if llm_cfg is None:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context=_new_context(
                llm_ready=False,
                form_values=form_values,
                error="模型尚未配置，请先在“模型”页面选择或创建可用配置。",
            ),
        )

    system = (
        "你是单人 TRPG 的冒险构思搭档。请严格输出一个 JSON 对象，不要解释，不要使用 Markdown。\n"
        "结构：{\"adventure_name\":\"冒险名\",\"chapter_title\":\"第一章标题\","
        "\"adventure_brief\":\"三到五句可编辑的冒险提案\",\"genre\":\"风格\","
        "\"tone\":\"基调\",\"tech_level\":\"时代或科技水平\",\"themes\":\"逗号分隔主题\","
        "\"character_count\":1,\"extra_constraints\":\"值得保留的限制或开场钩子\"}。\n"
        "提案要具体、可玩、有清晰冲突，但不要替玩家决定角色行动。"
    )
    user = (
        "请根据现有偏好补全并优化一套提案；若描述为空，就独立构思一套完整而有辨识度的提案。\n"
        f"我的想法：{form_values['adventure_brief'] or '（请你自由构思）'}\n"
        f"风格：{form_values['genre']}\n基调：{form_values['tone']}\n"
        f"时代或科技：{form_values['tech_level']}\n主题：{form_values['themes']}\n"
        f"角色数量：{form_values['character_count']}\n额外约束：{form_values['extra_constraints'] or '无'}"
    )
    try:
        client = create_llm_client(llm_cfg)
        obj = _decode_json_object(
            client.chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
        )
        form_values.update(
            {
                "adventure_brief": _bounded_text(obj.get("adventure_brief"), form_values["adventure_brief"], max_length=1200),
                "genre": _bounded_text(obj.get("genre"), form_values["genre"]),
                "tone": _bounded_text(obj.get("tone"), form_values["tone"]),
                "tech_level": _bounded_text(obj.get("tech_level"), form_values["tech_level"]),
                "themes": _bounded_text(obj.get("themes"), form_values["themes"], max_length=240),
                "character_count": max(1, min(4, int(obj.get("character_count") or form_values["character_count"]))),
                "extra_constraints": _bounded_text(
                    obj.get("extra_constraints"), form_values["extra_constraints"], max_length=800
                ),
            }
        )
        proposal = {
            "adventure_name": _bounded_text(obj.get("adventure_name"), "未命名冒险"),
            "chapter_title": _bounded_text(obj.get("chapter_title"), "第一章·故事开场"),
        }
    except (LLMClientError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context=_new_context(form_values=form_values, error=str(exc)),
        )

    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context=_new_context(form_values=form_values, proposal=proposal),
    )


@router.post("/new/generate", response_class=HTMLResponse)
def new_generate(
    request: Request,
    adventure_brief: str = Form(""),
    genre: str = Form("奇幻"),
    tone: str = Form("冒险"),
    tech_level: str = Form("中世纪"),
    themes: str = Form("探索,谜团"),
    character_count: int = Form(1),
    extra_constraints: str = Form(""),
    proposed_adventure_name: str = Form(""),
    proposed_chapter_title: str = Form(""),
) -> HTMLResponse:
    llm_cfg = load_active_llm_config()
    char_n = max(1, min(4, int(character_count)))
    form_values = {
        "adventure_brief": adventure_brief.strip(),
        "genre": genre.strip() or "奇幻",
        "tone": tone.strip() or "冒险",
        "tech_level": tech_level.strip() or "中世纪",
        "themes": themes.strip() or "探索,谜团",
        "character_count": char_n,
        "extra_constraints": extra_constraints.strip(),
    }
    proposal = {
        "adventure_name": proposed_adventure_name.strip(),
        "chapter_title": proposed_chapter_title.strip(),
    }
    if llm_cfg is None:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context=_new_context(
                llm_ready=False,
                form_values=form_values,
                proposal=proposal if any(proposal.values()) else None,
                error="模型尚未配置，请先在“模型”页面选择或创建可用配置。",
            ),
        )

    system = (
        "你是一个单人 TRPG 冒险设计师。请严格输出一个 JSON 对象，不要解释，不要使用 Markdown。\n"
        "JSON 结构：\n"
        "{\n"
        '  "adventure_name":"简洁、有辨识度的冒险名",\n'
        '  "chapter_title":"第一章标题",\n'
        '  "opening_scene":"一句话开场地点或局面",\n'
        '  "world_bible_entries":[\n'
        '    {"type":"Rule|Location|NPC|Organization","title":"...","tags":"逗号分隔","content":"多行文本"}\n'
        "  ],\n"
        '  "character_sheet":{"party":[\n'
        '    {"name":"...","race":"...","class":"...","level":1,"background":"...","goal":"...",'
        '"hp":10,"gold":5,"inventory":["..."],'
        '"abilities":{"STR":10,"DEX":10,"CON":10,"INT":10,"WIS":10,"CHA":10},'
        '"skill_proficiencies":["Perception","Stealth"]}\n'
        '  ],"notes":"系统建议或开场钩子"}\n'
        "}\n"
        f"生成 {char_n} 名角色。世界设定建议 6-10 条，覆盖硬规则、关键地点、关键人物与至少一个势力。"
        "level 必须是 1-20 的整数；abilities 必须使用 STR、DEX、CON、INT、WIS、CHA 六个 canonical key；"
        "skill_proficiencies 使用英文技能名数组。内容使用中文，具体可玩，不替玩家决定行动。"
    )
    user = (
        f"冒险构想：{form_values['adventure_brief'] or '请根据以下偏好补全'}\n"
        f"建议冒险名：{proposal['adventure_name'] or '请生成'}\n"
        f"建议第一章：{proposal['chapter_title'] or '请生成'}\n"
        f"风格：{form_values['genre']}\n基调：{form_values['tone']}\n"
        f"时代或科技：{form_values['tech_level']}\n主题：{form_values['themes']}\n"
        f"额外约束：{form_values['extra_constraints'] or '无'}"
    )

    try:
        client = create_llm_client(llm_cfg)
        obj = _decode_json_object(
            client.chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
        )
        entries = obj.get("world_bible_entries") or []
        sheet = obj.get("character_sheet") or {}
        if not isinstance(entries, list) or not isinstance(sheet, dict):
            raise ValueError("生成结果中的世界设定或角色卡格式不正确")
        sheet = _normalize_generated_character_sheet(sheet)
        obj["character_sheet"] = sheet
        obj["adventure_name"] = _bounded_text(
            obj.get("adventure_name"), proposal["adventure_name"] or "未命名冒险"
        )
        obj["chapter_title"] = _bounded_text(
            obj.get("chapter_title"), proposal["chapter_title"] or "第一章·故事开场"
        )
        obj["opening_scene"] = _bounded_text(obj.get("opening_scene"), "故事开场", max_length=240)
        preview_json = json.dumps(obj, ensure_ascii=False, indent=2)
    except (LLMClientError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context=_new_context(
                form_values=form_values,
                proposal=proposal if any(proposal.values()) else None,
                error=str(exc),
            ),
        )

    return templates.TemplateResponse(
        request=request,
        name="new_preview.html",
        context={
            "preview_obj": obj,
            "preview_json": preview_json,
            "source_form_json": _encode_source_form(form_values, proposal),
        },
    )


@router.post("/new/return", response_class=HTMLResponse)
def new_return(
    request: Request,
    source_form_json: str = Form(...),
    adventure_name: str = Form(""),
    chapter_title: str = Form(""),
) -> HTMLResponse:
    try:
        form_values, proposal = _decode_source_form(source_form_json)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context=_new_context(error=f"无法恢复刚才的创建草稿：{exc}"),
        )

    # Names are editable on the preview page; returning should preserve those
    # latest edits along with every field captured before generation.
    proposal["adventure_name"] = str(adventure_name or "").strip()[:120]
    proposal["chapter_title"] = str(chapter_title or "").strip()[:120]
    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context=_new_context(
            form_values=form_values,
            proposal=proposal if any(proposal.values()) else None,
        ),
    )


@router.post("/new/apply")
def new_apply(
    preview_json: str = Form(...),
    adventure_name: str = Form(""),
    chapter_title: str = Form(""),
) -> RedirectResponse:
    paths = ensure_app_dirs()
    try:
        obj = _decode_json_object(preview_json)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"无法采用这份冒险预览：{exc}") from exc

    entries = obj.get("world_bible_entries") or []
    sheet = obj.get("character_sheet") or {}
    if not isinstance(entries, list) or not isinstance(sheet, dict):
        raise HTTPException(status_code=400, detail="冒险预览缺少有效的世界设定或角色卡")
    try:
        # The preview is editable client input. Re-establish the canonical
        # character contract at the final persistence boundary instead of
        # trusting that it still matches the earlier generated preview.
        sheet = _normalize_generated_character_sheet(sheet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"无法采用这份角色卡：{exc}") from exc

    final_adventure_name = _bounded_text(adventure_name, _bounded_text(obj.get("adventure_name"), "未命名冒险"))
    final_chapter_title = _bounded_text(chapter_title, _bounded_text(obj.get("chapter_title"), "第一章·故事开场"))
    opening_scene = _bounded_text(obj.get("opening_scene"), "故事开场", max_length=240)

    conn = get_connection(paths.db_path)
    try:
        campaign_id = campaigns.create_campaign(conn, final_adventure_name)
        session_id = sessions.create_session(
            conn,
            campaign_id=campaign_id,
            title=final_chapter_title,
            current_scene=opening_scene,
        )
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = _bounded_text(entry.get("title"), "", max_length=180)
            content = str(entry.get("content") or "").strip()
            if not title or not content:
                continue
            world_bible.insert_world_bible_entry(
                conn,
                campaign_id=campaign_id,
                type=_bounded_text(entry.get("type"), "Rule", max_length=40),
                title=title,
                content=content,
                tags=_bounded_text(entry.get("tags"), "", max_length=300),
            )
        character_sheets.upsert_character_sheet(
            conn,
            session_id=session_id,
            json_text=json.dumps(sheet, ensure_ascii=False, indent=2),
        )
        conn.commit()
    finally:
        conn.close()

    save_app_state(
        paths.config_path,
        AppState(active_campaign_id=campaign_id, active_session_id=session_id),
    )
    return RedirectResponse(url="/game", status_code=303)

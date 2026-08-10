from __future__ import annotations

import sqlite3

from one_person_dnd.config import MemoryConfig
from one_person_dnd.context.pack import ContextBlock, ContextPack
from one_person_dnd.context.selection import select_story_blocks, select_thread_blocks, select_world_blocks
from one_person_dnd.db.repos import character_sheets, sessions
from one_person_dnd.domain.actions import ActionAssessment, PlayerAction
from one_person_dnd.domain.characters import summarize_character_sheet
from one_person_dnd.engine.dice import format_events_for_prompt


_RECALL_REASONS = {
    "world_bible": "匹配玩家填写的标签或置顶世界设定。",
    "scene_state": "注入当前场景和本回合额外上下文。",
    "character_state": "注入当前角色状态和角色卡摘要。",
    "dice": "玩家行动包含掷骰表达式。",
    "cheat_directive": "当前会话启用了金手指指令。",
    "plot_threads": "注入仍开放的剧情线和下一步。",
    "story_memory": "召回最近剧情记忆和摘要。",
    "action_assessment": "评估玩家行动类型、风险和掷骰需求。",
}

_CORE_CONTEXT_KINDS = {
    "action_assessment",
    "character_state",
    "cheat_directive",
    "dice",
    "scene_state",
}
_CORE_CONTEXT_SOURCES = {"sessions.pinned_world_notes"}
_MANDATORY_PROMPT_KINDS = {"action_assessment"}
_CONTEXT_BUDGET_SKIP_REASON = "因上下文预算裁剪，未注入本回合 prompt。"


def build_context_pack(
    conn: sqlite3.Connection,
    *,
    action: PlayerAction,
    assessment: ActionAssessment,
    memory_cfg: MemoryConfig,
    state_block: str = "",
    cheat_prompt: str = "",
) -> ContextPack:
    blocks: list[ContextBlock] = []
    world_blocks, recalled_world = select_world_blocks(
        conn,
        campaign_id=action.campaign_id,
        tags=action.manual_tags or None,
    )
    for idx, selected in enumerate(world_blocks):
        blocks.append(
            ContextBlock(
                kind="world_bible",
                title=f"WorldBible {idx + 1}",
                content=selected.content,
                source="world_bible",
                priority=80,
                preview_data=selected.preview_data,
            )
        )

    srow = sessions.get_session_sidebar(conn, action.session_id)
    if srow:
        scene_parts = []
        scene_preview: dict[str, object] = {"type": "scene"}
        if (srow["title"] or "").strip():
            session_title = (srow["title"] or "").strip()
            scene_parts.append(f"会话：{session_title}")
            scene_preview["session_title"] = session_title
        if (srow["current_scene"] or "").strip():
            current_scene = (srow["current_scene"] or "").strip()
            scene_parts.append(f"当前场景：{current_scene}")
            scene_preview["current_scene"] = current_scene
        if scene_parts:
            blocks.append(
                ContextBlock(
                    kind="scene_state",
                    title="Scene",
                    content="\n".join(scene_parts),
                    source="sessions",
                    priority=90,
                    preview_data=scene_preview,
                )
            )
        if (srow["session_state"] or "").strip():
            blocks.append(
                ContextBlock(
                    kind="character_state",
                    title="Character State",
                    content=(srow["session_state"] or "").strip(),
                    source="sessions",
                    priority=90,
                )
            )

    character_summary = summarize_character_sheet(character_sheets.get_character_sheet(conn, session_id=action.session_id))
    character_prompt = character_summary.to_prompt_text()
    if character_prompt:
        blocks.append(
            ContextBlock(
                kind="character_state",
                title="Character Sheet",
                content=character_prompt,
                source="character_sheets",
                priority=95,
                preview_data={
                    "type": "character_summary",
                    "name": character_summary.name,
                    "race": character_summary.race,
                    "role": character_summary.role,
                    "background": character_summary.background,
                    "goal": character_summary.goal,
                    "hp": character_summary.hp,
                    "max_hp": character_summary.max_hp,
                    "gold": character_summary.gold,
                    "level": character_summary.level,
                    "inventory": list(character_summary.inventory),
                    "conditions": list(character_summary.conditions),
                    "abilities": dict(character_summary.abilities),
                    "skill_proficiencies": list(character_summary.skill_proficiencies),
                    "notes": character_summary.notes,
                },
            )
        )

    if srow:
        if (srow["pinned_world_notes"] or "").strip():
            blocks.append(
                ContextBlock(
                    kind="world_bible",
                    title="Pinned World Notes",
                    content=(srow["pinned_world_notes"] or "").strip(),
                    source="sessions.pinned_world_notes",
                    priority=100,
                )
            )

    if assessment.dice_events:
        blocks.append(
            ContextBlock(
                kind="dice",
                title="Dice",
                content=format_events_for_prompt(assessment.dice_events),
                source="action_judge",
                priority=95,
            )
        )
    if state_block.strip():
        blocks.append(
            ContextBlock(
                kind="scene_state",
                title="Turn Extra Context",
                content=state_block.strip(),
                source="player.extra_context",
                priority=70,
            )
        )
    if cheat_prompt.strip():
        blocks.append(
            ContextBlock(
                kind="cheat_directive",
                title="Cheat Directive",
                content=cheat_prompt.strip(),
                source="session_cheats",
                priority=60,
            )
        )

    thread_blocks = select_thread_blocks(conn, session_id=action.session_id)
    for idx, selected in enumerate(thread_blocks):
        blocks.append(
            ContextBlock(
                kind="plot_threads",
                title=f"Open Thread {idx + 1}",
                content=selected.content,
                source="plot_threads",
                priority=70,
                preview_data=selected.preview_data,
            )
        )

    story_blocks = select_story_blocks(conn, session_id=action.session_id, limit=memory_cfg.story_journal_for_prompt)
    for idx, selected in enumerate(story_blocks):
        blocks.append(
            ContextBlock(
                kind="story_memory",
                title=f"Story Memory {idx + 1}",
                content=selected.content,
                source="story_journal",
                priority=50,
                preview_data=selected.preview_data,
            )
        )

    assessment_lines = [
        f"action_type: {assessment.action_type}",
        "signals: " + ", ".join(assessment.signals),
        "warnings: " + ", ".join(assessment.warnings),
    ]
    adjudication = assessment.adjudication
    if adjudication is not None:
        assessment_lines.extend(
            [
                f"adjudication_status: {adjudication.status}",
                f"adjudication_policy: {adjudication.policy_version}",
            ]
        )
        if adjudication.manual_rolls:
            assessment_lines.append("manual_rolls: raw_only; not a canonical ability check")
        if adjudication.check is not None:
            check = adjudication.check
            assessment_lines.extend(
                [
                    f"test_kind: {check.test_kind}",
                    f"intent: {check.intent}",
                    f"ability_skill: {check.ability}" + (f" / {check.skill}" if check.skill else ""),
                    f"dc: {check.dc} ({check.dc_reason})",
                    f"roll_mode: {check.roll_mode}; d20s: {list(check.d20s)}; selected: {check.selected_d20}",
                    "modifiers: "
                    f"ability {check.ability_modifier:+d}, proficiency {check.proficiency_modifier:+d}, "
                    f"circumstance {check.circumstance_modifier:+d}",
                    f"authoritative_total: {check.total}; outcome: {check.outcome}",
                    "dm_instruction: narrate the authoritative outcome; do not reroll or alter DC/modifiers",
                ]
            )
    assessment_text = "\n".join(assessment_lines).strip()
    assessment_preview: dict[str, object] = {
        "type": "action_assessment",
        "action_type": assessment.action_type,
        "signals": list(assessment.signals),
        "warnings": list(assessment.warnings),
    }
    if adjudication is not None:
        assessment_preview["status"] = adjudication.status
        if adjudication.check is not None:
            assessment_preview["check"] = adjudication.check.to_dict()
    blocks.append(
        ContextBlock(
            kind="action_assessment",
            title="Action Assessment",
            content=assessment_text,
            source="action_judge",
            priority=85,
            preview_data=assessment_preview,
        )
    )

    retained_blocks, skipped_blocks = _apply_context_budget(blocks, memory_cfg.context_chars_for_prompt)

    return ContextPack(
        campaign_id=action.campaign_id,
        session_id=action.session_id,
        action_text=action.text,
        blocks=retained_blocks,
        recalled_world=recalled_world,
        recalled_context=_build_recalled_context(retained_blocks, skipped_blocks),
        dice_events=assessment.dice_events,
        assessment=assessment,
    )


def _apply_context_budget(blocks: list[ContextBlock], max_chars: int) -> tuple[list[ContextBlock], list[ContextBlock]]:
    if max_chars <= 0:
        return blocks, []

    candidates = [(idx, block) for idx, block in enumerate(blocks) if (block.content or "").strip()]
    ranked = sorted(
        candidates,
        key=lambda item: (_is_core_context_block(item[1]), item[1].priority, -item[0]),
        reverse=True,
    )

    # The frozen action assessment is the mechanical fact the DM must narrate.
    # Treat it as budget-exempt: even an unusually small user-configured budget
    # must not make the model lose the already-committed DC, roll, or outcome.
    retained_indices = {
        idx for idx, block in candidates if block.kind in _MANDATORY_PROMPT_KINDS
    }
    used_chars = sum(
        len((block.content or "").strip())
        for idx, block in candidates
        if idx in retained_indices
    )
    retained_core_count = sum(
        1
        for idx, block in candidates
        if idx in retained_indices and _is_core_context_block(block)
    )
    for idx, block in ranked:
        if idx in retained_indices:
            continue
        block_chars = len((block.content or "").strip())
        is_core = _is_core_context_block(block)
        if used_chars + block_chars <= max_chars:
            retained_indices.add(idx)
            used_chars += block_chars
            if is_core:
                retained_core_count += 1
            continue
        if is_core and retained_core_count == 0:
            retained_indices.add(idx)
            used_chars += block_chars
            retained_core_count += 1

    retained = [block for idx, block in enumerate(blocks) if idx in retained_indices]
    skipped = [block for idx, block in enumerate(blocks) if idx not in retained_indices and (block.content or "").strip()]
    return retained, skipped


def _is_core_context_block(block: ContextBlock) -> bool:
    return block.kind in _CORE_CONTEXT_KINDS or block.source in _CORE_CONTEXT_SOURCES


def _build_recalled_context(included_blocks: list[ContextBlock], skipped_blocks: list[ContextBlock] | None = None) -> list[dict]:
    recalled: list[dict] = []
    for block in sorted(included_blocks, key=lambda b: b.priority, reverse=True):
        entry = _build_recalled_context_entry(block, status="included")
        if entry:
            recalled.append(entry)
    for block in sorted(skipped_blocks or [], key=lambda b: b.priority, reverse=True):
        entry = _build_recalled_context_entry(
            block,
            status="skipped",
            reason=_CONTEXT_BUDGET_SKIP_REASON,
            reason_code="budget_trimmed",
        )
        if entry:
            recalled.append(entry)
    return recalled


def _build_recalled_context_entry(
    block: ContextBlock,
    *,
    status: str,
    reason: str | None = None,
    reason_code: str | None = None,
) -> dict | None:
    content = (block.content or "").strip()
    if not content:
        return None
    entry = {
        "kind": block.kind,
        "title": block.title,
        "source": block.source,
        "status": status,
        "reason": reason or _RECALL_REASONS.get(block.kind, "作为本回合上下文的一部分注入。"),
        "reason_code": reason_code or (block.kind if block.kind in _RECALL_REASONS else "default"),
        "preview": _truncate_context_preview(content, 140),
    }
    if block.preview_data is not None:
        entry["preview_data"] = dict(block.preview_data)
    return entry


def _truncate_context_preview(text: str, max_chars: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from one_person_dnd.web.labels import (
    ACTION_SIGNAL_LABELS,
    ACTION_TYPE_LABELS,
    ACTION_WARNING_LABELS,
    ADJUDICATION_INTENT_CODES,
)
from one_person_dnd.web.localization import Localizer


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _truncate(text: str, max_chars: int = 140) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _scene_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    lines: list[str] = []
    session_title = _text(data.get("session_title"))
    current_scene = _text(data.get("current_scene"))
    if session_title:
        lines.append(ui("game.recall.preview.session", value=session_title))
    if current_scene:
        lines.append(ui("game.recall.preview.scene", value=current_scene))
    return " ".join(lines)


def _character_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    lines: list[str] = []

    def add(key: str, value: object) -> None:
        cleaned = _text(value)
        if cleaned:
            lines.append(ui(key, value=cleaned))

    add("game.recall.preview.name", data.get("name"))
    identity = " / ".join(
        value
        for value in (_text(data.get("race")), _text(data.get("role")))
        if value
    )
    add("game.recall.preview.identity", identity)
    add("game.recall.preview.background", data.get("background"))
    add("game.recall.preview.goal", data.get("goal"))

    hp = data.get("hp")
    max_hp = data.get("max_hp")
    if hp is not None or max_hp is not None:
        hp_text = f"{hp}/{max_hp}" if hp is not None and max_hp is not None else _text(hp if hp is not None else max_hp)
        add("game.recall.preview.hp", hp_text)
    if data.get("gold") is not None:
        add("game.recall.preview.gold", data.get("gold"))
    if data.get("level") is not None:
        add("game.recall.preview.level", data.get("level"))

    separator = ui("character.list_separator")
    ability_separator = ui("character.ability_separator")
    inventory = _text_list(data.get("inventory"))
    conditions = _text_list(data.get("conditions"))
    skills = _text_list(data.get("skill_proficiencies"))
    if inventory:
        add("game.recall.preview.inventory", separator.join(inventory))
    if conditions:
        add("game.recall.preview.conditions", separator.join(conditions))
    abilities = data.get("abilities")
    if isinstance(abilities, Mapping):
        ability_parts = [
            f"{_text(key)} {_text(value)}"
            for key, value in abilities.items()
            if _text(key)
        ]
        if ability_parts:
            add("game.recall.preview.abilities", ability_separator.join(ability_parts))
    if skills:
        add("game.recall.preview.skills", separator.join(skills))
    add("game.recall.preview.notes", data.get("notes"))
    return " ".join(lines)


def _world_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    entry_type = _text(data.get("entry_type"))
    type_key = {
        "rule": "world.type.rule",
        "location": "world.type.location",
        "npc": "world.type.npc",
        "organization": "world.type.organization",
        "setting": "world.type.setting",
    }.get(entry_type.casefold())
    display_type = ui(type_key) if type_key else entry_type
    title = _text(data.get("title"))
    parts = [f"[{display_type}] {title}".strip()]
    tags = _text(data.get("tags"))
    if tags:
        parts.append(ui("game.recall.preview.tags", value=tags))
    content = _text(data.get("content"))
    if content:
        parts.append(content)
    return " ".join(part for part in parts if part)


def _plot_thread_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    thread_id = _text(data.get("id"))
    priority = _text(data.get("priority")) or "0"
    title = _text(data.get("title"))
    parts = [f"[#{thread_id} · P{priority}] {title}".strip()]
    for key, field in (
        ("game.recall.preview.tags", "tags"),
        ("game.recall.preview.progress", "summary"),
        ("game.recall.preview.next", "next_step"),
    ):
        value = _text(data.get(field))
        if value:
            parts.append(ui(key, value=value))
    return " ".join(part for part in parts if part)


def _story_memory_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    parts: list[str] = []
    for key, field in (
        ("game.recall.preview.story_scene", "scene"),
        ("game.recall.preview.story_summary", "summary"),
        ("game.recall.preview.unresolved", "open_threads"),
        ("game.recall.preview.key_facts", "key_facts"),
    ):
        value = _text(data.get(field))
        if value:
            parts.append(ui(key, value=value))
    return " ".join(parts)


def _story_summary_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    summary = _text(data.get("summary"))
    if not summary:
        return ""
    level = _text(data.get("level"))
    key = (
        "game.recall.preview.campaign_summary"
        if level == "campaign"
        else "game.recall.preview.chapter_summary"
    )
    return ui(key, value=summary)


def _action_assessment_preview(data: Mapping[str, Any], ui: Localizer) -> str:
    parts: list[str] = []
    action_type = _text(data.get("action_type"))
    if action_type:
        parts.append(
            ui(f"action.type.{action_type}")
            if action_type in ACTION_TYPE_LABELS
            else action_type
        )
    for signal in _text_list(data.get("signals")):
        parts.append(
            ui(f"action.signal.{signal}")
            if signal in ACTION_SIGNAL_LABELS
            else signal
        )
    for warning in _text_list(data.get("warnings")):
        parts.append(
            ui(f"action.warning.{warning}")
            if warning in ACTION_WARNING_LABELS
            else warning
        )

    check = data.get("check")
    if isinstance(check, Mapping):
        outcome = _text(check.get("outcome"))
        outcome_label = (
            ui("game.turn.success")
            if outcome == "success"
            else ui("game.turn.failure")
            if outcome == "failure"
            else outcome
        )
        ability_skill = " / ".join(
            value
            for value in (_text(check.get("ability")), _text(check.get("skill")))
            if value
        )
        parts.append(
            ui(
                "game.recall.preview.check",
                outcome=outcome_label,
                ability_skill=ability_skill,
                dc=_text(check.get("dc")),
                total=_text(check.get("total")),
            )
        )
        intent = _text(check.get("intent"))
        if intent:
            intent_code = ADJUDICATION_INTENT_CODES.get(intent)
            intent_label = ui(f"adjudication.intent.{intent_code}") if intent_code else intent
            parts.append(ui("game.turn.intent", intent=intent_label))
    return " · ".join(part for part in parts if part)


def present_recalled_context(
    items: Iterable[Mapping[str, Any]],
    *,
    ui: Localizer,
) -> list[dict[str, Any]]:
    """Project prompt metadata into request-localized UI text without mutating it."""
    presented: list[dict[str, Any]] = []
    for item in items:
        copy = dict(item)
        preview_data = copy.pop("preview_data", None)
        display_preview = ""
        if isinstance(preview_data, Mapping):
            preview_type = _text(preview_data.get("type"))
            if preview_type == "scene":
                display_preview = _scene_preview(preview_data, ui)
            elif preview_type == "character_summary":
                display_preview = _character_preview(preview_data, ui)
            elif preview_type == "world_bible":
                display_preview = _world_preview(preview_data, ui)
            elif preview_type == "plot_thread":
                display_preview = _plot_thread_preview(preview_data, ui)
            elif preview_type == "story_memory":
                display_preview = _story_memory_preview(preview_data, ui)
            elif preview_type == "story_summary":
                display_preview = _story_summary_preview(preview_data, ui)
            elif preview_type == "action_assessment":
                display_preview = _action_assessment_preview(preview_data, ui)
        if display_preview:
            copy["display_preview"] = _truncate(display_preview)
        presented.append(copy)
    return presented


__all__ = ["present_recalled_context"]

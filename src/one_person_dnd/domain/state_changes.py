from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from one_person_dnd.domain.characters import summarize_character_sheet


@dataclass(frozen=True)
class StateChangePreview:
    ok: bool
    summary: str
    lines: list[str]


def merge_state_delta(base: Any, delta: Any) -> Any:
    if isinstance(base, dict) and isinstance(delta, dict):
        out = dict(base)
        for key, value in delta.items():
            out[key] = merge_state_delta(out[key], value) if key in out else value
        return out

    if isinstance(base, list) and isinstance(delta, list):
        if any(isinstance(v, dict) for v in delta):
            # Dict-element lists (e.g. "party") are merged by index rather than replaced
            # outright, so a partial delta like {"party": [{"hp": 6}]} only updates the
            # fields it mentions and doesn't erase the other fields of that party member.
            merged = list(base)
            for idx, value in enumerate(delta):
                if idx < len(merged):
                    if isinstance(merged[idx], dict) and isinstance(value, dict):
                        merged[idx] = merge_state_delta(merged[idx], value)
                    else:
                        merged[idx] = value
                else:
                    merged.append(value)
            return merged

        # Scalar-element lists (inventory/conditions/abilities/etc.) are replaced wholesale.
        # Index-merging scalars can only grow or overwrite a list, never shrink it, so a
        # shorter delta (e.g. removing a used-up item from inventory) would silently no-op.
        return list(delta)

    return delta


def _load_json_obj(text: str, *, default: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    fallback = default if default is not None else {}
    raw = (text or "").strip()
    if not raw:
        return fallback, ""
    try:
        loaded = json.loads(raw)
    except Exception as exc:
        return fallback, f"JSON 解析失败：{exc}"
    if not isinstance(loaded, dict):
        return fallback, "JSON 根必须是对象"
    return loaded, ""


def _text(value: Any, *, empty: str = "未设置") -> str:
    if value is None or value == "":
        return empty
    return str(value)


def _inventory_text(items: list[str]) -> str:
    return "、".join(items) if items else "无"


def preview_state_delta(base_sheet_text: str, delta_json_text: str) -> StateChangePreview:
    base, _base_error = _load_json_obj(base_sheet_text)
    delta, delta_error = _load_json_obj(delta_json_text)
    if delta_error:
        return StateChangePreview(ok=False, summary="无法预览变更", lines=[delta_error])

    merged = merge_state_delta(base, delta)
    before = summarize_character_sheet(json.dumps(base, ensure_ascii=False))
    after = summarize_character_sheet(json.dumps(merged, ensure_ascii=False))

    lines: list[str] = []
    if before.name != after.name:
        lines.append(f"名称：{_text(before.name)} -> {_text(after.name)}")
    if before.role != after.role:
        lines.append(f"职业：{_text(before.role)} -> {_text(after.role)}")
    if before.hp != after.hp:
        lines.append(f"HP：{_text(before.hp)} -> {_text(after.hp)}")
    if before.max_hp != after.max_hp:
        lines.append(f"HP 上限：{_text(before.max_hp)} -> {_text(after.max_hp)}")
    if before.gold != after.gold:
        lines.append(f"金币：{_text(before.gold)} -> {_text(after.gold)}")
    if before.inventory != after.inventory:
        lines.append(f"物品：{_inventory_text(before.inventory)} -> {_inventory_text(after.inventory)}")
    if before.goal != after.goal:
        lines.append(f"目标：{_text(before.goal)} -> {_text(after.goal)}")

    if lines:
        return StateChangePreview(ok=True, summary="将更新角色状态", lines=lines)

    keys = "、".join(sorted(delta.keys())) if delta else "空对象"
    return StateChangePreview(ok=True, summary="包含未识别字段变更", lines=[f"JSON 字段：{keys}"])

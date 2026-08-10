from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from one_person_dnd.domain.characters import summarize_character_sheet


@dataclass(frozen=True)
class StateChangePreview:
    ok: bool
    summary: str
    lines: list[str]


class PreviewTranslator(Protocol):
    def __call__(self, key: str, /, **values: object) -> str: ...


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


def _message(
    translator: PreviewTranslator | None,
    key: str,
    fallback: str,
    **values: object,
) -> str:
    return fallback if translator is None else translator(key, **values)


def _text(
    value: Any,
    *,
    translator: PreviewTranslator | None = None,
    empty: str = "未设置",
) -> str:
    if value is None or value == "":
        return _message(translator, "preview.value.unset", empty)
    return str(value)


def _inventory_text(items: list[str], *, translator: PreviewTranslator | None = None) -> str:
    if not items:
        return _message(translator, "preview.value.none", "无")
    separator = _message(translator, "preview.separator.list", "、")
    return separator.join(items)


def _change_line(
    translator: PreviewTranslator | None,
    key: str,
    label: str,
    before: str,
    after: str,
) -> str:
    return _message(
        translator,
        key,
        f"{label}：{before} -> {after}",
        before=before,
        after=after,
    )


def preview_state_delta(
    base_sheet_text: str,
    delta_json_text: str,
    *,
    translator: PreviewTranslator | None = None,
) -> StateChangePreview:
    base, _base_error = _load_json_obj(base_sheet_text)
    delta, delta_error = _load_json_obj(delta_json_text)
    if delta_error:
        return StateChangePreview(
            ok=False,
            summary=_message(translator, "preview.state.invalid_summary", "无法预览变更"),
            lines=[
                delta_error
                if translator is None
                else translator("preview.state.invalid_detail")
            ],
        )

    merged = merge_state_delta(base, delta)
    before = summarize_character_sheet(json.dumps(base, ensure_ascii=False))
    after = summarize_character_sheet(json.dumps(merged, ensure_ascii=False))

    lines: list[str] = []
    if before.name != after.name:
        lines.append(
            _change_line(
                translator,
                "preview.state.name",
                "名称",
                _text(before.name, translator=translator),
                _text(after.name, translator=translator),
            )
        )
    if before.role != after.role:
        lines.append(
            _change_line(
                translator,
                "preview.state.role",
                "职业",
                _text(before.role, translator=translator),
                _text(after.role, translator=translator),
            )
        )
    if before.hp != after.hp:
        lines.append(
            _change_line(
                translator,
                "preview.state.hp",
                "HP",
                _text(before.hp, translator=translator),
                _text(after.hp, translator=translator),
            )
        )
    if before.max_hp != after.max_hp:
        lines.append(
            _change_line(
                translator,
                "preview.state.max_hp",
                "HP 上限",
                _text(before.max_hp, translator=translator),
                _text(after.max_hp, translator=translator),
            )
        )
    if before.gold != after.gold:
        lines.append(
            _change_line(
                translator,
                "preview.state.gold",
                "金币",
                _text(before.gold, translator=translator),
                _text(after.gold, translator=translator),
            )
        )
    if before.inventory != after.inventory:
        lines.append(
            _change_line(
                translator,
                "preview.state.inventory",
                "物品",
                _inventory_text(before.inventory, translator=translator),
                _inventory_text(after.inventory, translator=translator),
            )
        )
    if before.goal != after.goal:
        lines.append(
            _change_line(
                translator,
                "preview.state.goal",
                "目标",
                _text(before.goal, translator=translator),
                _text(after.goal, translator=translator),
            )
        )

    if lines:
        return StateChangePreview(
            ok=True,
            summary=_message(translator, "preview.state.summary", "将更新角色状态"),
            lines=lines,
        )

    if delta:
        key_separator = _message(translator, "preview.separator.fields", "、")
        keys = key_separator.join(sorted(delta.keys()))
    else:
        keys = _message(translator, "preview.value.empty_object", "空对象")
    return StateChangePreview(
        ok=True,
        summary=_message(
            translator,
            "preview.state.unrecognized_summary",
            "包含未识别字段变更",
        ),
        lines=[
            _message(
                translator,
                "preview.state.json_fields",
                f"JSON 字段：{keys}",
                fields=keys,
            )
        ],
    )

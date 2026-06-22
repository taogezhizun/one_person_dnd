from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_as_text(v) for v in value if _as_text(v)]
    if isinstance(value, str):
        return [p.strip() for p in value.replace("，", ",").split(",") if p.strip()]
    return []


@dataclass(frozen=True)
class CharacterSummary:
    name: str = ""
    race: str = ""
    role: str = ""
    background: str = ""
    goal: str = ""
    hp: int | None = None
    max_hp: int | None = None
    gold: int | None = None
    inventory: list[str] = field(default_factory=list)
    abilities: dict[str, Any] = field(default_factory=dict)
    conditions: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def has_content(self) -> bool:
        return any(
            [
                self.name,
                self.race,
                self.role,
                self.background,
                self.goal,
                self.hp is not None,
                self.max_hp is not None,
                self.gold is not None,
                self.inventory,
                self.abilities,
                self.conditions,
                self.notes,
            ]
        )

    def to_prompt_text(self) -> str:
        if not self.has_content:
            return ""

        lines: list[str] = []
        if self.name:
            lines.append(f"名称：{self.name}")
        if self.race or self.role:
            if self.race and self.role:
                lines.append(f"种族/职业：{self.race} / {self.role}")
            else:
                lines.append(f"种族/职业：{self.race or self.role}")
        if self.background:
            lines.append(f"背景：{self.background}")
        if self.goal:
            lines.append(f"目标：{self.goal}")
        if self.hp is not None or self.max_hp is not None:
            if self.hp is not None and self.max_hp is not None:
                lines.append(f"HP：{self.hp}/{self.max_hp}")
            else:
                lines.append(f"HP：{self.hp if self.hp is not None else self.max_hp}")
        if self.gold is not None:
            lines.append(f"金币：{self.gold}")
        if self.inventory:
            lines.append("物品：" + "、".join(self.inventory))
        if self.conditions:
            lines.append("状态：" + "、".join(self.conditions))
        if self.abilities:
            ability_parts = [f"{k} {v}" for k, v in self.abilities.items() if _as_text(k)]
            if ability_parts:
                lines.append("属性：" + "，".join(ability_parts))
        if self.notes:
            lines.append(f"备注：{self.notes}")
        return "\n".join(lines).strip()


def _first_party_member(obj: dict[str, Any]) -> dict[str, Any]:
    party = obj.get("party")
    if isinstance(party, list) and party and isinstance(party[0], dict):
        return party[0]
    return obj


def summarize_character_sheet(sheet_text: str) -> CharacterSummary:
    try:
        loaded = json.loads(sheet_text or "{}")
    except Exception:
        return CharacterSummary()
    if not isinstance(loaded, dict):
        return CharacterSummary()

    member = _first_party_member(loaded)
    abilities = member.get("abilities") or member.get("ability_scores") or loaded.get("abilities") or {}
    if not isinstance(abilities, dict):
        abilities = {}

    return CharacterSummary(
        name=_as_text(member.get("name") or loaded.get("name")),
        race=_as_text(member.get("race") or member.get("ancestry") or member.get("species") or loaded.get("race")),
        role=_as_text(member.get("class") or member.get("job") or member.get("profession") or loaded.get("class")),
        background=_as_text(member.get("background") or loaded.get("background")),
        goal=_as_text(member.get("goal") or loaded.get("goal")),
        hp=_as_int(member.get("hp") if "hp" in member else loaded.get("hp")),
        max_hp=_as_int(member.get("max_hp") or member.get("hp_max") or loaded.get("max_hp") or loaded.get("hp_max")),
        gold=_as_int(member.get("gold") if "gold" in member else loaded.get("gold")),
        inventory=_as_text_list(member.get("inventory") if "inventory" in member else loaded.get("inventory")),
        abilities=dict(abilities),
        conditions=_as_text_list(member.get("conditions") if "conditions" in member else loaded.get("conditions")),
        notes=_as_text(member.get("notes") or loaded.get("notes")),
    )

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


CANONICAL_ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

_ABILITY_ALIASES = {
    "str": "STR",
    "strength": "STR",
    "力量": "STR",
    "dex": "DEX",
    "dexterity": "DEX",
    "敏捷": "DEX",
    "con": "CON",
    "constitution": "CON",
    "体质": "CON",
    "int": "INT",
    "intelligence": "INT",
    "智力": "INT",
    "wis": "WIS",
    "wisdom": "WIS",
    "感知": "WIS",
    "cha": "CHA",
    "charisma": "CHA",
    "魅力": "CHA",
}

_SKILL_ALIASES = {
    "acrobatics": "Acrobatics",
    "杂技": "Acrobatics",
    "animal handling": "Animal Handling",
    "animal_handling": "Animal Handling",
    "驯兽": "Animal Handling",
    "arcana": "Arcana",
    "奥秘": "Arcana",
    "athletics": "Athletics",
    "运动": "Athletics",
    "deception": "Deception",
    "欺骗": "Deception",
    "history": "History",
    "历史": "History",
    "insight": "Insight",
    "洞悉": "Insight",
    "intimidation": "Intimidation",
    "威吓": "Intimidation",
    "investigation": "Investigation",
    "调查": "Investigation",
    "medicine": "Medicine",
    "医药": "Medicine",
    "nature": "Nature",
    "自然": "Nature",
    "perception": "Perception",
    "察觉": "Perception",
    "performance": "Performance",
    "表演": "Performance",
    "persuasion": "Persuasion",
    "说服": "Persuasion",
    "religion": "Religion",
    "宗教": "Religion",
    "sleight of hand": "Sleight of Hand",
    "sleight_of_hand": "Sleight of Hand",
    "巧手": "Sleight of Hand",
    "stealth": "Stealth",
    "隐匿": "Stealth",
    "survival": "Survival",
    "生存": "Survival",
}


class CharacterSheetValidationError(ValueError):
    """A generated character sheet cannot safely become canonical state."""


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


def canonical_ability_name(value: Any) -> str | None:
    key = _as_text(value).casefold()
    return _ABILITY_ALIASES.get(key)


def canonical_skill_name(value: Any) -> str | None:
    key = " ".join(_as_text(value).replace("-", " ").split()).casefold()
    return _SKILL_ALIASES.get(key)


def normalize_generated_character_sheet(sheet: Any) -> dict[str, Any]:
    """Return a rules-ready new-adventure sheet or raise an actionable error."""
    if not isinstance(sheet, dict):
        raise CharacterSheetValidationError("生成结果中的角色卡必须是对象")
    party = sheet.get("party")
    if not isinstance(party, list) or not party:
        raise CharacterSheetValidationError("生成结果中的角色卡必须包含至少一名 party 角色")

    normalized_party: list[dict[str, Any]] = []
    for index, member in enumerate(party, start=1):
        if not isinstance(member, dict):
            raise CharacterSheetValidationError(f"角色 {index} 必须是对象")

        raw_abilities = member.get("abilities", {})
        if not isinstance(raw_abilities, dict):
            raise CharacterSheetValidationError(f"角色 {index} 的 abilities 必须是对象")
        missing_abilities = [
            ability for ability in CANONICAL_ABILITIES if ability not in raw_abilities
        ]
        if missing_abilities:
            raise CharacterSheetValidationError(
                f"角色 {index} 缺少 canonical 属性：{', '.join(missing_abilities)}"
            )
        abilities: dict[str, int] = {}
        for ability in CANONICAL_ABILITIES:
            value = raw_abilities[ability]
            if type(value) is not int or not 1 <= value <= 30:
                raise CharacterSheetValidationError(
                    f"角色 {index} 的 {ability} 必须是 1-30 的整数"
                )
            abilities[ability] = value

        if "level" not in member:
            raise CharacterSheetValidationError(f"角色 {index} 必须提供 level")
        raw_level = member["level"]
        if type(raw_level) is not int or not 1 <= raw_level <= 20:
            raise CharacterSheetValidationError(
                f"角色 {index} 的 level 必须是 1-20 的整数"
            )
        level = raw_level

        if "skill_proficiencies" not in member:
            raise CharacterSheetValidationError(
                f"角色 {index} 必须提供 skill_proficiencies"
            )
        raw_skills = member["skill_proficiencies"]
        if isinstance(raw_skills, str):
            skill_items = raw_skills.replace("，", ",").split(",")
        elif isinstance(raw_skills, list):
            skill_items = raw_skills
        else:
            raise CharacterSheetValidationError(
                f"角色 {index} 的 skill_proficiencies 必须是数组或逗号分隔字符串"
            )

        skills: list[str] = []
        for raw_skill in skill_items:
            skill = canonical_skill_name(raw_skill)
            if skill is None:
                raise CharacterSheetValidationError(
                    f"角色 {index} 包含未知技能：{_as_text(raw_skill) or '空值'}"
                )
            if skill not in skills:
                skills.append(skill)

        normalized = dict(member)
        normalized["level"] = level
        normalized["abilities"] = abilities
        normalized["skill_proficiencies"] = skills
        normalized_party.append(normalized)

    normalized_sheet = dict(sheet)
    normalized_sheet["party"] = normalized_party
    return normalized_sheet


def _normalize_ability_scores(value: Any) -> tuple[dict[str, int], list[str]]:
    if not isinstance(value, dict):
        return {}, list(CANONICAL_ABILITIES)

    scores: dict[str, int] = {}
    invalid: list[str] = []
    for raw_key, raw_value in value.items():
        ability = canonical_ability_name(raw_key)
        if ability is None:
            continue
        if isinstance(raw_value, bool) or not isinstance(raw_value, int) or not 1 <= raw_value <= 30:
            invalid.append(ability)
            scores.pop(ability, None)
            continue
        previous = scores.get(ability)
        if previous is not None and previous != raw_value:
            invalid.append(ability)
            scores.pop(ability, None)
            continue
        if ability not in invalid:
            scores[ability] = raw_value
    return scores, list(dict.fromkeys(invalid))


def _normalize_skill_proficiencies(value: Any) -> tuple[list[str], list[str]]:
    raw_items: list[Any]
    if isinstance(value, dict):
        raw_items = [
            key
            for key, enabled in value.items()
            if enabled is True or (isinstance(enabled, str) and enabled.strip().casefold() in {"proficient", "熟练"})
        ]
    else:
        raw_items = _as_text_list(value)

    skills: list[str] = []
    invalid: list[str] = []
    for raw in raw_items:
        skill = canonical_skill_name(raw)
        if skill is None:
            invalid.append(_as_text(raw))
        elif skill not in skills:
            skills.append(skill)
    return skills, [item for item in invalid if item]


def _normalize_check_source_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_sources in value.items():
        raw_key_text = _as_text(raw_key)
        key = canonical_skill_name(raw_key_text) or canonical_ability_name(raw_key_text)
        if raw_key_text in {"*", "all", "全部"}:
            key = "*"
        if key is None:
            continue
        sources = _as_text_list(raw_sources)
        if sources:
            normalized.setdefault(key, []).extend(source for source in sources if source not in normalized.get(key, []))
    return normalized


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
    level: int | None = None
    ability_scores: dict[str, int] = field(default_factory=dict)
    skill_proficiencies: list[str] = field(default_factory=list)
    check_advantages: dict[str, list[str]] = field(default_factory=dict)
    check_disadvantages: dict[str, list[str]] = field(default_factory=dict)
    invalid_ability_scores: list[str] = field(default_factory=list)
    level_invalid: bool = False
    rule_warnings: list[str] = field(default_factory=list)
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
                self.level is not None,
                self.skill_proficiencies,
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
        if self.level is not None:
            lines.append(f"等级：{self.level}")
        if self.inventory:
            lines.append("物品：" + "、".join(self.inventory))
        if self.conditions:
            lines.append("状态：" + "、".join(self.conditions))
        if self.abilities:
            ability_parts = [f"{k} {v}" for k, v in self.abilities.items() if _as_text(k)]
            if ability_parts:
                lines.append("属性：" + "，".join(ability_parts))
        if self.skill_proficiencies:
            lines.append("技能熟练：" + "、".join(self.skill_proficiencies))
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
        return CharacterSummary(
            invalid_ability_scores=list(CANONICAL_ABILITIES),
            rule_warnings=["invalid_character_sheet"],
        )
    if not isinstance(loaded, dict):
        return CharacterSummary(
            invalid_ability_scores=list(CANONICAL_ABILITIES),
            rule_warnings=["invalid_character_sheet"],
        )

    member = _first_party_member(loaded)
    raw_abilities: Any = {}
    for source, key in (
        (member, "ability_scores"),
        (member, "abilities"),
        (loaded, "ability_scores"),
        (loaded, "abilities"),
    ):
        if key in source:
            raw_abilities = source[key]
            break

    ability_scores, invalid_abilities = _normalize_ability_scores(raw_abilities)
    abilities = dict(raw_abilities) if isinstance(raw_abilities, dict) else {}
    raw_level = member.get("level") if "level" in member else loaded.get("level")
    level = raw_level if isinstance(raw_level, int) and not isinstance(raw_level, bool) and 1 <= raw_level <= 20 else None
    level_invalid = raw_level not in (None, "") and level is None
    raw_skills = (
        member.get("skill_proficiencies")
        if "skill_proficiencies" in member
        else member.get("skills", loaded.get("skill_proficiencies", loaded.get("skills")))
    )
    skill_proficiencies, invalid_skills = _normalize_skill_proficiencies(raw_skills)
    rule_warnings: list[str] = []
    if invalid_abilities:
        rule_warnings.append("invalid_ability_scores")
    if level_invalid:
        rule_warnings.append("invalid_level")
    if invalid_skills:
        rule_warnings.append("unknown_skill_proficiencies")

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
        level=level,
        ability_scores=ability_scores,
        skill_proficiencies=skill_proficiencies,
        check_advantages=_normalize_check_source_map(
            member.get("check_advantages", loaded.get("check_advantages"))
        ),
        check_disadvantages=_normalize_check_source_map(
            member.get("check_disadvantages", loaded.get("check_disadvantages"))
        ),
        invalid_ability_scores=invalid_abilities,
        level_invalid=level_invalid,
        rule_warnings=rule_warnings,
        conditions=_as_text_list(member.get("conditions") if "conditions" in member else loaded.get("conditions")),
        notes=_as_text(member.get("notes") or loaded.get("notes")),
    )

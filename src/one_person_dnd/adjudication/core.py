from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol

from one_person_dnd.domain.actions import (
    ActionAssessment,
    PlayerAction,
    action_language_flags,
    classify_action_text,
)
from one_person_dnd.domain.characters import CharacterSummary, summarize_character_sheet
from one_person_dnd.engine.dice import DiceEvent, parse_roll_expr

POLICY_VERSION = "srd_5_2_1_solo_checks_v1"

AdjudicationStatus = Literal["no_check", "resolved", "needs_input", "unsupported"]
RollMode = Literal["normal", "advantage", "disadvantage"]
Outcome = Literal["success", "failure"]

_MANUAL_ROLL_RE = re.compile(r"(?i)\b(\d{0,3}d\d{1,4}(?:[+-]\d{1,5})?)\b")
_UNSUPPORTED_MARKERS = (
    "豁免",
    "攻击检定",
    "伤害",
    "格挡",
    "招架",
    "闪避攻击",
    "躲避火球",
    "抵抗毒素",
    "死亡豁免",
    "saving throw",
)

# A rule is selected only for a concrete, uncertain attempt.  Ordinary movement,
# conversation, inventory use, and other routine prose deliberately match none.
_CHECK_RULES: tuple[tuple[tuple[str, ...], str, str | None, str], ...] = (
    (("欺骗", "撒谎", "伪装说辞", "deceive", "lie"), "CHA", "Deception", "用谎言误导对方"),
    (("威胁", "恐吓", "威吓", "intimidate"), "CHA", "Intimidation", "迫使对方屈服"),
    (("说服", "交涉", "谈判", "persuade", "negotiate"), "CHA", "Persuasion", "改变对方的决定"),
    (("洞悉", "察言观色", "判断是否撒谎", "insight"), "WIS", "Insight", "判断他人的真实意图"),
    (("潜行", "隐匿", "躲藏", "悄悄", "stealth", "sneak"), "DEX", "Stealth", "避免被发现"),
    (("翻越", "保持平衡", "走钢丝", "杂技", "acrobatics"), "DEX", "Acrobatics", "以灵巧动作克服障碍"),
    (("攀爬", "游泳", "跳跃", "挣脱", "推开沉重", "撬开", "athletics"), "STR", "Athletics", "以力量克服障碍"),
    (("扒窃", "偷走", "藏起物品", "巧手", "sleight of hand"), "DEX", "Sleight of Hand", "不被察觉地操纵物品"),
    (("开锁", "撬锁", "锁住的门", "上锁的门", "pick the lock"), "DEX", None, "打开上锁的装置"),
    (("调查", "搜索机关", "推理", "破解机关", "investigate"), "INT", "Investigation", "从线索推导结论"),
    (("观察", "察觉", "聆听", "留意", "perception"), "WIS", "Perception", "发现不明显的线索"),
    (("追踪", "求生", "辨认足迹", "survival"), "WIS", "Survival", "在野外追踪或求生"),
    (("奥秘", "辨认魔法", "魔法知识", "arcana"), "INT", "Arcana", "回忆或辨认奥术知识"),
    (("回忆历史", "历史知识", "history"), "INT", "History", "回忆历史知识"),
    (("自然知识", "辨认植物", "辨认野兽", "nature"), "INT", "Nature", "辨认自然知识"),
    (("宗教知识", "辨认神徽", "religion"), "INT", "Religion", "回忆宗教知识"),
    (("医治", "诊断伤势", "医药", "medicine"), "WIS", "Medicine", "判断或处理伤病"),
    (("驯服", "安抚动物", "驯兽", "animal handling"), "WIS", "Animal Handling", "控制或安抚动物"),
    (("表演", "演奏", "演讲", "performance"), "CHA", "Performance", "以表演影响观众"),
)


class InvalidAdjudicationInput(ValueError):
    pass


class AttemptConflict(RuntimeError):
    pass


class AdjudicationStoreBusy(RuntimeError):
    pass


class AdjudicationStoreCorrupt(RuntimeError):
    pass


def _is_sqlite_busy_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).casefold() for marker in ("locked", "busy")
    )


class D20Roller(Protocol):
    def roll(self, sides: int = 20) -> int: ...


class SystemRoller:
    def roll(self, sides: int = 20) -> int:
        if sides < 2:
            raise ValueError("dice must have at least two sides")
        return secrets.randbelow(sides) + 1


class SequenceRoller:
    """Fixed roller used by interface tests and deterministic local simulations."""

    def __init__(self, values: list[int] | tuple[int, ...]) -> None:
        self._values = list(values)
        self.calls = 0

    def roll(self, sides: int = 20) -> int:
        if not self._values:
            raise AssertionError("SequenceRoller exhausted")
        value = int(self._values.pop(0))
        self.calls += 1
        if not 1 <= value <= sides:
            raise AssertionError(f"fixed roll {value} is outside 1..{sides}")
        return value


@dataclass(frozen=True)
class AdjudicationRequest:
    attempt_id: str
    action: PlayerAction


@dataclass(frozen=True)
class CheckResolution:
    test_kind: Literal["ability_check"]
    ability: Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    skill: str | None
    intent: str
    dc: int
    dc_reason: str
    roll_mode: RollMode
    d20s: tuple[int, ...]
    selected_d20: int
    natural_face: Literal["natural_1", "natural_20"] | None
    ability_score: int
    ability_modifier: int
    proficiency_modifier: int
    circumstance_modifier: int
    modifier_sources: tuple[str, ...]
    advantage_sources: tuple[str, ...]
    disadvantage_sources: tuple[str, ...]
    total: int
    margin: int
    outcome: Outcome

    def __post_init__(self) -> None:
        if self.test_kind != "ability_check":
            raise ValueError("only ability_check is supported")
        if self.ability not in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
            raise ValueError("invalid ability")
        if self.roll_mode not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("invalid roll mode")
        if self.roll_mode == "normal" and len(self.d20s) != 1:
            raise ValueError("normal checks roll one d20")
        if self.roll_mode in {"advantage", "disadvantage"} and len(self.d20s) != 2:
            raise ValueError("advantage/disadvantage checks roll two d20s")
        if not self.d20s or any(not 1 <= value <= 20 for value in self.d20s):
            raise ValueError("invalid d20 face")
        expected_selected = (
            max(self.d20s)
            if self.roll_mode == "advantage"
            else min(self.d20s)
            if self.roll_mode == "disadvantage"
            else self.d20s[0]
        )
        if self.selected_d20 != expected_selected:
            raise ValueError("selected d20 does not match roll mode")
        if not 1 <= self.ability_score <= 30:
            raise ValueError("ability score must be in 1..30")
        if self.dc not in {5, 10, 15, 20, 25, 30}:
            raise ValueError("DC must use the adopted SRD difficulty ladder")
        if self.proficiency_modifier not in {0, 2, 3, 4, 5, 6}:
            raise ValueError("invalid proficiency modifier")
        if not -10 <= self.circumstance_modifier <= 10:
            raise ValueError("circumstance modifier is outside the supported range")
        if self.ability_modifier != (self.ability_score - 10) // 2:
            raise ValueError("ability modifier does not match score")
        expected_total = (
            self.selected_d20
            + self.ability_modifier
            + self.proficiency_modifier
            + self.circumstance_modifier
        )
        if self.total != expected_total or self.margin != self.total - self.dc:
            raise ValueError("check arithmetic is inconsistent")
        if self.outcome != ("success" if self.total >= self.dc else "failure"):
            raise ValueError("ability-check outcome must follow total versus DC")
        expected_face = "natural_1" if self.selected_d20 == 1 else "natural_20" if self.selected_d20 == 20 else None
        if self.natural_face != expected_face:
            raise ValueError("natural face label is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_kind": self.test_kind,
            "ability": self.ability,
            "skill": self.skill,
            "intent": self.intent,
            "dc": self.dc,
            "dc_reason": self.dc_reason,
            "roll_mode": self.roll_mode,
            "d20s": list(self.d20s),
            "selected_d20": self.selected_d20,
            "natural_face": self.natural_face,
            "ability_score": self.ability_score,
            "ability_modifier": self.ability_modifier,
            "proficiency_modifier": self.proficiency_modifier,
            "circumstance_modifier": self.circumstance_modifier,
            "modifier_sources": list(self.modifier_sources),
            "advantage_sources": list(self.advantage_sources),
            "disadvantage_sources": list(self.disadvantage_sources),
            "total": self.total,
            "margin": self.margin,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CheckResolution":
        return cls(
            test_kind=str(value["test_kind"]),  # type: ignore[arg-type]
            ability=str(value["ability"]),  # type: ignore[arg-type]
            skill=str(value["skill"]) if value.get("skill") else None,
            intent=str(value.get("intent") or ""),
            dc=int(value["dc"]),
            dc_reason=str(value.get("dc_reason") or ""),
            roll_mode=str(value["roll_mode"]),  # type: ignore[arg-type]
            d20s=tuple(int(item) for item in value["d20s"]),
            selected_d20=int(value["selected_d20"]),
            natural_face=str(value["natural_face"]) if value.get("natural_face") else None,  # type: ignore[arg-type]
            ability_score=int(value["ability_score"]),
            ability_modifier=int(value["ability_modifier"]),
            proficiency_modifier=int(value["proficiency_modifier"]),
            circumstance_modifier=int(value["circumstance_modifier"]),
            modifier_sources=tuple(str(item) for item in value.get("modifier_sources", [])),
            advantage_sources=tuple(str(item) for item in value.get("advantage_sources", [])),
            disadvantage_sources=tuple(str(item) for item in value.get("disadvantage_sources", [])),
            total=int(value["total"]),
            margin=int(value["margin"]),
            outcome=str(value["outcome"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class AdjudicationRecord:
    attempt_id: str
    policy_version: str
    request_fingerprint: str
    status: AdjudicationStatus
    action_type: str
    check: CheckResolution | None
    manual_rolls: tuple[DiceEvent, ...]
    signals: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.attempt_id.strip() or len(self.attempt_id) > 128:
            raise ValueError("invalid adjudication attempt identity")
        if not self.policy_version.strip() or not self.request_fingerprint.strip():
            raise ValueError("adjudication policy and fingerprint are required")
        if self.status not in {"no_check", "resolved", "needs_input", "unsupported"}:
            raise ValueError("invalid adjudication status")
        if (self.status == "resolved") != (self.check is not None):
            raise ValueError("only resolved records may contain a canonical check")
        if self.check is not None and self.manual_rolls:
            raise ValueError("manual rolls cannot also be a canonical ability check")
        for event in self.manual_rolls:
            count = int(event["count"])
            sides = int(event["sides"])
            modifier = int(event["modifier"])
            rolls = [int(item) for item in event["rolls"]]
            if count != len(rolls) or count < 1 or sides < 2:
                raise ValueError("manual roll shape is inconsistent")
            if any(not 1 <= item <= sides for item in rolls):
                raise ValueError("manual roll contains an invalid face")
            if int(event["total"]) != sum(rolls) + modifier:
                raise ValueError("manual roll arithmetic is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "policy_version": self.policy_version,
            "request_fingerprint": self.request_fingerprint,
            "status": self.status,
            "action_type": self.action_type,
            "check": self.check.to_dict() if self.check else None,
            "manual_rolls": [dict(event) for event in self.manual_rolls],
            "signals": list(self.signals),
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AdjudicationRecord":
        raw_check = value.get("check")
        raw_manual = value.get("manual_rolls") or []
        if not isinstance(raw_manual, list) or any(not isinstance(item, dict) for item in raw_manual):
            raise ValueError("manual_rolls must be a list of objects")
        return cls(
            attempt_id=str(value["attempt_id"]),
            policy_version=str(value["policy_version"]),
            request_fingerprint=str(value["request_fingerprint"]),
            status=str(value["status"]),  # type: ignore[arg-type]
            action_type=str(value["action_type"]),
            check=CheckResolution.from_dict(raw_check) if isinstance(raw_check, Mapping) else None,
            manual_rolls=tuple(dict(item) for item in raw_manual),  # type: ignore[arg-type]
            signals=tuple(str(item) for item in value.get("signals", [])),
            warnings=tuple(str(item) for item in value.get("warnings", [])),
        )

    @classmethod
    def from_json(cls, raw: str) -> "AdjudicationRecord":
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("adjudication record must be an object")
        return cls.from_dict(value)

    def to_action_assessment(self) -> ActionAssessment:
        dice_events = [dict(event) for event in self.manual_rolls]
        if self.check is not None:
            modifier = (
                self.check.ability_modifier
                + self.check.proficiency_modifier
                + self.check.circumstance_modifier
            )
            mode_label = "" if self.check.roll_mode == "normal" else f" ({self.check.roll_mode})"
            dice_events.append(
                {
                    "expr": f"d20{modifier:+d}{mode_label}",
                    "count": len(self.check.d20s),
                    "sides": 20,
                    "modifier": modifier,
                    "rolls": list(self.check.d20s),
                    "total": self.check.total,
                }
            )
        return ActionAssessment(
            action_type=self.action_type,
            dice_events=dice_events,  # type: ignore[arg-type]
            signals=list(self.signals),
            warnings=list(self.warnings),
            adjudication=self,
        )


@dataclass(frozen=True)
class _SelectedCheck:
    ability: str
    skill: str | None
    intent: str


@dataclass(frozen=True)
class _SceneFacts:
    dc: int = 15
    dc_reason: str = "缺少可信结构化难度事实，使用标准 DC 15。"
    circumstance_modifier: int = 0
    circumstance_reason: str = ""
    advantage_sources: tuple[str, ...] = ()
    disadvantage_sources: tuple[str, ...] = ()


CharacterLoader = Callable[[PlayerAction], CharacterSummary]


class ActionAdjudicator:
    """Deep module for one immutable SRD 5.2.1-style ability check."""

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        roller: D20Roller | None = None,
        character_loader: CharacterLoader | None = None,
    ) -> None:
        self._conn = conn
        self._roller = roller or SystemRoller()
        self._character_loader = character_loader
        self._memory_records: dict[tuple[int, str], AdjudicationRecord] = {}

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationRecord:
        attempt_id, action = self._validate_request(request)
        fingerprint = _request_fingerprint(action)
        existing = self._get_existing(action.session_id, attempt_id)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise AttemptConflict("同一 attempt_id 不能用于不同的玩家行动")
            return existing

        action_type = classify_action_text(action.text)
        manual_rolls = self._roll_manual_expressions(action.text)
        signals, warnings = action_language_flags(
            action.text,
            action_type=action_type,
            has_manual_roll=bool(manual_rolls),
        )

        lowered = action.text.casefold()
        if action_type == "combat" or any(marker.casefold() in lowered for marker in _UNSUPPORTED_MARKERS):
            record = self._record(
                attempt_id,
                fingerprint,
                "unsupported",
                action_type,
                None,
                manual_rolls,
                signals + ["adjudication_unsupported"],
                warnings + ["unsupported_attack_save_or_combat"],
            )
            return self._store(action.session_id, record)

        # A player-supplied roll is retained as evidence, but it is never promoted
        # into a canonical check or combined with character modifiers.
        if manual_rolls:
            record = self._record(
                attempt_id,
                fingerprint,
                "no_check",
                action_type,
                None,
                manual_rolls,
                signals + ["manual_roll_not_canonical"],
                warnings,
            )
            return self._store(action.session_id, record)

        selected = _select_check(action.text)
        if selected is None:
            record = self._record(
                attempt_id,
                fingerprint,
                "no_check",
                action_type,
                None,
                (),
                _without(signals, "roll_may_be_needed") + ["no_check_needed"],
                warnings,
            )
            return self._store(action.session_id, record)

        character = self._load_character(action)
        if selected.ability in character.invalid_ability_scores:
            record = self._record(
                attempt_id,
                fingerprint,
                "needs_input",
                action_type,
                None,
                (),
                _without(signals, "roll_may_be_needed") + ["adjudication_needs_input"],
                warnings + [f"invalid_ability_score:{selected.ability}"],
            )
            return self._store(action.session_id, record)

        ability_score = character.ability_scores.get(selected.ability, 10)
        if selected.ability not in character.ability_scores:
            warnings.append(f"ability_defaulted_to_10:{selected.ability}")
        ability_modifier = (ability_score - 10) // 2

        proficiency_modifier = 0
        modifier_sources = [f"{selected.ability} {ability_score} -> {ability_modifier:+d}"]
        if selected.skill and selected.skill in character.skill_proficiencies:
            if character.level_invalid:
                record = self._record(
                    attempt_id,
                    fingerprint,
                    "needs_input",
                    action_type,
                    None,
                    (),
                    _without(signals, "roll_may_be_needed") + ["adjudication_needs_input"],
                    warnings + ["invalid_level_for_proficiency"],
                )
                return self._store(action.session_id, record)
            level = character.level or 1
            if character.level is None:
                warnings.append("proficiency_level_defaulted_to_1")
            proficiency_modifier = _proficiency_bonus(level)
            modifier_sources.append(f"{selected.skill} 熟练 (等级 {level}) -> +{proficiency_modifier}")

        scene = self._load_scene_facts(action, character, selected)
        if scene.circumstance_modifier:
            modifier_sources.append(
                f"情境 {scene.circumstance_reason or '结构化规则'} -> {scene.circumstance_modifier:+d}"
            )
        if scene.advantage_sources and scene.disadvantage_sources:
            roll_mode: RollMode = "normal"
        elif scene.advantage_sources:
            roll_mode = "advantage"
        elif scene.disadvantage_sources:
            roll_mode = "disadvantage"
        else:
            roll_mode = "normal"

        d20s = (self._roll(20), self._roll(20)) if roll_mode != "normal" else (self._roll(20),)
        selected_d20 = max(d20s) if roll_mode == "advantage" else min(d20s) if roll_mode == "disadvantage" else d20s[0]
        total = selected_d20 + ability_modifier + proficiency_modifier + scene.circumstance_modifier
        check = CheckResolution(
            test_kind="ability_check",
            ability=selected.ability,  # type: ignore[arg-type]
            skill=selected.skill,
            intent=selected.intent,
            dc=scene.dc,
            dc_reason=scene.dc_reason,
            roll_mode=roll_mode,
            d20s=d20s,
            selected_d20=selected_d20,
            natural_face="natural_1" if selected_d20 == 1 else "natural_20" if selected_d20 == 20 else None,
            ability_score=ability_score,
            ability_modifier=ability_modifier,
            proficiency_modifier=proficiency_modifier,
            circumstance_modifier=scene.circumstance_modifier,
            modifier_sources=tuple(modifier_sources),
            advantage_sources=scene.advantage_sources,
            disadvantage_sources=scene.disadvantage_sources,
            total=total,
            margin=total - scene.dc,
            outcome="success" if total >= scene.dc else "failure",
        )
        record = self._record(
            attempt_id,
            fingerprint,
            "resolved",
            action_type,
            check,
            (),
            _without(signals, "roll_may_be_needed") + ["ability_check_resolved"],
            warnings,
        )
        return self._store(action.session_id, record)

    def _validate_request(self, request: AdjudicationRequest) -> tuple[str, PlayerAction]:
        action = request.action
        request_attempt = (request.attempt_id or "").strip()
        action_attempt = (action.attempt_id or "").strip()
        if request_attempt and action_attempt and request_attempt != action_attempt:
            raise InvalidAdjudicationInput("request 与 PlayerAction 的 attempt_id 不一致")
        attempt_id = request_attempt or action_attempt
        if not attempt_id or len(attempt_id) > 128:
            raise InvalidAdjudicationInput("attempt_id 不能为空且不能超过 128 字符")
        if action.campaign_id <= 0 or action.session_id <= 0:
            raise InvalidAdjudicationInput("campaign_id 和 session_id 必须为正整数")
        if not (action.text or "").strip():
            raise InvalidAdjudicationInput("玩家行动不能为空")
        if self._conn is not None:
            from one_person_dnd.db.repos import sessions

            if not sessions.session_exists_under_campaign(
                self._conn,
                session_id=action.session_id,
                campaign_id=action.campaign_id,
            ):
                raise InvalidAdjudicationInput("session 不属于指定 campaign")
        return attempt_id, action

    def _load_character(self, action: PlayerAction) -> CharacterSummary:
        if self._character_loader is not None:
            return self._character_loader(action)
        if self._conn is None:
            return CharacterSummary()
        from one_person_dnd.db.repos import character_sheets

        return summarize_character_sheet(
            character_sheets.get_character_sheet(self._conn, session_id=action.session_id)
        )

    def _load_scene_facts(
        self,
        action: PlayerAction,
        character: CharacterSummary,
        selected: _SelectedCheck,
    ) -> _SceneFacts:
        advantage = _sources_for(character.check_advantages, selected)
        disadvantage = _sources_for(character.check_disadvantages, selected)
        if self._conn is None:
            return _SceneFacts(advantage_sources=advantage, disadvantage_sources=disadvantage)

        from one_person_dnd.db.repos import sessions

        row = sessions.get_session_sidebar(self._conn, action.session_id)
        raw_state = row["session_state"] if row and "session_state" in row.keys() else ""
        structured = _parse_structured_scene_facts(raw_state, selected)
        return _SceneFacts(
            dc=structured.dc,
            dc_reason=structured.dc_reason,
            circumstance_modifier=structured.circumstance_modifier,
            circumstance_reason=structured.circumstance_reason,
            advantage_sources=_dedupe_tuple(advantage + structured.advantage_sources),
            disadvantage_sources=_dedupe_tuple(disadvantage + structured.disadvantage_sources),
        )

    def _roll_manual_expressions(self, text: str) -> tuple[DiceEvent, ...]:
        events: list[DiceEvent] = []
        for match in _MANUAL_ROLL_RE.finditer(text or ""):
            try:
                count, sides, modifier = parse_roll_expr(match.group(1))
            except ValueError:
                continue
            rolls = [self._roll(sides) for _ in range(count)]
            normalized = f"{count}d{sides}" + (f"{modifier:+d}" if modifier else "")
            events.append(
                {
                    "expr": normalized,
                    "count": count,
                    "sides": sides,
                    "modifier": modifier,
                    "rolls": rolls,
                    "total": sum(rolls) + modifier,
                }
            )
            if len(events) >= 5:
                break
        return tuple(events)

    def _roll(self, sides: int) -> int:
        value = int(self._roller.roll(sides))
        if not 1 <= value <= sides:
            raise ValueError(f"roller returned {value}, expected 1..{sides}")
        return value

    @staticmethod
    def _record(
        attempt_id: str,
        fingerprint: str,
        status: AdjudicationStatus,
        action_type: str,
        check: CheckResolution | None,
        manual_rolls: tuple[DiceEvent, ...],
        signals: list[str],
        warnings: list[str],
    ) -> AdjudicationRecord:
        return AdjudicationRecord(
            attempt_id=attempt_id,
            policy_version=POLICY_VERSION,
            request_fingerprint=fingerprint,
            status=status,
            action_type=action_type,
            check=check,
            manual_rolls=manual_rolls,
            signals=_dedupe_tuple(tuple(signals)),
            warnings=_dedupe_tuple(tuple(warnings)),
        )

    def _get_existing(self, session_id: int, attempt_id: str) -> AdjudicationRecord | None:
        if self._conn is None:
            return self._memory_records.get((session_id, attempt_id))
        from one_person_dnd.db.repos import adjudication_records

        try:
            row = adjudication_records.get_by_attempt(
                self._conn,
                session_id=session_id,
                attempt_id=attempt_id,
            )
        except sqlite3.OperationalError as exc:
            if _is_sqlite_busy_error(exc):
                raise AdjudicationStoreBusy("裁决记录暂时无法从 SQLite 读取") from exc
            raise
        if not row:
            return None
        try:
            raw = row["record_json"] if isinstance(row, Mapping) else row["record_json"]
            record = AdjudicationRecord.from_json(str(raw))
            row_fingerprint = str(row["fingerprint"])
            if record.attempt_id != attempt_id or record.request_fingerprint != row_fingerprint:
                raise ValueError("ledger identity does not match serialized record")
        except Exception as exc:
            raise AdjudicationStoreCorrupt("已保存的裁决记录无法校验") from exc
        return record

    def _store(self, session_id: int, record: AdjudicationRecord) -> AdjudicationRecord:
        key = (session_id, record.attempt_id)
        if self._conn is not None:
            from one_person_dnd.db.repos import adjudication_records

            try:
                adjudication_records.create(
                    self._conn,
                    session_id=session_id,
                    attempt_id=record.attempt_id,
                    fingerprint=record.request_fingerprint,
                    record_json=record.to_json(),
                )
            except sqlite3.IntegrityError:
                winner = self._get_existing(session_id, record.attempt_id)
                if winner is None:
                    raise
                if winner.request_fingerprint != record.request_fingerprint:
                    raise AttemptConflict("同一 attempt_id 已被另一条行动占用")
                return winner
            except sqlite3.OperationalError as exc:
                if _is_sqlite_busy_error(exc):
                    raise AdjudicationStoreBusy("裁决记录暂时无法写入 SQLite") from exc
                raise
        if self._conn is None:
            self._memory_records[key] = record
        return record


def _request_fingerprint(action: PlayerAction) -> str:
    payload = {
        "campaign_id": action.campaign_id,
        "session_id": action.session_id,
        "text": (action.text or "").strip(),
        "manual_tags": sorted({item.strip() for item in action.manual_tags if item.strip()}),
        "extra_context": (action.extra_context or "").strip(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _select_check(text: str) -> _SelectedCheck | None:
    lowered = (text or "").casefold()
    for markers, ability, skill, intent in _CHECK_RULES:
        if any(marker.casefold() in lowered for marker in markers):
            return _SelectedCheck(ability=ability, skill=skill, intent=intent)
    return None


def _proficiency_bonus(level: int) -> int:
    if not 1 <= level <= 20:
        raise ValueError("level must be in 1..20")
    return 2 + (level - 1) // 4


def _sources_for(source_map: Mapping[str, list[str]], selected: _SelectedCheck) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("*", selected.ability, selected.skill):
        if key:
            values.extend(source_map.get(key, []))
    return _dedupe_tuple(tuple(values))


def _parse_structured_scene_facts(raw: Any, selected: _SelectedCheck) -> _SceneFacts:
    try:
        loaded = json.loads(raw) if isinstance(raw, str) and raw.strip() else raw
    except (TypeError, ValueError):
        return _SceneFacts()
    if not isinstance(loaded, dict):
        return _SceneFacts()
    block = loaded.get("adjudication")
    if not isinstance(block, dict):
        return _SceneFacts()

    reason = str(block.get("dc_reason") or "").strip()
    difficulty = str(block.get("difficulty") or "").strip().casefold()
    dc = 15
    dc_reason = "缺少可信结构化难度事实，使用标准 DC 15。"
    if reason and difficulty in {"easy", "standard", "hard"}:
        dc = {"easy": 10, "standard": 15, "hard": 20}[difficulty]
        dc_reason = reason
    elif reason and isinstance(block.get("dc"), int) and block["dc"] in {5, 10, 15, 20, 25, 30}:
        dc = int(block["dc"])
        dc_reason = reason

    circumstance = block.get("circumstance_modifier")
    circumstance_reason = str(block.get("circumstance_reason") or "").strip()
    circumstance_modifier = (
        int(circumstance)
        if isinstance(circumstance, int)
        and not isinstance(circumstance, bool)
        and -10 <= circumstance <= 10
        and circumstance_reason
        else 0
    )

    advantage = _structured_sources(block.get("advantage_sources"), selected)
    disadvantage = _structured_sources(block.get("disadvantage_sources"), selected)
    return _SceneFacts(
        dc=dc,
        dc_reason=dc_reason,
        circumstance_modifier=circumstance_modifier,
        circumstance_reason=circumstance_reason if circumstance_modifier else "",
        advantage_sources=advantage,
        disadvantage_sources=disadvantage,
    )


def _structured_sources(value: Any, selected: _SelectedCheck) -> tuple[str, ...]:
    if isinstance(value, list):
        return _dedupe_tuple(tuple(str(item).strip() for item in value if str(item).strip()))
    if not isinstance(value, dict):
        return ()
    values: list[str] = []
    for key in ("*", selected.ability, selected.skill):
        if not key:
            continue
        raw = value.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item).strip())
    return _dedupe_tuple(tuple(values))


def _dedupe_tuple(items: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _without(items: list[str], value: str) -> list[str]:
    return [item for item in items if item != value]

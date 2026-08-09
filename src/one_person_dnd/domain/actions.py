from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from one_person_dnd.engine.dice import DiceEvent

if TYPE_CHECKING:
    from one_person_dnd.adjudication import AdjudicationRecord


_ZH_DIRECT_COMBAT_VERB = (
    r"(?:攻击(?!者|性)|挥砍|射击|刺向|砍向|劈向|斩向|捅向|砸向|射向)"
)
_ZH_WEAPON_COMBAT_VERB = (
    r"(?:攻击(?!者|性)|挥砍|射击|刺(?:向)?|砍(?:向)?|劈(?:向)?|"
    r"斩(?:向)?|捅(?:向)?|砸(?:向)?|射(?:向)?)"
)
_ZH_WEAPON = (
    r"(?:短剑|长剑|匕首|战斧|巨斧|手斧|斧头|战锤|巨锤|短弓|长弓|十字弩|"
    r"长枪|法杖|剑|刀|斧|锤|弓|弩|枪|矛|棍|杖|武器|拳头|拳|脚)"
)
_EN_COMBAT_VERB = (
    r"(?:attack|stab|slash|"
    r"shoot(?!\s+(?:(?:a|the|another)\s+)?(?:question|photo|picture|video|message|breeze)\b)|"
    r"strike(?!\s+(?:(?:a|the)\s+)?deal\b)|"
    r"swing(?!\s+by\b))"
)

_ACTIVE_COMBAT_PATTERNS = (
    re.compile(
        rf"(?:^|[，。！？；]\s*)我(?:要|想|尝试|试图|准备|立即|直接|先|开始|决定)?"
        rf"{_ZH_DIRECT_COMBAT_VERB}"
    ),
    re.compile(
        rf"(?:^|[，。！？；]\s*)我(?:要|想|尝试|试图|准备)?"
        rf"(?:用|拿|举|挥|抽出?|拔出?)(?:我的|手中的?|一把|那把|这把)?"
        rf"[^，。！？；]{{0,4}}?{_ZH_WEAPON}"
        rf"(?:朝|向|对准|猛地|狠狠地|猛烈地|立刻|直接)?{_ZH_WEAPON_COMBAT_VERB}"
    ),
    re.compile(
        rf"(?:然后|随后|接着|之后|后|再|并且|并)\s*"
        rf"(?:立即|直接|开始)?{_ZH_DIRECT_COMBAT_VERB}"
    ),
    re.compile(rf"^\s*{_ZH_DIRECT_COMBAT_VERB}"),
    re.compile(
        r"(?:^|[，。！？；]\s*)我(?:要|想|尝试|试图|准备)?"
        r"(?:发起战斗|开始战斗|加入战斗|进入战斗|施法攻击)"
    ),
    re.compile(r"(?:^|[，。！？；]\s*)我(?:要|想|尝试|试图|准备|立即|开始)?施法(?:[，。！？；]|$)"),
    re.compile(
        rf"(?:^|[.!?;]\s*)i\s+"
        rf"(?:(?:try|attempt|want|plan|prepare|decide|will|would\s+like|am\s+going)\s+(?:to\s+)?)?"
        rf"{_EN_COMBAT_VERB}\b",
        re.IGNORECASE,
    ),
    re.compile(rf"^\s*{_EN_COMBAT_VERB}\b", re.IGNORECASE),
    re.compile(rf"\b(?:and\s+then|then|and)\s+{_EN_COMBAT_VERB}\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class PlayerAction:
    campaign_id: int
    session_id: int
    text: str
    manual_tags: list[str] = field(default_factory=list)
    extra_context: str = ""
    attempt_id: str = ""


@dataclass(frozen=True)
class ActionAssessment:
    action_type: str
    dice_events: list[DiceEvent]
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adjudication: AdjudicationRecord | None = None


def classify_action_text(text: str) -> str:
    """Return the legacy broad action category without performing any roll."""
    cleaned = (text or "").strip()
    lowered = cleaned.lower()
    if any(pattern.search(cleaned) for pattern in _ACTIVE_COMBAT_PATTERNS):
        return "combat"
    if any(k in cleaned for k in ("说服", "交涉", "欺骗", "威胁", "询问", "谈判")):
        return "social"
    if any(k in cleaned for k in ("休息", "睡觉", "扎营", "疗伤")):
        return "rest"
    if any(k in cleaned for k in ("背包", "购买", "出售", "装备", "使用物品")):
        return "inventory"
    if lowered.startswith("/") or any(k in cleaned for k in ("系统", "debug", "忽略规则")):
        return "meta"
    return "exploration"


def action_language_flags(
    text: str,
    *,
    action_type: str,
    has_manual_roll: bool = False,
) -> tuple[list[str], list[str]]:
    """Share non-mechanical intent warnings between legacy and canonical paths."""
    cleaned = (text or "").strip()
    signals: list[str] = []
    warnings: list[str] = []

    if has_manual_roll:
        signals.append("explicit_roll")
    if action_type in ("inventory", "rest"):
        signals.append("state_change_likely")
    if action_type == "rest":
        signals.append("time_passes")
    if not has_manual_roll and action_type in ("social", "combat", "exploration"):
        signals.append("roll_may_be_needed")

    if any(k in cleaned for k in ("我宣布", "直接杀死", "立刻死亡", "世界规则改为", "所有人都")):
        warnings.append("possible_overreach")
        signals.append("dm_should_adjudicate_outcome")
    if _declares_success(cleaned):
        warnings.append("declared_success")
        signals.append("dm_should_adjudicate_outcome")
    if _claims_npc_outcome(cleaned):
        warnings.append("npc_outcome_claim")
        signals.append("dm_should_adjudicate_outcome")

    return _dedupe(signals), _dedupe(warnings)


def _declares_success(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "我成功",
            "成功说服",
            "成功欺骗",
            "成功潜行",
            "成功开锁",
            "顺利说服",
            "顺利潜入",
        )
    )


def _claims_npc_outcome(text: str) -> bool:
    if any(marker in text for marker in ("让他", "让她", "让他们", "迫使", "命令")):
        return any(marker in text for marker in ("承认", "交出", "告诉", "放我", "加入", "背叛", "离开"))
    return any(marker in text for marker in ("守卫交出", "老板交出", "敌人投降", "国王同意"))


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))

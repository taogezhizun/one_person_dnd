from __future__ import annotations

from one_person_dnd.domain.actions import ActionAssessment, PlayerAction
from one_person_dnd.engine.dice import roll_events_from_text


class ActionJudgeAgent:
    def run(self, action: PlayerAction) -> ActionAssessment:
        text = (action.text or "").strip()
        lowered = text.lower()
        dice_events = roll_events_from_text(text, max_rolls=5)
        signals: list[str] = []
        warnings: list[str] = []

        if dice_events:
            signals.append("explicit_roll")

        action_type = "exploration"
        if any(k in text for k in ("说服", "交涉", "欺骗", "威胁", "询问", "谈判")):
            action_type = "social"
        elif any(k in text for k in ("攻击", "战斗", "施法", "射击", "挥砍")):
            action_type = "combat"
        elif any(k in text for k in ("休息", "睡觉", "扎营", "疗伤")):
            action_type = "rest"
        elif any(k in text for k in ("背包", "购买", "出售", "装备", "使用物品")):
            action_type = "inventory"
        elif lowered.startswith("/") or any(k in text for k in ("系统", "debug", "忽略规则")):
            action_type = "meta"

        if action_type in ("inventory", "rest"):
            signals.append("state_change_likely")
        if action_type == "rest":
            signals.append("time_passes")

        if not dice_events and action_type in ("social", "combat", "exploration"):
            signals.append("roll_may_be_needed")

        if any(k in text for k in ("我宣布", "直接杀死", "立刻死亡", "世界规则改为", "所有人都")):
            warnings.append("possible_overreach")
            signals.append("dm_should_adjudicate_outcome")

        if _declares_success(text):
            warnings.append("declared_success")
            signals.append("dm_should_adjudicate_outcome")

        if _claims_npc_outcome(text):
            warnings.append("npc_outcome_claim")
            signals.append("dm_should_adjudicate_outcome")

        return ActionAssessment(
            action_type=action_type,
            dice_events=dice_events,
            signals=_dedupe(signals),
            warnings=_dedupe(warnings),
        )


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
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out

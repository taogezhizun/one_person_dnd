from __future__ import annotations

import re

from one_person_dnd.agents.base import AgentResult
from one_person_dnd.engine import protocol
from one_person_dnd.engine.parser import DMStructuredResponse


class ResponseEvaluatorAgent:
    REPAIRABLE_WARNINGS = frozenset(
        {
            "duplicate_choices",
            "non_actionable_choice",
            "choice_declares_outcome",
        }
    )

    def run(self, dm: DMStructuredResponse) -> AgentResult:
        choices = [c.strip() for c in list(dm.choices or []) if (c or "").strip()]
        warnings: list[str] = []
        duplicate_count = _duplicate_choice_count(choices)
        generic = [c for c in choices if _is_non_actionable_choice(c)]
        outcome = [c for c in choices if _declares_outcome(c)]

        if duplicate_count:
            warnings.append("duplicate_choices")
        if generic:
            warnings.append("non_actionable_choice")
        if outcome:
            warnings.append("choice_declares_outcome")

        return AgentResult(
            agent_name="response_evaluator",
            status="ok" if not warnings else "warn",
            output={
                "choice_count": len(choices),
                "duplicate_choice_count": duplicate_count,
                "non_actionable_choices": generic,
                "outcome_choices": outcome,
            },
            warnings=warnings,
        )

    def should_repair(self, warnings: list[str]) -> bool:
        return any(w in self.REPAIRABLE_WARNINGS for w in warnings)

    def build_repair_prompt(self, dm_raw: str, warnings: list[str]) -> str:
        warning_text = ", ".join([w for w in warnings if w]) or "response_playability_issue"
        return (
            "你刚才的 DM 回复通过了初步生成，但下一步反应评估发现问题："
            f"{warning_text}。\n"
            "请在不改变既有事实、地点、NPC 反应和玩家处境的前提下，重写为完整、可继续游玩的 DM 回复。\n"
            "必须严格输出这些分隔符段落，分隔符单独占一行：\n"
            f"{protocol.NARRATION}\n"
            f"{protocol.CHOICES}\n"
            f"{protocol.DM_NOTES}\n"
            f"{protocol.MEMORY}\n"
            "CHOICES 必须给出 3-6 条以 - 开头的玩家可执行的行动；"
            "选项必须具体、互不重复，并且不能替玩家宣布成功、失败、击杀、获得物品或 NPC 已经服从。\n"
            "如果需要 STATE_DELTA 或 THREAD_UPDATES，只能追加有效 JSON；不确定时留空或省略可选段。\n"
            "禁止输出分隔符之外的说明。\n\n"
            "【待修复输出】\n"
            f"{(dm_raw or '').strip()}\n"
        )


def _normalize_choice(choice: str) -> str:
    return re.sub(r"[\s，。！？、,.!?;；：:（）()【】\\[\\]\"'“”‘’]+", "", (choice or "").lower())


def _duplicate_choice_count(choices: list[str]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for choice in choices:
        normalized = _normalize_choice(choice)
        if not normalized:
            continue
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)
    return duplicates


def _is_non_actionable_choice(choice: str) -> bool:
    normalized = _normalize_choice(choice)
    if normalized in {"继续", "等待", "无", "随便", "继续前进", "继续行动", "看看", "观察"}:
        return True
    return len(normalized) <= 2


def _declares_outcome(choice: str) -> bool:
    text = (choice or "").strip()
    if any(marker in text for marker in ("成功", "已经", "立刻", "直接杀死", "获得", "得到")):
        return True
    if text.startswith(("让", "迫使", "命令")) and any(
        marker in text for marker in ("交出", "放你", "放我", "同意", "加入", "离开", "投降")
    ):
        return True
    return False

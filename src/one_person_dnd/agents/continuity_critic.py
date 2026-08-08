from __future__ import annotations

from one_person_dnd.agents.base import AgentResult
from one_person_dnd.domain.actions import ActionAssessment
from one_person_dnd.domain.thread_updates import validate_thread_updates_json
from one_person_dnd.engine import protocol
from one_person_dnd.engine.guardrails import GuardrailError, validate_state_delta_json
from one_person_dnd.engine.orchestrator import _has_required_protocol_delims
from one_person_dnd.engine.parser import parse_dm_text


class ContinuityCriticAgent:
    REPAIRABLE_WARNINGS = frozenset(
        {
            "empty_dm_response",
            "missing_required_protocol_delimiters",
            "empty_narration",
            "choice_count_out_of_range",
            "adjudication_outcome_conflict",
            "unresolved_check_declared",
        }
    )

    def run(self, dm_raw: str, action_assessment: ActionAssessment | None = None) -> AgentResult:
        warnings: list[str] = []
        output: dict[str, object] = {}
        if not (dm_raw or "").strip():
            warnings.append("empty_dm_response")
        if not _has_required_protocol_delims(dm_raw):
            warnings.append("missing_required_protocol_delimiters")

        dm = parse_dm_text(dm_raw)
        if not (dm.narration or "").strip():
            warnings.append("empty_narration")

        choice_count = len(dm.choices)
        output["choice_count"] = choice_count
        if choice_count < 2 or choice_count > 6:
            warnings.append("choice_count_out_of_range")

        if (dm.state_delta_json or "").strip():
            try:
                validate_state_delta_json(dm.state_delta_json)
            except GuardrailError as exc:
                warnings.append("malformed_state_delta")
                output["state_delta_error"] = str(exc)

        if (dm.thread_updates_json or "").strip():
            try:
                validate_thread_updates_json(dm.thread_updates_json)
            except GuardrailError as exc:
                warnings.append("malformed_thread_updates")
                output["thread_updates_error"] = str(exc)

        adjudication = action_assessment.adjudication if action_assessment else None
        explicit_outcome = _explicit_adjudication_outcome(dm.narration)
        if adjudication is not None:
            output["adjudication_status"] = adjudication.status
            if adjudication.check is not None:
                output["expected_outcome"] = adjudication.check.outcome
                if explicit_outcome and explicit_outcome != adjudication.check.outcome:
                    warnings.append("adjudication_outcome_conflict")
            elif adjudication.status == "needs_input" and explicit_outcome:
                warnings.append("unresolved_check_declared")

        return AgentResult(
            agent_name="continuity_critic",
            status="ok" if not warnings else "warn",
            output=output,
            warnings=warnings,
        )

    def should_repair(self, warnings: list[str]) -> bool:
        return any(w in self.REPAIRABLE_WARNINGS for w in warnings)

    def build_repair_prompt(
        self,
        dm_raw: str,
        warnings: list[str],
        action_assessment: ActionAssessment | None = None,
    ) -> str:
        relevant = [w for w in warnings if w in self.REPAIRABLE_WARNINGS]
        warning_text = ", ".join(relevant) or "unknown_playability_issue"
        adjudication_instruction = _adjudication_repair_instruction(action_assessment)
        return (
            "你刚才的 DM 回复通过了初步生成，但可玩性审查发现问题："
            f"{warning_text}。\n"
            "请在不改变既有事实、地点、NPC 反应和玩家处境的前提下，重写为完整、可继续游玩的 DM 回复。\n"
            "必须严格输出这些分隔符段落，分隔符单独占一行：\n"
            f"{protocol.NARRATION}\n"
            f"{protocol.CHOICES}\n"
            f"{protocol.DM_NOTES}\n"
            f"{protocol.MEMORY}\n"
            "要求：NARRATION 不能为空；CHOICES 必须给出 3-6 条以 - 开头的可选行动；"
            "DM_NOTES 和 MEMORY 可简短但不能省略。"
            f"{adjudication_instruction}"
            "如果需要 STATE_DELTA 或 THREAD_UPDATES，只能追加有效 JSON；不确定时留空或省略可选段。\n"
            "禁止输出分隔符之外的说明。\n\n"
            "【待修复输出】\n"
            f"{(dm_raw or '').strip()}\n"
        )


def _explicit_adjudication_outcome(narration: str) -> str | None:
    text = (narration or "").casefold()
    failure_markers = ("检定失败", "判定失败", "行动失败", "check failed", "check failure")
    success_markers = ("检定成功", "判定成功", "行动成功", "check succeeded", "check success")
    has_failure = any(marker in text for marker in failure_markers)
    has_success = any(marker in text for marker in success_markers)
    if has_failure == has_success:
        return None
    return "failure" if has_failure else "success"


def _adjudication_repair_instruction(action_assessment: ActionAssessment | None) -> str:
    adjudication = action_assessment.adjudication if action_assessment else None
    if adjudication is None:
        return ""
    if adjudication.check is not None:
        check = adjudication.check
        outcome = "成功" if check.outcome == "success" else "失败"
        return (
            f"系统规则结算已冻结为：{check.ability}"
            f"{' / ' + check.skill if check.skill else ''}，DC {check.dc}，总值 {check.total}，结果{outcome}。"
            "必须按此结果重写，不得重掷或改动数值。\n"
        )
    if adjudication.status == "needs_input":
        return "系统尚缺少完成检定所需的角色数据；不得宣布检定成功或失败。\n"
    return ""

from __future__ import annotations

from one_person_dnd.agents.base import AgentResult
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
        }
    )

    def run(self, dm_raw: str) -> AgentResult:
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

        return AgentResult(
            agent_name="continuity_critic",
            status="ok" if not warnings else "warn",
            output=output,
            warnings=warnings,
        )

    def should_repair(self, warnings: list[str]) -> bool:
        return any(w in self.REPAIRABLE_WARNINGS for w in warnings)

    def build_repair_prompt(self, dm_raw: str, warnings: list[str]) -> str:
        relevant = [w for w in warnings if w in self.REPAIRABLE_WARNINGS]
        warning_text = ", ".join(relevant) or "unknown_playability_issue"
        return (
            "你刚才的 DM 回复通过了初步生成，但可玩性审查发现问题："
            f"{warning_text}。\n"
            "请在不改变既有事实、地点、NPC 反应和玩家处境的前提下，重写为完整、可继续游玩的 DM 回复。\n"
            "必须严格输出这些分隔符段落，分隔符单独占一行：\n"
            "===NARRATION===\n"
            "===CHOICES===\n"
            "===DM_NOTES===\n"
            "===MEMORY===\n"
            "要求：NARRATION 不能为空；CHOICES 必须给出 3-6 条以 - 开头的可选行动；"
            "DM_NOTES 和 MEMORY 可简短但不能省略。"
            "如果需要 STATE_DELTA 或 THREAD_UPDATES，只能追加有效 JSON；不确定时留空或省略可选段。\n"
            "禁止输出分隔符之外的说明。\n\n"
            "【待修复输出】\n"
            f"{(dm_raw or '').strip()}\n"
        )

import unittest

from one_person_dnd.agents.response_evaluator import ResponseEvaluatorAgent
from one_person_dnd.engine.parser import parse_dm_text


def _dm_with_choices(choices: list[str]):
    return parse_dm_text(
        "\n".join(
            [
                "===NARRATION===",
                "守卫握紧钥匙，等待你的下一步。",
                "===CHOICES===",
                *[f"- {choice}" for choice in choices],
                "===DM_NOTES===",
                "evaluate choices",
                "===MEMORY===",
                "玩家正在和守卫交涉。",
            ]
        )
    )


class TestResponseEvaluatorAgent(unittest.TestCase):
    def test_accepts_distinct_player_action_choices(self) -> None:
        result = ResponseEvaluatorAgent().run(
            _dm_with_choices(
                [
                    "询问守卫钥匙的来历",
                    "观察守卫腰间是否有备用钥匙",
                    "退到门厅寻找其他入口",
                ]
            )
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.warnings, [])

    def test_warns_when_choices_are_duplicate_or_too_generic(self) -> None:
        result = ResponseEvaluatorAgent().run(
            _dm_with_choices(
                [
                    "继续",
                    "继续",
                    "等待",
                ]
            )
        )

        self.assertEqual(result.status, "warn")
        self.assertIn("duplicate_choices", result.warnings)
        self.assertIn("non_actionable_choice", result.warnings)
        self.assertEqual(result.output["duplicate_choice_count"], 1)

    def test_warns_when_choice_declares_successful_outcome(self) -> None:
        result = ResponseEvaluatorAgent().run(
            _dm_with_choices(
                [
                    "成功说服守卫交出钥匙",
                    "让守卫立刻放你通过",
                    "调查门锁结构",
                ]
            )
        )

        self.assertIn("choice_declares_outcome", result.warnings)
        self.assertTrue(result.output["outcome_choices"])

    def test_builds_repair_prompt_for_response_warnings(self) -> None:
        raw = "===NARRATION===\n门厅很暗。\n===CHOICES===\n- 继续\n- 继续\n===DM_NOTES===\nok\n===MEMORY===\n门厅。"
        prompt = ResponseEvaluatorAgent().build_repair_prompt(raw, ["duplicate_choices", "non_actionable_choice"])

        self.assertIn("duplicate_choices", prompt)
        self.assertIn("non_actionable_choice", prompt)
        self.assertIn("3-6 条", prompt)
        self.assertIn("玩家可执行的行动", prompt)

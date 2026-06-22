import unittest

from one_person_dnd.agents.continuity_critic import ContinuityCriticAgent


class TestContinuityCriticAgent(unittest.TestCase):
    def test_warns_when_state_delta_is_malformed(self) -> None:
        raw = "\n".join(
            [
                "===NARRATION===",
                "门厅里传来脚步声。",
                "===CHOICES===",
                "- 躲起来",
                "- 迎上去",
                "===DM_NOTES===",
                "ok",
                "===MEMORY===",
                "门厅有人靠近。",
                "===STATE_DELTA===",
                '{"party":[{"hp":7}',
            ]
        )

        result = ContinuityCriticAgent().run(raw)

        self.assertEqual(result.status, "warn")
        self.assertIn("malformed_state_delta", result.warnings)
        self.assertIn("state_delta_error", result.output)

    def test_warns_when_choice_count_is_outside_playable_range(self) -> None:
        raw = "\n".join(
            [
                "===NARRATION===",
                "你站在门前。",
                "===CHOICES===",
                "- 等待",
                "===DM_NOTES===",
                "ok",
                "===MEMORY===",
                "玩家停在门前。",
            ]
        )

        result = ContinuityCriticAgent().run(raw)

        self.assertEqual(result.status, "warn")
        self.assertIn("choice_count_out_of_range", result.warnings)
        self.assertEqual(result.output["choice_count"], 1)

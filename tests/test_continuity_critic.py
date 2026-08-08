import unittest

from one_person_dnd.adjudication import ActionAdjudicator, AdjudicationRequest, SequenceRoller
from one_person_dnd.agents.continuity_critic import ContinuityCriticAgent
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.domain.characters import CharacterSummary


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

    def test_warns_when_thread_updates_are_malformed(self) -> None:
        raw = "\n".join(
            [
                "===NARRATION===",
                "守卫记下了你的名字。",
                "===CHOICES===",
                "- 追问原因",
                "- 离开门厅",
                "===DM_NOTES===",
                "ok",
                "===MEMORY===",
                "守卫记住了玩家。",
                "===THREAD_UPDATES===",
                '{"updates":[{"id":1,"status":"unknown"}]}',
            ]
        )

        result = ContinuityCriticAgent().run(raw)

        self.assertIn("malformed_thread_updates", result.warnings)
        self.assertIn("thread_updates_error", result.output)

    def test_warns_and_repairs_when_dm_contradicts_frozen_check(self) -> None:
        action = PlayerAction(campaign_id=1, session_id=2, text="我尝试开锁", attempt_id="critic-check")
        record = ActionAdjudicator(
            roller=SequenceRoller([18]),
            character_loader=lambda _: CharacterSummary(ability_scores={"DEX": 10}),
        ).adjudicate(AdjudicationRequest(attempt_id=action.attempt_id, action=action))
        assessment = record.to_action_assessment()
        raw = "\n".join(
            [
                "===NARRATION===",
                "这次检定失败，锁纹丝不动。",
                "===CHOICES===",
                "- 检查锁芯",
                "- 寻找钥匙",
                "===DM_NOTES===",
                "conflict",
                "===MEMORY===",
                "玩家尝试开锁。",
            ]
        )

        critic = ContinuityCriticAgent()
        result = critic.run(raw, assessment)
        repair_prompt = critic.build_repair_prompt(raw, result.warnings, assessment)

        self.assertEqual(record.check.outcome, "success")
        self.assertIn("adjudication_outcome_conflict", result.warnings)
        self.assertTrue(critic.should_repair(result.warnings))
        self.assertIn("总值 18，结果成功", repair_prompt)
        self.assertIn("不得重掷", repair_prompt)

    def test_needs_input_cannot_be_narrated_as_resolved(self) -> None:
        action = PlayerAction(campaign_id=1, session_id=2, text="我尝试开锁", attempt_id="missing-score")
        record = ActionAdjudicator(
            roller=SequenceRoller([]),
            character_loader=lambda _: CharacterSummary(invalid_ability_scores=["DEX"]),
        ).adjudicate(AdjudicationRequest(attempt_id=action.attempt_id, action=action))
        raw = "\n".join(
            [
                "===NARRATION===",
                "你的检定成功，锁打开了。",
                "===CHOICES===",
                "- 进入房间",
                "- 检查门框",
                "===DM_NOTES===",
                "premature",
                "===MEMORY===",
                "玩家开门。",
            ]
        )

        result = ContinuityCriticAgent().run(raw, record.to_action_assessment())

        self.assertEqual(record.status, "needs_input")
        self.assertIn("unresolved_check_declared", result.warnings)

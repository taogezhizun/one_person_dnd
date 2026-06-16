import unittest

from one_person_dnd.agents.action_judge import ActionJudgeAgent
from one_person_dnd.domain.actions import PlayerAction


class TestActionJudgeAgent(unittest.TestCase):
    def test_detects_explicit_dice(self) -> None:
        action = PlayerAction(
            campaign_id=1,
            session_id=2,
            text="我观察门锁并掷 1d20+3",
            manual_tags=[],
            extra_context="",
        )
        result = ActionJudgeAgent().run(action)
        self.assertEqual(result.action_type, "exploration")
        self.assertEqual(len(result.dice_events), 1)
        self.assertIn("explicit_roll", result.signals)

    def test_flags_player_overreach(self) -> None:
        action = PlayerAction(
            campaign_id=1,
            session_id=2,
            text="我宣布国王立刻死亡并把王国送给我",
            manual_tags=[],
            extra_context="",
        )
        result = ActionJudgeAgent().run(action)
        self.assertIn("possible_overreach", result.warnings)

    def test_classifies_social_action(self) -> None:
        action = PlayerAction(
            campaign_id=1,
            session_id=2,
            text="我试图说服守卫放我进去",
            manual_tags=[],
            extra_context="",
        )
        result = ActionJudgeAgent().run(action)
        self.assertEqual(result.action_type, "social")
        self.assertIn("roll_may_be_needed", result.signals)

    def test_flags_declared_success_and_npc_outcome_claims(self) -> None:
        action = PlayerAction(
            campaign_id=1,
            session_id=2,
            text="我成功说服守卫交出钥匙，并让他承认自己一直在撒谎",
            manual_tags=[],
            extra_context="",
        )

        result = ActionJudgeAgent().run(action)

        self.assertEqual(result.action_type, "social")
        self.assertIn("dm_should_adjudicate_outcome", result.signals)
        self.assertIn("declared_success", result.warnings)
        self.assertIn("npc_outcome_claim", result.warnings)

    def test_inventory_and_rest_actions_expect_state_changes(self) -> None:
        inventory = ActionJudgeAgent().run(
            PlayerAction(
                campaign_id=1,
                session_id=2,
                text="我购买一瓶治疗药水并支付 50 金币",
                manual_tags=[],
                extra_context="",
            )
        )
        rest = ActionJudgeAgent().run(
            PlayerAction(
                campaign_id=1,
                session_id=2,
                text="我短休疗伤，整理装备",
                manual_tags=[],
                extra_context="",
            )
        )

        self.assertEqual(inventory.action_type, "inventory")
        self.assertIn("state_change_likely", inventory.signals)
        self.assertEqual(rest.action_type, "rest")
        self.assertIn("state_change_likely", rest.signals)
        self.assertIn("time_passes", rest.signals)

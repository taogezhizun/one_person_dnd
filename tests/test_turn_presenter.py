import unittest

from one_person_dnd.adjudication import ActionAdjudicator, AdjudicationRequest, SequenceRoller
from one_person_dnd.domain.actions import ActionAssessment
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.domain.characters import CharacterSummary
from one_person_dnd.engine.orchestrator import TurnResult
from one_person_dnd.engine.parser import DMStructuredResponse
from one_person_dnd.web.turn_presenter import TurnPresenter


class TestTurnPresenter(unittest.TestCase):
    def test_completed_turn_has_one_canonical_shape_for_html_and_sse(self) -> None:
        result = TurnResult(
            turn_index=7,
            dm_raw_text="raw",
            dm=DMStructuredResponse(
                narration="门后传来脚步声。",
                choices=["贴门倾听", "退到阴影里", "直接敲门"],
                dm_notes="保持悬念",
                memory_suggestions="门后有人",
                state_delta_json='{"hp": 9}',
                thread_updates_json='{"updates": []}',
            ),
            recalled_world=[{"title": "旧塔"}],
            recalled_context=[{"kind": "world", "title": "旧塔"}],
            dice_events=[
                {
                    "expr": "1d20+2",
                    "count": 1,
                    "sides": 20,
                    "modifier": 2,
                    "rolls": [13],
                    "total": 15,
                }
            ],
            action_assessment=ActionAssessment(
                action_type="exploration",
                dice_events=[],
                signals=["roll_may_be_needed"],
                warnings=["declared_success"],
            ),
            critic_warnings=["choice_count_out_of_range"],
            response_warnings=["duplicate_choices"],
        )

        turn = TurnPresenter().present_result(result, player_text="我检查门缝")

        self.assertEqual(turn["turn_index"], 7)
        self.assertEqual(turn["player_text"], "我检查门缝")
        self.assertEqual(turn["dm"]["narration"], "门后传来脚步声。")
        self.assertEqual(turn["dm"]["choices"], ["贴门倾听", "退到阴影里", "直接敲门"])
        self.assertEqual(turn["action_assessment"]["action_type"], "exploration")
        self.assertEqual(turn["action_assessment"]["signals"], ["roll_may_be_needed"])
        self.assertEqual(turn["critic_warnings"], ["choice_count_out_of_range"])
        self.assertEqual(turn["response_warnings"], ["duplicate_choices"])
        self.assertEqual(turn["pending_review_delta"], 2)
        self.assertTrue(turn["has_pending_review"])

    def test_history_rows_are_presented_oldest_first_and_bad_dice_degrades_safely(self) -> None:
        rows = [
            {
                "turn_index": 2,
                "player_text": "我继续前进",
                "dm_text": (
                    "===NARRATION===\n走廊更暗了。\n"
                    "===CHOICES===\n- 点亮火把\n- 原路返回\n- 摸索前进\n"
                    "===DM_NOTES===\n\n===MEMORY===\n"
                ),
                "dice_events": "not-json",
                "created_at": "later",
            },
            {
                "turn_index": 1,
                "player_text": "我观察走廊",
                "dm_text": (
                    "===NARRATION===\n墙上有新鲜抓痕。\n"
                    "===CHOICES===\n- 检查抓痕\n- 查看地面\n- 退回门口\n"
                    "===DM_NOTES===\n\n===MEMORY===\n"
                ),
                "dice_events": (
                    '[{"expr":"1d20","count":1,"sides":20,"modifier":0,'
                    '"rolls":[11],"total":11}]'
                ),
                "created_at": "earlier",
            },
        ]

        turns = TurnPresenter().present_history(
            rows,
            campaign_id=3,
            session_id=4,
        )

        self.assertEqual([turn["turn_index"] for turn in turns], [1, 2])
        self.assertEqual(turns[0]["dm"]["narration"], "墙上有新鲜抓痕。")
        self.assertEqual(turns[0]["dice_events"][0]["total"], 11)
        self.assertEqual(turns[1]["dice_events"], [])
        self.assertFalse(turns[0]["has_pending_review"])
        self.assertEqual(turns[0]["pending_review_delta"], 0)

    def test_history_uses_frozen_adjudication_record(self) -> None:
        action = PlayerAction(campaign_id=3, session_id=4, text="我尝试开锁", attempt_id="history-check")
        roller = SequenceRoller([14])
        record = ActionAdjudicator(
            roller=roller,
            character_loader=lambda _: CharacterSummary(ability_scores={"DEX": 14}),
        ).adjudicate(AdjudicationRequest(attempt_id=action.attempt_id, action=action))
        rows = [
            {
                "turn_index": 0,
                "player_text": action.text,
                "dm_text": (
                    "===NARRATION===\n锁舌弹开。\n"
                    "===CHOICES===\n- 进入房间\n- 检查门框\n"
                    "===DM_NOTES===\n\n===MEMORY===\n"
                ),
                "dice_events": "[]",
                "attempt_id": action.attempt_id,
                "adjudication_json": record.to_json(),
                "created_at": "now",
            }
        ]

        turn = TurnPresenter().present_history(rows, campaign_id=3, session_id=4)[0]

        self.assertEqual(roller.calls, 1)
        self.assertEqual(turn["action_assessment"]["adjudication"]["check"]["selected_d20"], 14)
        self.assertEqual(turn["action_assessment"]["adjudication"]["check"]["total"], 16)
        self.assertEqual(turn["dice_events"][0]["rolls"], [14])

    def test_replayed_result_does_not_increment_pending_review_count_again(self) -> None:
        result = TurnResult(
            turn_index=2,
            dm_raw_text="raw",
            dm=DMStructuredResponse(
                narration="已保存的结果。",
                choices=["继续", "返回"],
                dm_notes="",
                memory_suggestions="",
                state_delta_json='{"hp": 9}',
            ),
            recalled_world=[],
            dice_events=[],
            replayed=True,
        )

        turn = TurnPresenter().present_result(result, player_text="重试")

        self.assertTrue(turn["replayed"])
        self.assertFalse(turn["has_pending_review"])
        self.assertEqual(turn["pending_review_delta"], 0)


if __name__ == "__main__":
    unittest.main()

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_person_dnd.adjudication import (
    ActionAdjudicator,
    AdjudicationRecord,
    AdjudicationRequest,
    AdjudicationStoreBusy,
    AttemptConflict,
    InvalidAdjudicationInput,
    SequenceRoller,
)
from one_person_dnd.db.conn import get_connection
from one_person_dnd.db.repos import campaigns, character_sheets, sessions
from one_person_dnd.db.schema import init_db
from one_person_dnd.domain.actions import PlayerAction
from one_person_dnd.domain.characters import summarize_character_sheet


class TestActionAdjudicator(unittest.TestCase):
    def _game(
        self,
        character: dict | None = None,
        *,
        session_state: dict | None = None,
    ):
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "test.sqlite3"
        init_db(db_path)
        conn = get_connection(db_path)
        campaign_id = campaigns.create_campaign(conn, "裁决测试")
        session_id = sessions.create_session(
            conn,
            campaign_id=campaign_id,
            title="第一章",
            current_scene="测试场景",
        )
        if character is not None:
            character_sheets.upsert_character_sheet(
                conn,
                session_id=session_id,
                json_text=json.dumps({"party": [character]}, ensure_ascii=False),
            )
        if session_state is not None:
            sessions.update_session_sidebar(
                conn,
                campaign_id=campaign_id,
                session_id=session_id,
                current_scene="测试场景",
                session_state=json.dumps(session_state, ensure_ascii=False),
                pinned_world_notes="",
            )
        conn.commit()
        return tmp, conn, campaign_id, session_id

    @staticmethod
    def _action(campaign_id: int, session_id: int, text: str) -> PlayerAction:
        return PlayerAction(campaign_id=campaign_id, session_id=session_id, text=text)

    def test_meaningful_gate_skips_routine_action_without_rolling(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"name": "艾拉", "ability_scores": {"DEX": 14}})
        try:
            roller = SequenceRoller([])
            record = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                AdjudicationRequest("routine-1", self._action(campaign_id, session_id, "我走到桌边坐下"))
            )

            self.assertEqual(record.status, "no_check")
            self.assertIsNone(record.check)
            self.assertEqual(roller.calls, 0)
            self.assertIn("no_check_needed", record.signals)
        finally:
            conn.close()
            tmp.cleanup()

    def test_investigating_an_attacker_trace_remains_an_exploration_check(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"name": "艾拉", "ability_scores": {"INT": 14}}
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([12])).adjudicate(
                AdjudicationRequest(
                    "attacker-trace",
                    self._action(campaign_id, session_id, "我调查攻击者留下的足迹"),
                )
            )

            self.assertEqual(record.status, "resolved")
            self.assertEqual(record.action_type, "exploration")
            self.assertIsNotNone(record.check)
            assert record.check is not None
            self.assertEqual(record.check.skill, "Investigation")
        finally:
            conn.close()
            tmp.cleanup()

    def test_locked_ledger_read_is_a_typed_busy_error_before_rolling(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"name": "艾拉", "ability_scores": {"INT": 14}}
        )
        roller = SequenceRoller([12])
        try:
            with (
                patch(
                    "one_person_dnd.db.repos.adjudication_records.get_by_attempt",
                    side_effect=sqlite3.OperationalError("database is locked"),
                ),
                self.assertRaises(AdjudicationStoreBusy),
            ):
                ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                    AdjudicationRequest(
                        "locked-ledger-read",
                        self._action(campaign_id, session_id, "我调查门锁"),
                    )
                )

            self.assertEqual(roller.calls, 0)
        finally:
            conn.close()
            tmp.cleanup()

    def test_observing_traces_of_a_past_battle_remains_exploration(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"name": "艾拉", "ability_scores": {"WIS": 14}}
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([12])).adjudicate(
                AdjudicationRequest(
                    "battle-traces",
                    self._action(campaign_id, session_id, "我观察战斗留下的痕迹"),
                )
            )

            self.assertEqual(record.status, "resolved")
            self.assertEqual(record.action_type, "exploration")
            self.assertIsNotNone(record.check)
            assert record.check is not None
            self.assertEqual(record.check.skill, "Perception")
        finally:
            conn.close()
            tmp.cleanup()

    def test_stabbing_with_a_sword_is_explicitly_unsupported(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"name": "艾拉", "ability_scores": {"STR": 14}}
        )
        try:
            roller = SequenceRoller([])
            record = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                AdjudicationRequest(
                    "sword-stab",
                    self._action(campaign_id, session_id, "我用剑刺向哥布林"),
                )
            )

            self.assertEqual(record.status, "unsupported")
            self.assertEqual(record.action_type, "combat")
            self.assertIsNone(record.check)
            self.assertEqual(roller.calls, 0)
            self.assertIn("adjudication_unsupported", record.signals)
        finally:
            conn.close()
            tmp.cleanup()

    def test_explicit_weapon_attack_verbs_are_unsupported(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"name": "艾拉", "ability_scores": {"STR": 14, "DEX": 14}}
        )
        try:
            for index, text in enumerate(
                ("我用斧头劈向兽人", "我举锤砸向骷髅", "我用弓射向狼"),
                start=1,
            ):
                with self.subTest(text=text):
                    roller = SequenceRoller([])
                    record = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                        AdjudicationRequest(
                            f"weapon-attack-{index}",
                            self._action(campaign_id, session_id, text),
                        )
                    )

                    self.assertEqual(record.status, "unsupported")
                    self.assertEqual(record.action_type, "combat")
                    self.assertEqual(roller.calls, 0)
        finally:
            conn.close()
            tmp.cleanup()

    def test_ability_score_proficiency_and_standard_dc_form_one_check(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {
                "name": "艾拉",
                "level": 3,
                "ability_scores": {"DEX": 14},
                "skill_proficiencies": ["Acrobatics"],
            }
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([11])).adjudicate(
                AdjudicationRequest("check-1", self._action(campaign_id, session_id, "我翻越湿滑的栏杆"))
            )

            self.assertEqual(record.status, "resolved")
            check = record.check
            self.assertIsNotNone(check)
            assert check is not None
            self.assertEqual(check.ability, "DEX")
            self.assertEqual(check.skill, "Acrobatics")
            self.assertEqual(check.dc, 15)
            self.assertIn("标准 DC 15", check.dc_reason)
            self.assertEqual(check.ability_modifier, 2)
            self.assertEqual(check.proficiency_modifier, 2)
            self.assertEqual(check.total, 15)
            self.assertEqual(check.margin, 0)
            self.assertEqual(check.outcome, "success")
        finally:
            conn.close()
            tmp.cleanup()

    def test_advantage_and_disadvantage_fully_cancel_regardless_of_source_count(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {
                "ability_scores": {"DEX": 14},
                "check_advantages": {"Acrobatics": ["绳索帮助", "同伴指引"]},
                "check_disadvantages": {"Acrobatics": ["表面湿滑"]},
            }
        )
        try:
            roller = SequenceRoller([12])
            record = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                AdjudicationRequest("cancel-1", self._action(campaign_id, session_id, "我翻越栏杆"))
            )

            assert record.check is not None
            self.assertEqual(record.check.roll_mode, "normal")
            self.assertEqual(record.check.d20s, (12,))
            self.assertEqual(len(record.check.advantage_sources), 2)
            self.assertEqual(len(record.check.disadvantage_sources), 1)
            self.assertEqual(roller.calls, 1)
        finally:
            conn.close()
            tmp.cleanup()

    def test_advantage_rolls_two_and_selects_higher_face(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {
                "ability_scores": {"DEX": 12},
                "check_advantages": {"Stealth": ["结构化隐蔽条件"]},
            }
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([4, 17])).adjudicate(
                AdjudicationRequest("adv-1", self._action(campaign_id, session_id, "我潜行绕过守卫"))
            )

            assert record.check is not None
            self.assertEqual(record.check.roll_mode, "advantage")
            self.assertEqual(record.check.d20s, (4, 17))
            self.assertEqual(record.check.selected_d20, 17)
        finally:
            conn.close()
            tmp.cleanup()

    def test_natural_twenty_does_not_override_failed_ability_check(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"ability_scores": {"DEX": 1}},
            session_state={"adjudication": {"dc": 30, "dc_reason": "系统记录的近乎不可能障碍"}},
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([20])).adjudicate(
                AdjudicationRequest("nat20", self._action(campaign_id, session_id, "我翻越栏杆"))
            )

            assert record.check is not None
            self.assertEqual(record.check.natural_face, "natural_20")
            self.assertEqual(record.check.total, 15)
            self.assertEqual(record.check.outcome, "failure")
        finally:
            conn.close()
            tmp.cleanup()

    def test_natural_one_does_not_override_successful_ability_check(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"ability_scores": {"WIS": 30}},
            session_state={"adjudication": {"dc": 5, "dc_reason": "系统记录的极明显线索"}},
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([1])).adjudicate(
                AdjudicationRequest("nat1", self._action(campaign_id, session_id, "我观察门上的巨大标记"))
            )

            assert record.check is not None
            self.assertEqual(record.check.natural_face, "natural_1")
            self.assertEqual(record.check.total, 11)
            self.assertEqual(record.check.outcome, "success")
        finally:
            conn.close()
            tmp.cleanup()

    def test_manual_roll_is_recorded_but_not_promoted_to_canonical_check(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"WIS": 18}})
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([12])).adjudicate(
                AdjudicationRequest("manual-1", self._action(campaign_id, session_id, "我观察门锁并掷 1d20+5"))
            )

            self.assertEqual(record.status, "no_check")
            self.assertIsNone(record.check)
            self.assertEqual(record.manual_rolls[0]["total"], 17)
            self.assertIn("manual_roll_not_canonical", record.signals)
        finally:
            conn.close()
            tmp.cleanup()

    def test_combat_and_attack_are_explicitly_unsupported(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"STR": 18}})
        try:
            roller = SequenceRoller([])
            record = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                AdjudicationRequest("combat-1", self._action(campaign_id, session_id, "我挥砍攻击兽人"))
            )

            self.assertEqual(record.status, "unsupported")
            self.assertIsNone(record.check)
            self.assertEqual(roller.calls, 0)
            self.assertIn("unsupported_attack_save_or_combat", record.warnings)

            save = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                AdjudicationRequest("save-1", self._action(campaign_id, session_id, "我躲避火球"))
            )
            self.assertEqual(save.status, "unsupported")
            self.assertEqual(roller.calls, 0)
        finally:
            conn.close()
            tmp.cleanup()

    def test_proficient_skill_without_level_defaults_to_level_one_once(self) -> None:
        tmp, conn, campaign_id, session_id = self._game(
            {"ability_scores": {"CHA": 12}, "skill_proficiencies": ["Persuasion"]}
        )
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([12])).adjudicate(
                AdjudicationRequest("pb-default", self._action(campaign_id, session_id, "我说服守卫放行"))
            )

            assert record.check is not None
            self.assertEqual(record.check.proficiency_modifier, 2)
            self.assertEqual(
                sum("熟练" in source for source in record.check.modifier_sources),
                1,
            )
            self.assertIn("proficiency_level_defaulted_to_1", record.warnings)
        finally:
            conn.close()
            tmp.cleanup()

    def test_retry_replays_persisted_record_and_conflicting_payload_fails(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"WIS": 14}})
        try:
            first_roller = SequenceRoller([13])
            action = self._action(campaign_id, session_id, "我观察暗门")
            first = ActionAdjudicator(conn=conn, roller=first_roller).adjudicate(
                AdjudicationRequest("retry-1", action)
            )
            conn.commit()

            replay_roller = SequenceRoller([])
            replay = ActionAdjudicator(conn=conn, roller=replay_roller).adjudicate(
                AdjudicationRequest("retry-1", action)
            )
            self.assertEqual(replay, first)
            self.assertEqual(replay_roller.calls, 0)

            with self.assertRaises(AttemptConflict):
                ActionAdjudicator(conn=conn, roller=SequenceRoller([])).adjudicate(
                    AdjudicationRequest(
                        "retry-1",
                        self._action(campaign_id, session_id, "我调查另一扇门"),
                    )
                )
        finally:
            conn.close()
            tmp.cleanup()

    def test_invalid_selected_ability_needs_input_without_rolling(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"DEX": "+3"}})
        try:
            roller = SequenceRoller([])
            record = ActionAdjudicator(conn=conn, roller=roller).adjudicate(
                AdjudicationRequest("invalid-1", self._action(campaign_id, session_id, "我翻越栏杆"))
            )

            self.assertEqual(record.status, "needs_input")
            self.assertEqual(roller.calls, 0)
            self.assertIn("invalid_ability_score:DEX", record.warnings)
        finally:
            conn.close()
            tmp.cleanup()

    def test_unreadable_or_ambiguous_ability_data_needs_input_without_rolling(self) -> None:
        cases = (
            ("malformed sheet", "{not json"),
            ("non-object abilities", json.dumps({"abilities": ["DEX", 14]})),
            ("ambiguous DEX", json.dumps({"abilities": {"DEX": 14, "敏捷": 15}})),
        )

        for index, (label, sheet_text) in enumerate(cases):
            with self.subTest(label=label):
                roller = SequenceRoller([])
                record = ActionAdjudicator(
                    roller=roller,
                    character_loader=lambda _, raw=sheet_text: summarize_character_sheet(raw),
                ).adjudicate(
                    AdjudicationRequest(
                        f"invalid-sheet-{index}",
                        self._action(1, 1, "我翻越栏杆"),
                    )
                )

                self.assertEqual(record.status, "needs_input")
                self.assertIsNone(record.check)
                self.assertEqual(roller.calls, 0)
                self.assertIn("invalid_ability_score:DEX", record.warnings)

    def test_legacy_character_missing_selected_ability_still_defaults_to_ten(self) -> None:
        roller = SequenceRoller([11])
        record = ActionAdjudicator(
            roller=roller,
            character_loader=lambda _: summarize_character_sheet(
                json.dumps({"name": "旧角色", "abilities": {"WIS": 12}}, ensure_ascii=False)
            ),
        ).adjudicate(
            AdjudicationRequest("legacy-missing-dex", self._action(1, 1, "我翻越栏杆"))
        )

        self.assertEqual(record.status, "resolved")
        self.assertEqual(roller.calls, 1)
        self.assertIsNotNone(record.check)
        assert record.check is not None
        self.assertEqual(record.check.ability_score, 10)
        self.assertIn("ability_defaulted_to_10:DEX", record.warnings)

    def test_record_json_round_trip_preserves_check_invariants(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"CHA": 16}})
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([10])).adjudicate(
                AdjudicationRequest("json-1", self._action(campaign_id, session_id, "我说服守卫放行"))
            )

            self.assertEqual(AdjudicationRecord.from_json(record.to_json()), record)
            assessment = record.to_action_assessment()
            self.assertIs(assessment.adjudication, record)
            self.assertEqual(assessment.dice_events[-1]["total"], record.check.total if record.check else None)
        finally:
            conn.close()
            tmp.cleanup()

    def test_record_rejects_manual_and_canonical_roll_in_same_result(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"DEX": 12}})
        try:
            record = ActionAdjudicator(conn=conn, roller=SequenceRoller([14])).adjudicate(
                AdjudicationRequest("exclusive-rolls", self._action(campaign_id, session_id, "我尝试开锁"))
            )
            payload = record.to_dict()
            payload["manual_rolls"] = [
                {"expr": "1d20", "count": 1, "sides": 20, "modifier": 0, "rolls": [9], "total": 9}
            ]

            with self.assertRaisesRegex(ValueError, "manual rolls"):
                AdjudicationRecord.from_dict(payload)
        finally:
            conn.close()
            tmp.cleanup()

    def test_request_rejects_attempt_or_campaign_session_mismatch(self) -> None:
        tmp, conn, campaign_id, session_id = self._game({"ability_scores": {"WIS": 12}})
        try:
            adjudicator = ActionAdjudicator(conn=conn, roller=SequenceRoller([]))
            with self.assertRaises(InvalidAdjudicationInput):
                adjudicator.adjudicate(
                    AdjudicationRequest(
                        "request-id",
                        PlayerAction(
                            campaign_id=campaign_id,
                            session_id=session_id,
                            text="我走到桌边",
                            attempt_id="different-id",
                        ),
                    )
                )
            with self.assertRaises(InvalidAdjudicationInput):
                adjudicator.adjudicate(
                    AdjudicationRequest(
                        "wrong-campaign",
                        PlayerAction(campaign_id=campaign_id + 99, session_id=session_id, text="我走到桌边"),
                    )
                )
        finally:
            conn.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

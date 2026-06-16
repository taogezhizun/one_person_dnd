import json
import unittest

from one_person_dnd.domain.state_changes import merge_state_delta, preview_state_delta


class TestStateChanges(unittest.TestCase):
    def test_merge_party_member_delta_preserves_existing_fields(self) -> None:
        base = {
            "party": [
                {
                    "name": "艾拉",
                    "race": "人类",
                    "class": "游侠",
                    "hp": 8,
                    "max_hp": 12,
                    "gold": 15,
                    "inventory": ["短弓"],
                }
            ],
            "notes": "害怕深水。",
        }
        delta = {"party": [{"hp": 6, "gold": 18}]}

        merged = merge_state_delta(base, delta)

        self.assertEqual(merged["party"][0]["name"], "艾拉")
        self.assertEqual(merged["party"][0]["class"], "游侠")
        self.assertEqual(merged["party"][0]["inventory"], ["短弓"])
        self.assertEqual(merged["party"][0]["hp"], 6)
        self.assertEqual(merged["party"][0]["gold"], 18)
        self.assertEqual(merged["notes"], "害怕深水。")

    def test_preview_summarizes_recognized_character_changes(self) -> None:
        base = {
            "party": [
                {
                    "name": "艾拉",
                    "hp": 8,
                    "max_hp": 12,
                    "gold": 15,
                    "inventory": ["短弓"],
                }
            ]
        }
        delta = {"party": [{"hp": 6, "gold": 18, "inventory": ["短弓", "银钥匙"]}]}

        preview = preview_state_delta(
            json.dumps(base, ensure_ascii=False),
            json.dumps(delta, ensure_ascii=False),
        )

        self.assertTrue(preview.ok)
        self.assertEqual(preview.summary, "将更新角色状态")
        self.assertIn("HP：8 -> 6", preview.lines)
        self.assertIn("金币：15 -> 18", preview.lines)
        self.assertIn("物品：短弓 -> 短弓、银钥匙", preview.lines)

    def test_preview_reports_invalid_delta(self) -> None:
        preview = preview_state_delta("{}", "{not json")

        self.assertFalse(preview.ok)
        self.assertEqual(preview.summary, "无法预览变更")
        self.assertTrue(preview.lines)
        self.assertIn("JSON", preview.lines[0])

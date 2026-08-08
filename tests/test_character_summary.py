import json
import unittest

from one_person_dnd.domain.characters import summarize_character_sheet


class TestCharacterSummary(unittest.TestCase):
    def test_summarizes_party_member_for_prompt(self) -> None:
        sheet = {
            "party": [
                {
                    "name": "艾拉",
                    "race": "人类",
                    "class": "游侠",
                    "background": "边境猎人",
                    "goal": "找到失踪的导师",
                    "hp": 8,
                    "max_hp": 12,
                    "gold": 15,
                    "level": 3,
                    "inventory": ["短弓", "绳索"],
                    "abilities": {"DEX": 14, "WIS": 13},
                    "skill_proficiencies": ["Acrobatics", "察觉"],
                    "conditions": ["中毒", "隐匿"],
                }
            ],
            "notes": "害怕深水。",
        }

        summary = summarize_character_sheet(json.dumps(sheet, ensure_ascii=False))
        prompt_text = summary.to_prompt_text()

        self.assertEqual(summary.name, "艾拉")
        self.assertEqual(summary.hp, 8)
        self.assertEqual(summary.max_hp, 12)
        self.assertEqual(summary.gold, 15)
        self.assertEqual(summary.level, 3)
        self.assertEqual(summary.ability_scores, {"DEX": 14, "WIS": 13})
        self.assertEqual(summary.skill_proficiencies, ["Acrobatics", "Perception"])
        self.assertEqual(summary.inventory, ["短弓", "绳索"])
        self.assertEqual(summary.conditions, ["中毒", "隐匿"])
        self.assertEqual(summary.notes, "害怕深水。")
        self.assertIn("艾拉", prompt_text)
        self.assertIn("人类 / 游侠", prompt_text)
        self.assertIn("HP：8/12", prompt_text)
        self.assertIn("金币：15", prompt_text)
        self.assertIn("物品：短弓、绳索", prompt_text)
        self.assertIn("状态：中毒、隐匿", prompt_text)
        self.assertIn("属性：DEX 14，WIS 13", prompt_text)
        self.assertIn("等级：3", prompt_text)
        self.assertIn("技能熟练：Acrobatics、Perception", prompt_text)
        self.assertIn("备注：害怕深水。", prompt_text)
        self.assertIn("目标：找到失踪的导师", prompt_text)

    def test_summarizes_top_level_legacy_sheet(self) -> None:
        sheet = {"name": "独行者", "hp": 6, "gold": 2, "inventory": "匕首,火把"}

        summary = summarize_character_sheet(json.dumps(sheet, ensure_ascii=False))

        self.assertEqual(summary.name, "独行者")
        self.assertEqual(summary.inventory, ["匕首", "火把"])

    def test_invalid_sheet_returns_empty_summary(self) -> None:
        summary = summarize_character_sheet("{not json")

        self.assertFalse(summary.has_content)
        self.assertEqual(summary.to_prompt_text(), "")
        self.assertEqual(
            set(summary.invalid_ability_scores),
            {"STR", "DEX", "CON", "INT", "WIS", "CHA"},
        )
        self.assertIn("invalid_character_sheet", summary.rule_warnings)

    def test_rule_fields_reject_ambiguous_scores_and_normalize_aliases(self) -> None:
        sheet = {
            "name": "旧角色",
            "level": "3",
            "ability_scores": {"敏捷": 14, "WIS": "+2", "STR": 31},
            "skill_proficiencies": ["隐匿", "unknown skill"],
            "check_advantages": {"Stealth": ["结构化隐蔽条件"]},
        }

        summary = summarize_character_sheet(json.dumps(sheet, ensure_ascii=False))

        self.assertEqual(summary.ability_scores, {"DEX": 14})
        self.assertEqual(summary.invalid_ability_scores, ["WIS", "STR"])
        self.assertTrue(summary.level_invalid)
        self.assertEqual(summary.skill_proficiencies, ["Stealth"])
        self.assertEqual(summary.check_advantages, {"Stealth": ["结构化隐蔽条件"]})
        self.assertIn("invalid_ability_scores", summary.rule_warnings)
        self.assertIn("invalid_level", summary.rule_warnings)
        self.assertIn("unknown_skill_proficiencies", summary.rule_warnings)

    def test_non_object_abilities_make_every_score_unusable(self) -> None:
        summary = summarize_character_sheet(
            json.dumps({"party": [{"name": "损坏角色", "abilities": ["DEX", 14]}]}, ensure_ascii=False)
        )

        self.assertEqual(summary.name, "损坏角色")
        self.assertEqual(summary.abilities, {})
        self.assertEqual(summary.ability_scores, {})
        self.assertEqual(
            set(summary.invalid_ability_scores),
            {"STR", "DEX", "CON", "INT", "WIS", "CHA"},
        )
        self.assertIn("invalid_ability_scores", summary.rule_warnings)

import unittest

from one_person_dnd.engine.parser import parse_dm_text


class TestParseDMText(unittest.TestCase):
    def test_delimited_protocol(self) -> None:
        text = "\n".join(
            [
                "===NARRATION===",
                "你站在一扇门前。",
                "===CHOICES===",
                "- 推门",
                "- 观察四周",
                "===DM_NOTES===",
                "门上有微弱的魔法痕迹。",
                "===MEMORY===",
                "玩家来到古塔一层的门前。",
            ]
        )
        dm = parse_dm_text(text)
        self.assertEqual(dm.narration, "你站在一扇门前。")
        self.assertEqual(dm.choices, ["推门", "观察四周"])
        self.assertEqual(dm.dm_notes, "门上有微弱的魔法痕迹。")
        self.assertEqual(dm.memory_suggestions, "玩家来到古塔一层的门前。")

    def test_choices_numbering_is_trimmed(self) -> None:
        text = "\n".join(
            [
                "===NARRATION===",
                "test",
                "===CHOICES===",
                "1. 走",
                "2) 跑",
                "- 跳",
                "===DM_NOTES===",
                "",
                "===MEMORY===",
                "",
            ]
        )
        dm = parse_dm_text(text)
        self.assertEqual(dm.choices, ["走", "跑", "跳"])

    def test_fallback_extracts_inline_chinese_optional_actions(self) -> None:
        text = "\n".join(
            [
                "你蹲在老橡树旁，看到树根间有一片被翻动过的泥土。",
                "",
                "可选行动：",
                "- 动手挖开那片泥土",
                "1. 先环顾四周，确认附近无人监视",
                "2) 用匕首试探泥土下方是否有硬物",
            ]
        )

        dm = parse_dm_text(text)

        self.assertEqual(dm.narration, "你蹲在老橡树旁，看到树根间有一片被翻动过的泥土。")
        self.assertEqual(
            dm.choices,
            [
                "动手挖开那片泥土",
                "先环顾四周，确认附近无人监视",
                "用匕首试探泥土下方是否有硬物",
            ],
        )

    def test_fallback_extracts_markdown_bold_optional_actions_heading(self) -> None:
        text = "\n".join(
            [
                "石板边缘没有明显缝隙。",
                "",
                "**可选行动：**",
                "- 尝试用匕首沿着边缘撬动",
                "- 退开一些观察石板与树根的相对位置",
            ]
        )

        dm = parse_dm_text(text)

        self.assertEqual(dm.narration, "石板边缘没有明显缝隙。")
        self.assertEqual(
            dm.choices,
            [
                "尝试用匕首沿着边缘撬动",
                "退开一些观察石板与树根的相对位置",
            ],
        )

    def test_empty_text(self) -> None:
        dm = parse_dm_text("")
        self.assertEqual(dm.narration, "")
        self.assertEqual(dm.choices, [])
        self.assertEqual(dm.dm_notes, "")
        self.assertEqual(dm.memory_suggestions, "")

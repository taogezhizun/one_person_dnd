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

    def test_empty_text(self) -> None:
        dm = parse_dm_text("")
        self.assertEqual(dm.narration, "")
        self.assertEqual(dm.choices, [])
        self.assertEqual(dm.dm_notes, "")
        self.assertEqual(dm.memory_suggestions, "")


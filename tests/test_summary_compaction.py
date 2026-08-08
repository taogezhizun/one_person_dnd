import unittest

from one_person_dnd.engine.orchestrator import _compact_memory_blocks


class TestSummaryCompaction(unittest.TestCase):
    def test_short_memory_is_deduplicated_without_reordering(self) -> None:
        result = _compact_memory_blocks(["开局约定", "发现密门", "发现密门", "拿到钥匙"], 200)

        self.assertEqual(result, "开局约定\n发现密门\n拿到钥匙")

    def test_long_memory_keeps_premise_and_latest_progress(self) -> None:
        blocks = [f"事件 {index}：" + ("细节" * 20) for index in range(10)]

        result = _compact_memory_blocks(blocks, 180)

        self.assertLessEqual(len(result), 180)
        self.assertIn("事件 0", result)
        self.assertIn("事件 9", result)
        self.assertIn("中段记忆已压缩", result)

    def test_overlong_edge_blocks_are_bounded(self) -> None:
        result = _compact_memory_blocks(["开" * 300, "末" * 300], 100)

        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.startswith("开"))
        self.assertTrue(result.endswith("…"))


if __name__ == "__main__":
    unittest.main()

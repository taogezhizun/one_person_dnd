import unittest

from one_person_dnd.engine import protocol


class TestProtocolConstants(unittest.TestCase):
    def test_delimiter_literals(self) -> None:
        self.assertEqual(protocol.NARRATION, "===NARRATION===")
        self.assertEqual(protocol.CHOICES, "===CHOICES===")
        self.assertEqual(protocol.DM_NOTES, "===DM_NOTES===")
        self.assertEqual(protocol.MEMORY, "===MEMORY===")
        self.assertEqual(protocol.STATE_DELTA, "===STATE_DELTA===")
        self.assertEqual(protocol.THREAD_UPDATES, "===THREAD_UPDATES===")

    def test_required_and_optional_groupings(self) -> None:
        self.assertEqual(
            protocol.REQUIRED_DELIMITERS,
            ("===NARRATION===", "===CHOICES===", "===DM_NOTES===", "===MEMORY==="),
        )
        self.assertEqual(protocol.OPTIONAL_DELIMITERS, ("===STATE_DELTA===", "===THREAD_UPDATES==="))

    def test_delimiter_fields_mapping_used_by_parser(self) -> None:
        self.assertEqual(
            protocol.DELIMITER_FIELDS,
            {
                "===NARRATION===": "narration",
                "===CHOICES===": "choices",
                "===DM_NOTES===": "dm_notes",
                "===MEMORY===": "memory_suggestions",
                "===STATE_DELTA===": "state_delta_json",
                "===THREAD_UPDATES===": "thread_updates_json",
            },
        )


if __name__ == "__main__":
    unittest.main()

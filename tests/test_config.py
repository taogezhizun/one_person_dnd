import tempfile
import unittest
from pathlib import Path

from one_person_dnd.config import AppState, LLMConfig, load_app_state, load_llm_config, load_memory_config, save_app_state, save_llm_config
from one_person_dnd.engine.constants import HISTORY_TURNS_FOR_PROMPT, STORY_JOURNAL_FOR_PROMPT


class TestConfig(unittest.TestCase):
    def test_llm_roundtrip_allows_empty_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "api_config.ini"
            save_llm_config(
                p,
                LLMConfig(
                    base_url="http://localhost:8000/v1",
                    api_key="",
                    model="m",
                    timeout_seconds=12.5,
                ),
            )
            cfg = load_llm_config(p)
            self.assertIsNotNone(cfg)
            assert cfg is not None
            self.assertEqual(cfg.provider, "openai_compat")
            self.assertEqual(cfg.base_url, "http://localhost:8000/v1")
            self.assertEqual(cfg.api_key, "")
            self.assertEqual(cfg.model, "m")
            self.assertEqual(cfg.timeout_seconds, 12.5)

    def test_app_state_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "api_config.ini"
            save_app_state(p, AppState(active_campaign_id=1, active_session_id=2))
            s = load_app_state(p)
            self.assertEqual(s.active_campaign_id, 1)
            self.assertEqual(s.active_session_id, 2)

    def test_memory_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "api_config.ini"
            m = load_memory_config(p)
            self.assertEqual(m.history_turns_for_prompt, HISTORY_TURNS_FOR_PROMPT)
            self.assertEqual(m.story_journal_for_prompt, STORY_JOURNAL_FOR_PROMPT)

    def test_memory_invalid_values_fallback_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "api_config.ini"
            p.write_text(
                "\n".join(
                    [
                        "[memory]",
                        "history_turns_for_prompt = abc",
                        "story_journal_for_prompt = ???",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            m = load_memory_config(p)
            self.assertEqual(m.history_turns_for_prompt, HISTORY_TURNS_FOR_PROMPT)
            self.assertEqual(m.story_journal_for_prompt, STORY_JOURNAL_FOR_PROMPT)


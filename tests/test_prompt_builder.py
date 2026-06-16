import unittest

from one_person_dnd.context.pack import ContextBlock, ContextPack
from one_person_dnd.engine.prompt_builder import RetrievedMemory, build_dm_messages
from one_person_dnd.engine.prompt_builder import build_dm_messages_from_context_pack


class TestPromptBuilder(unittest.TestCase):
    def test_system_prompt_documents_thread_updates_schema(self) -> None:
        messages = build_dm_messages(
            memory=RetrievedMemory(world_bible_blocks=[], story_blocks=[]),
            state_block="",
        )

        system = messages[0].content

        self.assertIn("===THREAD_UPDATES===", system)
        self.assertIn('"updates"', system)
        self.assertIn('"id"', system)
        self.assertIn('"title"', system)
        self.assertIn('"next_step"', system)

    def test_context_pack_prompt_uses_only_retained_blocks(self) -> None:
        pack = ContextPack(
            campaign_id=1,
            session_id=2,
            action_text="我检查门厅",
            blocks=[
                ContextBlock(
                    kind="character_state",
                    title="Character Sheet",
                    content="艾拉 HP：8/12",
                    source="character_sheets",
                    priority=95,
                ),
                ContextBlock(
                    kind="story_memory",
                    title="Story Memory 1",
                    content="保留下来的近期剧情摘要",
                    source="story_journal",
                    priority=50,
                ),
            ],
            recalled_context=[
                {
                    "kind": "story_memory",
                    "title": "Story Memory 2",
                    "source": "story_journal",
                    "status": "skipped",
                    "reason": "因上下文预算裁剪。",
                    "preview": "被裁剪的旧剧情摘要",
                }
            ],
        )

        messages = build_dm_messages_from_context_pack(pack)
        context = messages[1].content

        self.assertIn("艾拉 HP：8/12", context)
        self.assertIn("保留下来的近期剧情摘要", context)
        self.assertNotIn("被裁剪的旧剧情摘要", context)

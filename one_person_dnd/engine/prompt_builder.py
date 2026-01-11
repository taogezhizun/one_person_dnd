from __future__ import annotations

from dataclasses import dataclass

from one_person_dnd.llm import ChatMessage


@dataclass(frozen=True)
class RetrievedMemory:
    world_bible_blocks: list[str]
    story_blocks: list[str]


def build_dm_messages(
    *,
    memory: RetrievedMemory,
    state_block: str,
    player_text: str,
) -> list[ChatMessage]:
    system = (
        "你是 Dungeon Master（DM）。\n"
        "硬规则：不得改写或违反世界设定（WorldBible）。不得替玩家做决定，只能给出选项。\n"
        "输出必须严格按以下四段分隔符输出（分隔符单独占一行，大小写一致，前后不要加任何符号/加粗）：\n"
        "===NARRATION===\n"
        "(这里写叙事，使用 Markdown 也可以)\n"
        "===CHOICES===\n"
        "(这里给玩家 3-6 条可选行动，每条一行，以 - 开头)\n"
        "===DM_NOTES===\n"
        "(这里写给系统看的 DM 备注，可简短)\n"
        "===MEMORY===\n"
        "(这里写建议写入剧情摘要的要点，可简短)\n"
        "禁止输出以上分隔符之外的额外前缀/标题。\n"
        "请用中文。"
    )

    world = "\n\n".join(memory.world_bible_blocks) or "（无相关世界设定条目）"
    story = "\n\n".join(memory.story_blocks) or "（无近期剧情摘要）"

    user = (
        "【WorldBible】\n"
        f"{world}\n\n"
        "【StoryJournal】\n"
        f"{story}\n\n"
        "【当前状态】\n"
        f"{state_block}\n\n"
        "【玩家输入】\n"
        f"{player_text}\n"
    )

    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


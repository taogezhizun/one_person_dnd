from __future__ import annotations

from dataclasses import dataclass, field

from one_person_dnd.context.pack import ContextPack
from one_person_dnd.llm import ChatMessage


@dataclass(frozen=True)
class RetrievedMemory:
    world_bible_blocks: list[str]
    story_blocks: list[str]
    plot_threads_blocks: list[str] = field(default_factory=list)  # open threads, formatted for prompt


def build_dm_messages(
    *,
    memory: RetrievedMemory,
    state_block: str,
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
        "你可以在最后追加可选段（如果需要）：\n"
        "===STATE_DELTA===\n"
        "(JSON，对角色卡/物品/HP/金币等的变更建议；留空也可以)\n"
        "===THREAD_UPDATES===\n"
        '(JSON，对主线线程的更新建议；留空也可以。格式必须是 {"updates":[...]}。'
        '更新已有线程用 {"id":1,"summary":"...","next_step":"...","status":"open"}；'
        '新建线程用 {"title":"...","priority":1,"summary":"...","next_step":"...","tags":"主线"}。'
        "status 只能是 open 或 closed)\n"
        "禁止输出任何不在以上分隔符内的额外前缀/标题。\n"
        "请用中文。"
    )

    world = "\n\n".join(memory.world_bible_blocks) or "（无相关世界设定条目）"
    story = "\n\n".join(memory.story_blocks) or "（无近期剧情摘要）"
    threads = ""
    if memory.plot_threads_blocks:
        threads = "\n\n".join(memory.plot_threads_blocks).strip()

    context = (
        "【WorldBible】\n"
        f"{world}\n\n"
        "【PlotThreads】\n"
        f"{threads or '（无进行中的主线线程）'}\n\n"
        "【StoryJournal】\n"
        f"{story}\n\n"
        "【当前状态】\n"
        f"{state_block}\n"
    )

    return [
        ChatMessage(role="system", content=system),
        # Use a second system message to provide stable context blocks.
        ChatMessage(role="system", content=context),
    ]


def build_dm_messages_from_context_pack(pack: ContextPack) -> list[ChatMessage]:
    world_blocks = [b.content for b in pack.blocks if b.kind == "world_bible"]
    story_blocks = [b.content for b in pack.blocks if b.kind == "story_memory"]
    thread_blocks = [b.content for b in pack.blocks if b.kind == "plot_threads"]
    state_parts = [
        b.content
        for b in pack.blocks
        if b.kind in ("scene_state", "character_state", "dice", "action_assessment", "cheat_directive")
    ]
    return build_dm_messages(
        memory=RetrievedMemory(
            world_bible_blocks=world_blocks,
            story_blocks=story_blocks,
            plot_threads_blocks=thread_blocks,
        ),
        state_block="\n\n".join([p for p in state_parts if p.strip()]).strip(),
    )

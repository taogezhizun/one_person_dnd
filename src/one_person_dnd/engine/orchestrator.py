from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from one_person_dnd.config import LLMConfig, MemoryConfig
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import sessions, story_journal, turn_logs, world_bible
from one_person_dnd.engine.constants import HISTORY_TURNS_FOR_PROMPT, STORY_JOURNAL_FOR_PROMPT
from one_person_dnd.engine.parser import DMStructuredResponse, parse_dm_text
from one_person_dnd.engine.prompt_builder import RetrievedMemory, build_dm_messages
from one_person_dnd.llm import ChatMessage, create_llm_client


@dataclass(frozen=True)
class TurnResult:
    turn_index: int
    dm_raw_text: str
    dm: DMStructuredResponse
    recalled_world: list[dict]


def _fetch_world_bible(
    conn: sqlite3.Connection,
    *,
    campaign_id: int,
    tags: list[str] | None,
    limit: int = 10,
) -> tuple[list[str], list[dict]]:
    rows = world_bible.select_world_bible_for_prompt(conn, campaign_id=campaign_id, tags=tags, limit=limit)

    blocks: list[str] = []
    preview: list[dict] = []
    for r in rows:
        blocks.append(f"[{r['type']}] {r['title']}\n标签：{r['tags'] or ''}\n{r['content']}")
        preview.append({"type": r["type"], "title": r["title"], "tags": r["tags"] or ""})
    return blocks, preview


def _fetch_story_journal(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    limit: int = STORY_JOURNAL_FOR_PROMPT,
) -> list[str]:
    rows = story_journal.select_story_journal_for_prompt(conn, session_id=session_id, limit=limit)
    blocks: list[str] = []
    for r in rows[::-1]:
        blocks.append(
            f"场景：{r['scene_id'] or ''}\n摘要：{r['summary']}\n未解决：{r['open_threads'] or ''}\n要点：{r['key_facts'] or ''}"
        )
    return blocks


def _next_turn_index(conn: sqlite3.Connection, session_id: int) -> int:
    return turn_logs.get_next_turn_index(conn, session_id)


def _get_session_scene_id(conn: sqlite3.Connection, session_id: int) -> str:
    return sessions.get_session_scene_id(conn, session_id)


def _fetch_recent_turn_context(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    limit: int,
) -> list[ChatMessage]:
    """
    Fetch recent turns and convert them into ChatMessages for LLM context.
    We include player_text as user messages, and DM narration/choices as assistant messages.
    """
    if limit <= 0:
        return []
    rows = turn_logs.list_recent_turn_pairs(conn, session_id=session_id, limit=limit)
    if not rows:
        return []

    msgs: list[ChatMessage] = []
    for r in rows[::-1]:
        player_text = (r["player_text"] or "").strip()
        dm_text = (r["dm_text"] or "").strip()
        if player_text:
            msgs.append(ChatMessage(role="user", content=player_text))
        if dm_text:
            dm = parse_dm_text(dm_text)
            assistant_parts: list[str] = []
            if dm.narration:
                assistant_parts.append(dm.narration.strip())
            if dm.choices:
                assistant_parts.append("可选行动：\n" + "\n".join([f"- {c}" for c in dm.choices]))
            assistant_content = "\n\n".join([p for p in assistant_parts if p.strip()]).strip()
            msgs.append(ChatMessage(role="assistant", content=assistant_content or dm_text))
    return msgs


def run_turn(
    *,
    db_path: Path,
    llm_cfg: LLMConfig,
    campaign_id: int,
    session_id: int,
    player_text: str,
    state_block: str,
    tags: list[str] | None = None,
    memory_cfg: MemoryConfig | None = None,
) -> TurnResult:
    conn = get_connection(db_path)
    try:
        memory_cfg = memory_cfg or MemoryConfig()
        world_blocks, world_preview = _fetch_world_bible(conn, campaign_id=campaign_id, tags=tags)
        memory = RetrievedMemory(
            world_bible_blocks=world_blocks,
            story_blocks=_fetch_story_journal(conn, session_id=session_id, limit=memory_cfg.story_journal_for_prompt),
        )
        # Base messages: system rules + stable context blocks (world/story/state)
        messages = build_dm_messages(memory=memory, state_block=state_block)
        # Add recent conversation turns for continuity
        messages.extend(_fetch_recent_turn_context(conn, session_id=session_id, limit=memory_cfg.history_turns_for_prompt))
        # Current player input as the last user message
        messages.append(ChatMessage(role="user", content=player_text))

        client = create_llm_client(llm_cfg)
        dm_raw = client.chat(messages)
        dm_struct = parse_dm_text(dm_raw)

        turn_index = _next_turn_index(conn, session_id)
        turn_logs.insert_turn_log(
            conn,
            session_id=session_id,
            turn_index=turn_index,
            player_text=player_text,
            dm_text=dm_raw,
            dice_events_json=json.dumps([], ensure_ascii=False),
        )

        # Persist medium-term memory (story journal) so continuity can span beyond recent N turns.
        mem = (dm_struct.memory_suggestions or "").strip()
        if mem:
            scene_id = _get_session_scene_id(conn, session_id)
            story_journal.insert_story_journal_entry(conn, session_id=session_id, scene_id=scene_id, summary=mem)

        conn.commit()
        return TurnResult(turn_index=turn_index, dm_raw_text=dm_raw, dm=dm_struct, recalled_world=world_preview)
    finally:
        conn.close()


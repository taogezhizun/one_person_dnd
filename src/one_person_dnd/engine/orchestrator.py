from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from one_person_dnd.config import LLMConfig, MemoryConfig
from one_person_dnd.db import get_connection
from one_person_dnd.db.repos import (
    plot_threads,
    sessions,
    state_change_requests,
    story_journal,
    summaries,
    turn_logs,
    world_bible,
)
from one_person_dnd.engine.constants import HISTORY_TURNS_FOR_PROMPT, STORY_JOURNAL_FOR_PROMPT
from one_person_dnd.engine.parser import DMStructuredResponse, parse_dm_text
from one_person_dnd.engine.prompt_builder import RetrievedMemory, build_dm_messages
from one_person_dnd.llm import ChatMessage, create_llm_client

logger = logging.getLogger("one_person_dnd.turn")


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


def build_turn_messages_and_preview(
    conn: sqlite3.Connection,
    *,
    campaign_id: int,
    session_id: int,
    player_text: str,
    state_block: str,
    tags: list[str] | None,
    memory_cfg: MemoryConfig,
) -> tuple[list[ChatMessage], list[dict]]:
    """
    Build full LLM message list for a turn, and return recalled world preview for UI.
    This is shared by both non-streaming and streaming turn implementations.
    """
    world_blocks, world_preview = _fetch_world_bible(conn, campaign_id=campaign_id, tags=tags)

    open_threads = plot_threads.list_open_threads(conn, session_id=session_id, limit=20)
    thread_blocks: list[str] = []
    for t in open_threads:
        title = (t.get("title") or "").strip()
        pri = t.get("priority", 0)
        summary = (t.get("summary") or "").strip()
        next_step = (t.get("next_step") or "").strip()
        tags_text = (t.get("tags") or "").strip()
        parts = [f"[P{pri}] {title}"]
        if tags_text:
            parts.append(f"标签：{tags_text}")
        if summary:
            parts.append(f"进展：{summary}")
        if next_step:
            parts.append(f"下一步：{next_step}")
        thread_blocks.append("\n".join(parts).strip())

    # Memory pyramid (MVP): inject campaign + latest chapter summaries if present.
    campaign_sum = summaries.get_latest_summary(conn, session_id=session_id, level="campaign")
    chapter_sum = summaries.get_latest_summary(conn, session_id=session_id, level="chapter")
    story_blocks = _fetch_story_journal(conn, session_id=session_id, limit=memory_cfg.story_journal_for_prompt)

    if campaign_sum and (campaign_sum.get("summary") or "").strip():
        story_blocks = ["【战役总摘要】\n" + (campaign_sum.get("summary") or "").strip()] + story_blocks
    if chapter_sum and (chapter_sum.get("summary") or "").strip():
        story_blocks = ["【最近章节摘要】\n" + (chapter_sum.get("summary") or "").strip()] + story_blocks

    memory = RetrievedMemory(world_bible_blocks=world_blocks, story_blocks=story_blocks, plot_threads_blocks=thread_blocks)
    messages = build_dm_messages(memory=memory, state_block=state_block)
    messages.extend(_fetch_recent_turn_context(conn, session_id=session_id, limit=memory_cfg.history_turns_for_prompt))
    messages.append(ChatMessage(role="user", content=player_text))
    return messages, world_preview


def persist_turn(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    player_text: str,
    dm_raw: str,
    dm_struct: DMStructuredResponse,
    recalled_world: list[dict],
) -> TurnResult:
    """
    Persist turn logs, story journal, pending change requests, and rollup summaries.
    Caller is responsible for committing.
    """
    turn_index = _next_turn_index(conn, session_id)
    turn_logs.insert_turn_log(
        conn,
        session_id=session_id,
        turn_index=turn_index,
        player_text=player_text,
        dm_text=dm_raw,
        dice_events_json=json.dumps([], ensure_ascii=False),
    )

    if (dm_struct.state_delta_json or "").strip():
        state_change_requests.create_request(
            conn,
            session_id=session_id,
            turn_index=turn_index,
            kind="state_delta",
            delta_json_text=(dm_struct.state_delta_json or "").strip(),
        )
    if (dm_struct.thread_updates_json or "").strip():
        state_change_requests.create_request(
            conn,
            session_id=session_id,
            turn_index=turn_index,
            kind="thread_updates",
            delta_json_text=(dm_struct.thread_updates_json or "").strip(),
        )

    mem = (dm_struct.memory_suggestions or "").strip()
    if mem:
        scene_id = _get_session_scene_id(conn, session_id)
        story_journal.insert_story_journal_entry(
            conn, session_id=session_id, scene_id=scene_id, summary=mem, turn_index=turn_index
        )

    _maybe_rollup_summaries(conn, session_id=session_id, current_turn_index=turn_index)
    return TurnResult(turn_index=turn_index, dm_raw_text=dm_raw, dm=dm_struct, recalled_world=recalled_world)


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
        t0 = time.perf_counter()
        messages, world_preview = build_turn_messages_and_preview(
            conn,
            campaign_id=campaign_id,
            session_id=session_id,
            player_text=player_text,
            state_block=state_block,
            tags=tags,
            memory_cfg=memory_cfg,
        )
        t_prompt = time.perf_counter()
        msg_count = len(messages)
        prompt_chars = sum(len(m.content or "") for m in messages)

        client = create_llm_client(llm_cfg)
        dm_raw = client.chat(messages)
        t_llm = time.perf_counter()
        dm_struct = parse_dm_text(dm_raw)
        t_parse = time.perf_counter()

        result = persist_turn(
            conn,
            session_id=session_id,
            player_text=player_text,
            dm_raw=dm_raw,
            dm_struct=dm_struct,
            recalled_world=world_preview,
        )
        t_persist = time.perf_counter()
        conn.commit()

        logger.info(
            "turn_done non_stream session=%s turn=%s prompt_chars=%s msg_count=%s prompt_ms=%s llm_ms=%s parse_ms=%s persist_ms=%s total_ms=%s",
            session_id,
            result.turn_index,
            prompt_chars,
            msg_count,
            int((t_prompt - t0) * 1000),
            int((t_llm - t_prompt) * 1000),
            int((t_parse - t_llm) * 1000),
            int((t_persist - t_parse) * 1000),
            int((t_persist - t0) * 1000),
        )

        return result
    finally:
        conn.close()


def _truncate(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def _maybe_rollup_summaries(conn: sqlite3.Connection, *, session_id: int, current_turn_index: int) -> None:
    """
    MVP rollup strategy:
    - Keep recent buffer of journal entries unsummarized.
    - When enough unsummarized entries accumulate, create a chapter summary.
    - When enough chapter summaries exist, (re)generate campaign summary.
    """
    RECENT_BUFFER = 12
    CHAPTER_CHUNK = 20
    CHAPTER_MAX_CHARS = 1200
    CAMPAIGN_MAX_CHARS = 1500
    CAMPAIGN_REGEN_CHAPTERS = 3

    progress_end = summaries.get_chapter_rollup_progress(conn, session_id=session_id)
    start_turn = progress_end + 1
    end_limit = max(-1, current_turn_index - RECENT_BUFFER)
    if end_limit < start_turn:
        return

    # Find the next chunk end by scanning available journal entries.
    rows = conn.execute(
        """
        SELECT turn_index, summary
        FROM story_journal_entries
        WHERE session_id = ? AND turn_index IS NOT NULL AND turn_index BETWEEN ? AND ?
        ORDER BY turn_index ASC, id ASC
        """,
        (session_id, start_turn, end_limit),
    ).fetchall()
    if len(rows) < CHAPTER_CHUNK:
        return

    chunk_rows = rows[:CHAPTER_CHUNK]
    chunk_start = int(chunk_rows[0]["turn_index"])
    chunk_end = int(chunk_rows[-1]["turn_index"])
    lines = []
    for r in chunk_rows:
        s = (r["summary"] or "").strip()
        if s:
            lines.append(s)
    chapter_text = _truncate("\n".join(lines), CHAPTER_MAX_CHARS) or "（空）"
    summaries.insert_summary(
        conn,
        session_id=session_id,
        level="chapter",
        start_turn=chunk_start,
        end_turn=chunk_end,
        summary=chapter_text,
    )

    # Regenerate campaign summary from all chapter summaries (deterministic).
    chapters = summaries.list_chapter_summaries(conn, session_id=session_id, limit=200)
    if len(chapters) < CAMPAIGN_REGEN_CHAPTERS:
        return
    merged = "\n\n".join([f"[{c['start_turn']}-{c['end_turn']}]\n{c['summary']}" for c in chapters]).strip()
    campaign_text = _truncate(merged, CAMPAIGN_MAX_CHARS) or "（空）"
    latest_end = max(int(c["end_turn"]) for c in chapters)
    summaries.delete_campaign_summaries(conn, session_id=session_id)
    summaries.insert_summary(
        conn,
        session_id=session_id,
        level="campaign",
        start_turn=0,
        end_turn=latest_end,
        summary=campaign_text,
    )


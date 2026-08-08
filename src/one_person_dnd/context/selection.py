from __future__ import annotations

import sqlite3

from one_person_dnd.db.repos import plot_threads, story_journal, summaries, turn_logs, world_bible
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import ChatMessage


def select_world_blocks(
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


def select_thread_blocks(conn: sqlite3.Connection, *, session_id: int, limit: int = 20) -> list[str]:
    rows = plot_threads.list_open_threads(conn, session_id=session_id, limit=limit)
    blocks: list[str] = []
    for t in rows:
        # The DM protocol requires an existing thread id for updates.  Keep the
        # id in the prompt-facing block so the model can update the canonical
        # row instead of guessing an id or creating a duplicate thread.
        parts = [f"[#{int(t['id'])} · P{t.get('priority', 0)}] {(t.get('title') or '').strip()}"]
        if (t.get("tags") or "").strip():
            parts.append(f"标签：{(t.get('tags') or '').strip()}")
        if (t.get("summary") or "").strip():
            parts.append(f"进展：{(t.get('summary') or '').strip()}")
        if (t.get("next_step") or "").strip():
            parts.append(f"下一步：{(t.get('next_step') or '').strip()}")
        blocks.append("\n".join(parts).strip())
    return blocks


def select_story_blocks(conn: sqlite3.Connection, *, session_id: int, limit: int) -> list[str]:
    rows = story_journal.select_story_journal_for_prompt(conn, session_id=session_id, limit=limit)
    blocks: list[str] = []
    for r in rows[::-1]:
        blocks.append(f"场景：{r['scene_id'] or ''}\n摘要：{r['summary']}\n未解决：{r['open_threads'] or ''}\n要点：{r['key_facts'] or ''}")

    campaign_sum = summaries.get_latest_summary(conn, session_id=session_id, level="campaign")
    chapter_sum = summaries.get_latest_summary(conn, session_id=session_id, level="chapter")
    if campaign_sum and (campaign_sum.get("summary") or "").strip():
        blocks = ["【战役总摘要】\n" + (campaign_sum.get("summary") or "").strip()] + blocks
    if chapter_sum and (chapter_sum.get("summary") or "").strip():
        blocks = ["【最近章节摘要】\n" + (chapter_sum.get("summary") or "").strip()] + blocks
    return blocks


def select_recent_turn_messages(conn: sqlite3.Connection, *, session_id: int, limit: int) -> list[ChatMessage]:
    if limit <= 0:
        return []
    rows = turn_logs.list_recent_turn_pairs(conn, session_id=session_id, limit=limit)
    messages: list[ChatMessage] = []
    for r in rows[::-1]:
        player_text = (r["player_text"] or "").strip()
        dm_text = (r["dm_text"] or "").strip()
        if player_text:
            messages.append(ChatMessage(role="user", content=player_text))
        if dm_text:
            dm = parse_dm_text(dm_text)
            parts = []
            if dm.narration:
                parts.append(dm.narration.strip())
            if dm.choices:
                parts.append("可选行动：\n" + "\n".join([f"- {c}" for c in dm.choices]))
            messages.append(ChatMessage(role="assistant", content="\n\n".join(parts).strip() or dm_text))
    return messages

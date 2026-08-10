from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from one_person_dnd.db.repos import plot_threads, story_journal, summaries, turn_logs, world_bible
from one_person_dnd.engine.parser import parse_dm_text
from one_person_dnd.llm import ChatMessage


@dataclass(frozen=True)
class SelectedContextBlock:
    content: str
    preview_data: dict[str, object]


def select_world_blocks(
    conn: sqlite3.Connection,
    *,
    campaign_id: int,
    tags: list[str] | None,
    limit: int = 10,
) -> tuple[list[SelectedContextBlock], list[dict]]:
    rows = world_bible.select_world_bible_for_prompt(conn, campaign_id=campaign_id, tags=tags, limit=limit)
    blocks: list[SelectedContextBlock] = []
    preview: list[dict] = []
    for r in rows:
        content = f"[{r['type']}] {r['title']}\n标签：{r['tags'] or ''}\n{r['content']}"
        blocks.append(
            SelectedContextBlock(
                content=content,
                preview_data={
                    "type": "world_bible",
                    "entry_type": r["type"],
                    "title": r["title"],
                    "tags": r["tags"] or "",
                    "content": r["content"] or "",
                },
            )
        )
        preview.append({"type": r["type"], "title": r["title"], "tags": r["tags"] or ""})
    return blocks, preview


def select_thread_blocks(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    limit: int = 20,
) -> list[SelectedContextBlock]:
    rows = plot_threads.list_open_threads(conn, session_id=session_id, limit=limit)
    blocks: list[SelectedContextBlock] = []
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
        blocks.append(
            SelectedContextBlock(
                content="\n".join(parts).strip(),
                preview_data={
                    "type": "plot_thread",
                    "id": int(t["id"]),
                    "priority": int(t.get("priority", 0)),
                    "title": (t.get("title") or "").strip(),
                    "tags": (t.get("tags") or "").strip(),
                    "summary": (t.get("summary") or "").strip(),
                    "next_step": (t.get("next_step") or "").strip(),
                },
            )
        )
    return blocks


def select_story_blocks(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    limit: int,
) -> list[SelectedContextBlock]:
    rows = story_journal.select_story_journal_for_prompt(conn, session_id=session_id, limit=limit)
    blocks: list[SelectedContextBlock] = []
    for r in rows[::-1]:
        blocks.append(
            SelectedContextBlock(
                content=(
                    f"场景：{r['scene_id'] or ''}\n摘要：{r['summary']}\n"
                    f"未解决：{r['open_threads'] or ''}\n要点：{r['key_facts'] or ''}"
                ),
                preview_data={
                    "type": "story_memory",
                    "scene": r["scene_id"] or "",
                    "summary": r["summary"] or "",
                    "open_threads": r["open_threads"] or "",
                    "key_facts": r["key_facts"] or "",
                },
            )
        )

    campaign_sum = summaries.get_latest_summary(conn, session_id=session_id, level="campaign")
    chapter_sum = summaries.get_latest_summary(conn, session_id=session_id, level="chapter")
    if campaign_sum and (campaign_sum.get("summary") or "").strip():
        summary = (campaign_sum.get("summary") or "").strip()
        blocks = [
            SelectedContextBlock(
                content="【战役总摘要】\n" + summary,
                preview_data={"type": "story_summary", "level": "campaign", "summary": summary},
            )
        ] + blocks
    if chapter_sum and (chapter_sum.get("summary") or "").strip():
        summary = (chapter_sum.get("summary") or "").strip()
        blocks = [
            SelectedContextBlock(
                content="【最近章节摘要】\n" + summary,
                preview_data={"type": "story_summary", "level": "chapter", "summary": summary},
            )
        ] + blocks
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

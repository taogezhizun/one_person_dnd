from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from one_person_dnd.config import LLMConfig
from one_person_dnd.db import get_connection
from one_person_dnd.engine.parser import DMStructuredResponse, parse_dm_text
from one_person_dnd.engine.prompt_builder import RetrievedMemory, build_dm_messages
from one_person_dnd.llm import OpenAICompatClient


@dataclass(frozen=True)
class TurnResult:
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
    # MVP: tags is comma-separated string; we do simple LIKE matching.
    if not tags:
        rows = conn.execute(
            """
            SELECT type, title, content, tags
            FROM world_bible_entries
            WHERE campaign_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (campaign_id, limit),
        ).fetchall()
    else:
        clauses = []
        params: list[object] = [campaign_id]
        for t in tags:
            clauses.append("tags LIKE ?")
            params.append(f"%{t}%")
        where = " OR ".join(clauses) if clauses else "1=1"
        rows = conn.execute(
            f"""
            SELECT type, title, content, tags
            FROM world_bible_entries
            WHERE campaign_id = ? AND ({where})
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

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
    limit: int = 5,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT scene_id, summary, open_threads, key_facts, created_at
        FROM story_journal_entries
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    blocks: list[str] = []
    for r in rows[::-1]:
        blocks.append(
            f"场景：{r['scene_id'] or ''}\n摘要：{r['summary']}\n未解决：{r['open_threads'] or ''}\n要点：{r['key_facts'] or ''}"
        )
    return blocks


def _next_turn_index(conn: sqlite3.Connection, session_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(turn_index), -1) + 1 AS next_idx FROM turn_logs WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return int(row["next_idx"])


def run_turn(
    *,
    db_path: Path,
    llm_cfg: LLMConfig,
    campaign_id: int,
    session_id: int,
    player_text: str,
    state_block: str,
    tags: list[str] | None = None,
) -> TurnResult:
    conn = get_connection(db_path)
    try:
        world_blocks, world_preview = _fetch_world_bible(conn, campaign_id=campaign_id, tags=tags)
        memory = RetrievedMemory(
            world_bible_blocks=world_blocks,
            story_blocks=_fetch_story_journal(conn, session_id=session_id),
        )
        messages = build_dm_messages(memory=memory, state_block=state_block, player_text=player_text)

        client = OpenAICompatClient(llm_cfg)
        dm_raw = client.chat(messages)
        dm_struct = parse_dm_text(dm_raw)

        turn_index = _next_turn_index(conn, session_id)
        conn.execute(
            """
            INSERT INTO turn_logs(session_id, turn_index, player_text, dm_text, dice_events)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, turn_index, player_text, dm_raw, json.dumps([], ensure_ascii=False)),
        )
        conn.commit()
        return TurnResult(dm_raw_text=dm_raw, dm=dm_struct, recalled_world=world_preview)
    finally:
        conn.close()


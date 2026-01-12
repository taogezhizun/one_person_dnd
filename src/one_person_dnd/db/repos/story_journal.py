from __future__ import annotations

import sqlite3


def list_story_journal_entries(conn: sqlite3.Connection, *, session_id: int, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, scene_id, summary, created_at
        FROM story_journal_entries
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def select_story_journal_for_prompt(conn: sqlite3.Connection, *, session_id: int, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT scene_id, summary, open_threads, key_facts, created_at
        FROM story_journal_entries
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()


def insert_story_journal_entry(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    scene_id: str,
    summary: str,
    open_threads: str = "",
    key_facts: str = "",
) -> int:
    conn.execute(
        """
        INSERT INTO story_journal_entries(session_id, scene_id, summary, open_threads, key_facts)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, scene_id, summary, open_threads, key_facts),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


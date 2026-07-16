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
    turn_index: int | None = None,
) -> int:
    conn.execute(
        """
        INSERT INTO story_journal_entries(session_id, scene_id, summary, open_threads, key_facts, turn_index)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, scene_id, summary, open_threads, key_facts, turn_index),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def list_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> list[dict]:
    """Full-column, deterministically ordered dump used for snapshot narrative capture."""
    rows = conn.execute(
        """
        SELECT id, session_id, scene_id, summary, open_threads, key_facts, turn_index, created_at
        FROM story_journal_entries
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> None:
    """Used only by snapshot restore's narrative replace; caller owns the transaction."""
    conn.execute("DELETE FROM story_journal_entries WHERE session_id = ?", (session_id,))


def bulk_insert(conn: sqlite3.Connection, *, session_id: int, rows: list[dict]) -> None:
    """Re-insert rows captured by list_all_for_session, preserving original ids."""
    for row in rows:
        conn.execute(
            """
            INSERT INTO story_journal_entries(id, session_id, scene_id, summary, open_threads, key_facts, turn_index, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                session_id,
                row.get("scene_id"),
                row["summary"],
                row.get("open_threads"),
                row.get("key_facts"),
                row.get("turn_index"),
                row["created_at"],
            ),
        )

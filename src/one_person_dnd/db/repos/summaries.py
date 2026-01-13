from __future__ import annotations

import sqlite3


def get_latest_summary(conn: sqlite3.Connection, *, session_id: int, level: str) -> dict | None:
    row = conn.execute(
        """
        SELECT id, session_id, level, start_turn, end_turn, summary, created_at
        FROM session_summaries
        WHERE session_id = ? AND level = ?
        ORDER BY end_turn DESC, id DESC
        LIMIT 1
        """,
        (session_id, level),
    ).fetchone()
    return dict(row) if row else None


def list_chapter_summaries(conn: sqlite3.Connection, *, session_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, start_turn, end_turn, summary, created_at
        FROM session_summaries
        WHERE session_id = ? AND level = 'chapter'
        ORDER BY start_turn ASC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_summary(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    level: str,
    start_turn: int,
    end_turn: int,
    summary: str,
) -> int:
    conn.execute(
        """
        INSERT INTO session_summaries(session_id, level, start_turn, end_turn, summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, level, start_turn, end_turn, summary),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def delete_campaign_summaries(conn: sqlite3.Connection, *, session_id: int) -> None:
    conn.execute("DELETE FROM session_summaries WHERE session_id = ? AND level = 'campaign'", (session_id,))


def get_chapter_rollup_progress(conn: sqlite3.Connection, *, session_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(end_turn), -1) AS end_turn FROM session_summaries WHERE session_id = ? AND level = 'chapter'",
        (session_id,),
    ).fetchone()
    return int(row["end_turn"])


def select_journal_range(conn: sqlite3.Connection, *, session_id: int, start_turn: int, end_turn: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT turn_index, scene_id, summary
        FROM story_journal_entries
        WHERE session_id = ? AND turn_index IS NOT NULL AND turn_index BETWEEN ? AND ?
        ORDER BY turn_index ASC, id ASC
        """,
        (session_id, start_turn, end_turn),
    ).fetchall()


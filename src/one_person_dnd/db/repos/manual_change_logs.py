from __future__ import annotations

import sqlite3


def insert_log(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    actor: str,
    change_type: str,
    detail_json_text: str,
) -> int:
    conn.execute(
        """
        INSERT INTO manual_change_logs(session_id, actor, change_type, detail_json_text)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, actor, change_type, detail_json_text),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def list_recent(conn: sqlite3.Connection, *, session_id: int, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, session_id, actor, change_type, detail_json_text, created_at
        FROM manual_change_logs
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]

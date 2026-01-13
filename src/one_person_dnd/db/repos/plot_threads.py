from __future__ import annotations

import sqlite3


def list_threads(conn: sqlite3.Connection, *, session_id: int, status: str | None = None, limit: int = 200) -> list[dict]:
    if status:
        rows = conn.execute(
            """
            SELECT id, title, status, priority, summary, next_step, tags, updated_at, created_at
            FROM plot_threads
            WHERE session_id = ? AND status = ?
            ORDER BY priority DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, title, status, priority, summary, next_step, tags, updated_at, created_at
            FROM plot_threads
            WHERE session_id = ?
            ORDER BY status ASC, priority DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_open_threads(conn: sqlite3.Connection, *, session_id: int, limit: int = 20) -> list[dict]:
    return list_threads(conn, session_id=session_id, status="open", limit=limit)


def create_thread(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    title: str,
    priority: int = 0,
    summary: str = "",
    next_step: str = "",
    tags: str = "",
) -> int:
    conn.execute(
        """
        INSERT INTO plot_threads(session_id, title, status, priority, summary, next_step, tags)
        VALUES (?, ?, 'open', ?, ?, ?, ?)
        """,
        (session_id, title, priority, summary, next_step, tags),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def update_thread(
    conn: sqlite3.Connection,
    *,
    thread_id: int,
    session_id: int,
    title: str,
    priority: int,
    summary: str,
    next_step: str,
    tags: str,
) -> None:
    conn.execute(
        """
        UPDATE plot_threads
        SET title = ?, priority = ?, summary = ?, next_step = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND session_id = ?
        """,
        (title, priority, summary, next_step, tags, thread_id, session_id),
    )


def set_status(conn: sqlite3.Connection, *, thread_id: int, session_id: int, status: str) -> None:
    conn.execute(
        """
        UPDATE plot_threads
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND session_id = ?
        """,
        (status, thread_id, session_id),
    )


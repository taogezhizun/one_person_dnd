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


def get_thread(conn: sqlite3.Connection, *, session_id: int, thread_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT id, title, status, priority, summary, next_step, tags, updated_at, created_at
        FROM plot_threads
        WHERE id = ? AND session_id = ?
        LIMIT 1
        """,
        (thread_id, session_id),
    ).fetchone()
    return dict(row) if row else None


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


def list_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> list[dict]:
    """Full-column, deterministically ordered dump used for snapshot narrative capture."""
    rows = conn.execute(
        """
        SELECT id, session_id, title, status, priority, summary, next_step, tags, updated_at, created_at
        FROM plot_threads
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> None:
    """Used only by snapshot restore's narrative replace; caller owns the transaction."""
    conn.execute("DELETE FROM plot_threads WHERE session_id = ?", (session_id,))


def bulk_insert(conn: sqlite3.Connection, *, session_id: int, rows: list[dict]) -> None:
    """Re-insert rows captured by list_all_for_session, preserving original ids and
    the in-place update history (status/summary/next_step) as of capture time."""
    for row in rows:
        conn.execute(
            """
            INSERT INTO plot_threads(id, session_id, title, status, priority, summary, next_step, tags, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                session_id,
                row["title"],
                row["status"],
                row["priority"],
                row.get("summary"),
                row.get("next_step"),
                row.get("tags"),
                row["updated_at"],
                row["created_at"],
            ),
        )

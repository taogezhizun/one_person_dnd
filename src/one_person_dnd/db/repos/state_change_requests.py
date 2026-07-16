from __future__ import annotations

import sqlite3


def create_request(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    turn_index: int,
    kind: str,
    delta_json_text: str,
) -> int:
    conn.execute(
        """
        INSERT INTO state_change_requests(session_id, turn_index, kind, delta_json_text, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (session_id, turn_index, kind, delta_json_text),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def list_pending(conn: sqlite3.Connection, *, session_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, session_id, turn_index, kind, delta_json_text, status, error_text, created_at
        FROM state_change_requests
        WHERE session_id = ? AND status = 'pending'
        ORDER BY id ASC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def set_status(
    conn: sqlite3.Connection,
    *,
    request_id: int,
    session_id: int,
    status: str,
    error_text: str = "",
) -> None:
    conn.execute(
        """
        UPDATE state_change_requests
        SET status = ?, error_text = ?
        WHERE id = ? AND session_id = ?
        """,
        (status, error_text or None, request_id, session_id),
    )


def get_request(conn: sqlite3.Connection, *, request_id: int, session_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT id, session_id, turn_index, kind, delta_json_text, status, error_text, created_at
        FROM state_change_requests
        WHERE id = ? AND session_id = ?
        LIMIT 1
        """,
        (request_id, session_id),
    ).fetchone()
    return dict(row) if row else None


def delete_all_pending_for_session(conn: sqlite3.Connection, *, session_id: int) -> None:
    """
    Used only by snapshot restore's narrative replace: pending requests reference
    turn_index / thread state that may no longer exist after the rewind, so they
    are discarded rather than replayed. Applied/rejected requests are left as an
    audit trail; caller owns the transaction.
    """
    conn.execute(
        "DELETE FROM state_change_requests WHERE session_id = ? AND status = 'pending'",
        (session_id,),
    )

from __future__ import annotations

import sqlite3


_SELECT_COLUMNS = """
    id, session_id, attempt_id, fingerprint, record_json, turn_index,
    created_at, completed_at, claim_token, claim_expires_at
"""


def create(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
    fingerprint: str,
    record_json: str,
    turn_index: int | None = None,
) -> int:
    """
    Insert one adjudication attempt without committing the connection.

    turn_index is intentionally optional: callers can commit the deterministic
    result before invoking the LLM, then bind it to a persisted turn with
    mark_completed(). Duplicate (session_id, attempt_id) keys raise SQLite's
    IntegrityError so the upper module can decide whether to replay or reject.
    """
    cursor = conn.execute(
        """
        INSERT INTO adjudication_records(
          session_id, attempt_id, fingerprint, record_json, turn_index, completed_at
        )
        VALUES (?, ?, ?, ?, ?, CASE WHEN ? IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END)
        """,
        (session_id, attempt_id, fingerprint, record_json, turn_index, turn_index),
    )
    return int(cursor.lastrowid)


def get_by_attempt(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
) -> dict | None:
    row = conn.execute(
        f"""
        SELECT {_SELECT_COLUMNS}
        FROM adjudication_records
        WHERE session_id = ? AND attempt_id = ?
        LIMIT 1
        """,
        (session_id, attempt_id),
    ).fetchone()
    return dict(row) if row else None


def get_by_session_turn(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    turn_index: int,
) -> dict | None:
    row = conn.execute(
        f"""
        SELECT {_SELECT_COLUMNS}
        FROM adjudication_records
        WHERE session_id = ? AND turn_index = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (session_id, turn_index),
    ).fetchone()
    return dict(row) if row else None


def mark_completed(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
    turn_index: int,
) -> bool:
    """
    Bind an attempt to its final turn.

    Repeating the same binding is allowed. A different existing turn_index is
    not overwritten and returns False, preserving replay identity.
    """
    cursor = conn.execute(
        """
        UPDATE adjudication_records
        SET turn_index = ?,
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            claim_token = NULL,
            claim_expires_at = NULL
        WHERE session_id = ?
          AND attempt_id = ?
          AND (turn_index IS NULL OR turn_index = ?)
        """,
        (turn_index, session_id, attempt_id, turn_index),
    )
    return cursor.rowcount > 0


def try_claim(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
    claim_token: str,
    lease_seconds: int,
) -> bool:
    """Atomically acquire or renew the generation lease for an unfinished attempt."""
    token = claim_token.strip()
    if not token:
        raise ValueError("claim_token must not be blank")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    cursor = conn.execute(
        """
        UPDATE adjudication_records
        SET claim_token = ?, claim_expires_at = unixepoch() + ?
        WHERE session_id = ?
          AND attempt_id = ?
          AND turn_index IS NULL
          AND (
            claim_token IS NULL
            OR claim_expires_at IS NULL
            OR claim_expires_at <= unixepoch()
            OR claim_token = ?
          )
        """,
        (token, lease_seconds, session_id, attempt_id, token),
    )
    return cursor.rowcount > 0


def renew_claim(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
    claim_token: str,
    lease_seconds: int,
) -> bool:
    """Extend a lease only while the caller still owns the unfinished attempt."""
    token = claim_token.strip()
    if not token:
        raise ValueError("claim_token must not be blank")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    cursor = conn.execute(
        """
        UPDATE adjudication_records
        SET claim_expires_at = unixepoch() + ?
        WHERE session_id = ?
          AND attempt_id = ?
          AND turn_index IS NULL
          AND claim_token = ?
        """,
        (lease_seconds, session_id, attempt_id, token),
    )
    return cursor.rowcount > 0


def release_claim(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
    claim_token: str,
) -> bool:
    """Release an unfinished attempt only when the caller still owns its lease."""
    token = claim_token.strip()
    if not token:
        raise ValueError("claim_token must not be blank")
    cursor = conn.execute(
        """
        UPDATE adjudication_records
        SET claim_token = NULL, claim_expires_at = NULL
        WHERE session_id = ?
          AND attempt_id = ?
          AND turn_index IS NULL
          AND claim_token = ?
        """,
        (session_id, attempt_id, token),
    )
    return cursor.rowcount > 0


def delete_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> None:
    """Delete adjudication attempts for one session; caller owns the transaction."""
    conn.execute("DELETE FROM adjudication_records WHERE session_id = ?", (session_id,))

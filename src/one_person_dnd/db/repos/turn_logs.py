from __future__ import annotations

import sqlite3


def get_next_turn_index(conn: sqlite3.Connection, session_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(turn_index), -1) + 1 AS next_idx FROM turn_logs WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return int(row["next_idx"])


def list_turn_logs(conn: sqlite3.Connection, *, session_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT turn_index, player_text, dm_text, dice_events,
               attempt_id, adjudication_json, created_at
        FROM turn_logs
        WHERE session_id = ?
        ORDER BY turn_index DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_recent_turn_pairs(conn: sqlite3.Connection, *, session_id: int, limit: int) -> list[sqlite3.Row]:
    if limit <= 0:
        return []
    return conn.execute(
        """
        SELECT player_text, dm_text
        FROM turn_logs
        WHERE session_id = ?
        ORDER BY turn_index DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()


def insert_turn_log(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    turn_index: int,
    player_text: str,
    dm_text: str,
    dice_events_json: str,
    attempt_id: str | None = None,
    adjudication_json: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO turn_logs(
          session_id, turn_index, player_text, dm_text, dice_events,
          attempt_id, adjudication_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            turn_index,
            player_text,
            dm_text,
            dice_events_json,
            attempt_id,
            adjudication_json,
        ),
    )


def get_by_session_turn(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    turn_index: int,
) -> dict | None:
    row = conn.execute(
        """
        SELECT id, session_id, turn_index, player_text, dm_text, dice_events,
               attempt_id, adjudication_json, created_at
        FROM turn_logs
        WHERE session_id = ? AND turn_index = ?
        LIMIT 1
        """,
        (session_id, turn_index),
    ).fetchone()
    return dict(row) if row else None


def get_by_attempt(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    attempt_id: str,
) -> dict | None:
    row = conn.execute(
        """
        SELECT id, session_id, turn_index, player_text, dm_text, dice_events,
               attempt_id, adjudication_json, created_at
        FROM turn_logs
        WHERE session_id = ? AND attempt_id = ?
        LIMIT 1
        """,
        (session_id, attempt_id),
    ).fetchone()
    return dict(row) if row else None


def list_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> list[dict]:
    """Full-column, deterministically ordered dump used for snapshot narrative capture."""
    rows = conn.execute(
        """
        SELECT id, session_id, turn_index, player_text, dm_text, dice_events,
               attempt_id, adjudication_json, created_at
        FROM turn_logs
        WHERE session_id = ?
        ORDER BY turn_index ASC, id ASC
        """,
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_all_for_session(conn: sqlite3.Connection, *, session_id: int) -> None:
    """Used only by snapshot restore's narrative replace; caller owns the transaction."""
    conn.execute("DELETE FROM turn_logs WHERE session_id = ?", (session_id,))


def bulk_insert(conn: sqlite3.Connection, *, session_id: int, rows: list[dict]) -> None:
    """Re-insert rows captured by list_all_for_session, preserving original ids/turn_index."""
    for row in rows:
        conn.execute(
            """
            INSERT INTO turn_logs(
              id, session_id, turn_index, player_text, dm_text, dice_events,
              attempt_id, adjudication_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                session_id,
                row["turn_index"],
                row["player_text"],
                row["dm_text"],
                row.get("dice_events"),
                row.get("attempt_id"),
                row.get("adjudication_json"),
                row["created_at"],
            ),
        )

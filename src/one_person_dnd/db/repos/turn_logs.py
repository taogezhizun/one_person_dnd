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
        SELECT turn_index, player_text, dm_text, created_at
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
) -> None:
    conn.execute(
        """
        INSERT INTO turn_logs(session_id, turn_index, player_text, dm_text, dice_events)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, turn_index, player_text, dm_text, dice_events_json),
    )


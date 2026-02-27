from __future__ import annotations

import sqlite3


def get_cheat(conn: sqlite3.Connection, *, session_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT session_id, enabled, cheat_prompt, updated_at
        FROM session_cheats
        WHERE session_id = ?
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def upsert_cheat(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    enabled: bool,
    cheat_prompt: str,
) -> None:
    conn.execute(
        """
        INSERT INTO session_cheats(session_id, enabled, cheat_prompt, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET
          enabled = excluded.enabled,
          cheat_prompt = excluded.cheat_prompt,
          updated_at = CURRENT_TIMESTAMP
        """,
        (session_id, 1 if enabled else 0, cheat_prompt),
    )


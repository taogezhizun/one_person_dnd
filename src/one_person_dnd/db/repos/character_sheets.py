from __future__ import annotations

import sqlite3


def get_character_sheet(conn: sqlite3.Connection, *, session_id: int) -> str:
    row = conn.execute("SELECT json_text FROM character_sheets WHERE session_id = ? LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return ""
    return row["json_text"] or ""


def upsert_character_sheet(conn: sqlite3.Connection, *, session_id: int, json_text: str) -> None:
    conn.execute(
        """
        INSERT INTO character_sheets(session_id, json_text, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET
          json_text = excluded.json_text,
          updated_at = CURRENT_TIMESTAMP
        """,
        (session_id, json_text),
    )


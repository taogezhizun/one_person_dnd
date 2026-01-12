from __future__ import annotations

import sqlite3


def get_first_session_id(conn: sqlite3.Connection, campaign_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM sessions WHERE campaign_id = ? ORDER BY id LIMIT 1",
        (campaign_id,),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def session_exists_under_campaign(conn: sqlite3.Connection, *, session_id: int, campaign_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 AS ok FROM sessions WHERE id = ? AND campaign_id = ? LIMIT 1",
        (session_id, campaign_id),
    ).fetchone()
    return row is not None


def get_session_title(conn: sqlite3.Connection, session_id: int) -> str | None:
    row = conn.execute("SELECT title FROM sessions WHERE id = ? LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return None
    return row["title"]


def get_session_scene_id(conn: sqlite3.Connection, session_id: int) -> str:
    row = conn.execute("SELECT current_scene FROM sessions WHERE id = ? LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return ""
    return (row["current_scene"] or "").strip()


def get_session_sidebar(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT title, current_scene, session_state, pinned_world_notes FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()


def list_sessions(conn: sqlite3.Connection, campaign_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, current_scene, created_at FROM sessions WHERE campaign_id = ? ORDER BY id DESC",
        (campaign_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_session(conn: sqlite3.Connection, *, campaign_id: int, title: str, current_scene: str) -> int:
    conn.execute(
        "INSERT INTO sessions(campaign_id, title, current_scene) VALUES (?, ?, ?)",
        (campaign_id, title, current_scene),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def get_session_campaign_id(conn: sqlite3.Connection, session_id: int) -> int | None:
    row = conn.execute("SELECT campaign_id FROM sessions WHERE id = ? LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return None
    return int(row["campaign_id"])


def update_session_sidebar(
    conn: sqlite3.Connection,
    *,
    campaign_id: int,
    session_id: int,
    current_scene: str,
    session_state: str,
    pinned_world_notes: str,
) -> None:
    conn.execute(
        """
        UPDATE sessions
        SET current_scene = ?, session_state = ?, pinned_world_notes = ?
        WHERE id = ? AND campaign_id = ?
        """,
        (current_scene, session_state, pinned_world_notes, session_id, campaign_id),
    )


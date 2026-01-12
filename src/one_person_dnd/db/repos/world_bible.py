from __future__ import annotations

import sqlite3


def list_world_bible_entries(conn: sqlite3.Connection, *, campaign_id: int, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, type, title, tags, updated_at
        FROM world_bible_entries
        WHERE campaign_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (campaign_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def select_world_bible_for_prompt(
    conn: sqlite3.Connection,
    *,
    campaign_id: int,
    tags: list[str] | None,
    limit: int = 10,
) -> list[sqlite3.Row]:
    if not tags:
        return conn.execute(
            """
            SELECT type, title, content, tags
            FROM world_bible_entries
            WHERE campaign_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (campaign_id, limit),
        ).fetchall()

    clauses: list[str] = []
    params: list[object] = [campaign_id]
    for t in tags:
        clauses.append("tags LIKE ?")
        params.append(f"%{t}%")
    where = " OR ".join(clauses) if clauses else "1=1"

    return conn.execute(
        f"""
        SELECT type, title, content, tags
        FROM world_bible_entries
        WHERE campaign_id = ? AND ({where})
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()


def insert_world_bible_entry(
    conn: sqlite3.Connection,
    *,
    campaign_id: int,
    type: str,
    title: str,
    content: str,
    tags: str,
    related_locations: str = "",
    related_npcs: str = "",
) -> int:
    conn.execute(
        """
        INSERT INTO world_bible_entries(
          campaign_id, type, title, content, tags, related_locations, related_npcs
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (campaign_id, type, title, content, tags, related_locations, related_npcs),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


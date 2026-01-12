from __future__ import annotations

import sqlite3


def get_first_campaign_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM campaigns ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    return int(row["id"])


def campaign_exists(conn: sqlite3.Connection, campaign_id: int) -> bool:
    row = conn.execute("SELECT 1 AS ok FROM campaigns WHERE id = ? LIMIT 1", (campaign_id,)).fetchone()
    return row is not None


def get_campaign_name(conn: sqlite3.Connection, campaign_id: int) -> str | None:
    row = conn.execute("SELECT name FROM campaigns WHERE id = ? LIMIT 1", (campaign_id,)).fetchone()
    if row is None:
        return None
    return row["name"]


def list_campaigns(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, name, created_at FROM campaigns ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def create_campaign(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT INTO campaigns(name) VALUES (?)", (name,))
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


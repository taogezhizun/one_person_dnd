from __future__ import annotations

import sqlite3


def list_profiles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, name, provider, base_url, api_key, model, timeout_seconds, created_at, updated_at
        FROM llm_profiles
        ORDER BY id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_profile(conn: sqlite3.Connection, profile_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT id, name, provider, base_url, api_key, model, timeout_seconds, created_at, updated_at
        FROM llm_profiles
        WHERE id = ?
        LIMIT 1
        """,
        (profile_id,),
    ).fetchone()
    return dict(row) if row else None


def get_profile_by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute(
        """
        SELECT id, name, provider, base_url, api_key, model, timeout_seconds, created_at, updated_at
        FROM llm_profiles
        WHERE name = ?
        LIMIT 1
        """,
        (name,),
    ).fetchone()
    return dict(row) if row else None


def create_profile(
    conn: sqlite3.Connection,
    *,
    name: str,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> int:
    conn.execute(
        """
        INSERT INTO llm_profiles(name, provider, base_url, api_key, model, timeout_seconds)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, provider, base_url, api_key, model, float(timeout_seconds)),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def update_profile(
    conn: sqlite3.Connection,
    *,
    profile_id: int,
    name: str,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> None:
    conn.execute(
        """
        UPDATE llm_profiles
        SET name = ?, provider = ?, base_url = ?, api_key = ?, model = ?, timeout_seconds = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (name, provider, base_url, api_key, model, float(timeout_seconds), profile_id),
    )


def delete_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    conn.execute("DELETE FROM llm_profiles WHERE id = ?", (profile_id,))


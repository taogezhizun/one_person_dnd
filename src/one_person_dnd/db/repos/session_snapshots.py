from __future__ import annotations

import sqlite3


def create_snapshot(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    snapshot_name: str,
    turn_index: int,
    current_scene: str,
    session_state: str,
    pinned_world_notes: str,
    character_sheet_json: str,
    narrative_json: str | None = None,
) -> int:
    """
    narrative_json is the captured turn_logs/story_journal_entries/plot_threads/
    session_summaries payload for this session at snapshot time (see
    web.routes.saves._capture_narrative_json). It is optional/nullable so any
    caller that only needs the legacy state-only snapshot still works.
    """
    conn.execute(
        """
        INSERT INTO session_snapshots(
          session_id, snapshot_name, turn_index,
          current_scene, session_state, pinned_world_notes, character_sheet_json,
          narrative_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            snapshot_name,
            int(turn_index),
            current_scene,
            session_state,
            pinned_world_notes,
            character_sheet_json,
            narrative_json,
        ),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


def list_snapshots(conn: sqlite3.Connection, *, session_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, session_id, snapshot_name, turn_index, created_at
        FROM session_snapshots
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def get_snapshot(conn: sqlite3.Connection, *, snapshot_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT id, session_id, snapshot_name, turn_index, current_scene, session_state,
               pinned_world_notes, character_sheet_json, narrative_json, created_at
        FROM session_snapshots
        WHERE id = ?
        LIMIT 1
        """,
        (int(snapshot_id),),
    ).fetchone()
    return dict(row) if row else None

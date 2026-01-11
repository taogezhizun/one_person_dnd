from __future__ import annotations

import sqlite3
from pathlib import Path

from one_person_dnd.db.conn import get_connection


SCHEMA_VERSION = 2


def _apply_schema_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          last_opened_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          campaign_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          current_scene TEXT,
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_campaign_id ON sessions(campaign_id);

        CREATE TABLE IF NOT EXISTS world_bible_entries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          campaign_id INTEGER NOT NULL,
          type TEXT NOT NULL,
          title TEXT NOT NULL,
          content TEXT NOT NULL,
          tags TEXT,
          related_locations TEXT,
          related_npcs TEXT,
          updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_world_bible_campaign_id ON world_bible_entries(campaign_id);
        CREATE INDEX IF NOT EXISTS idx_world_bible_type ON world_bible_entries(type);

        CREATE TABLE IF NOT EXISTS story_journal_entries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          scene_id TEXT,
          summary TEXT NOT NULL,
          open_threads TEXT,
          key_facts TEXT,
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_story_journal_session_id ON story_journal_entries(session_id);

        CREATE TABLE IF NOT EXISTS turn_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          turn_index INTEGER NOT NULL,
          player_text TEXT NOT NULL,
          dm_text TEXT NOT NULL,
          dice_events TEXT,
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_turn_logs_unique_turn ON turn_logs(session_id, turn_index);
        """
    )


def _apply_schema_v2(conn: sqlite3.Connection) -> None:
    """
    Add session-level persistent info blocks for the game sidebar.
    """
    # SQLite doesn't support IF NOT EXISTS for ADD COLUMN, so we check table_info first.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions);").fetchall()}
    if "session_state" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN session_state TEXT;")
    if "pinned_world_notes" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN pinned_world_notes TEXT;")


def init_db(db_path: Path) -> None:
    """
    Initialize (and lightly migrate) the SQLite database using PRAGMA user_version.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        current_version = int(conn.execute("PRAGMA user_version;").fetchone()[0])
        if current_version == 0:
            _apply_schema_v1(conn)
            _apply_schema_v2(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
            conn.commit()
        elif current_version == 1:
            _apply_schema_v2(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
            conn.commit()
        elif current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"DB schema version {current_version} is newer than app supports ({SCHEMA_VERSION})."
            )
    finally:
        conn.close()


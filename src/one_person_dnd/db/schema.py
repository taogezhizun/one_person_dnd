from __future__ import annotations

import sqlite3
from pathlib import Path

from one_person_dnd.db.conn import get_connection


SCHEMA_VERSION = 5


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


def _apply_schema_v3(conn: sqlite3.Connection) -> None:
    """
    Plot threads (Quest/Thread Tracker) for long-term continuity.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS plot_threads (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', -- open | closed
          priority INTEGER NOT NULL DEFAULT 0,
          summary TEXT,
          next_step TEXT,
          tags TEXT,
          updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_plot_threads_session_id ON plot_threads(session_id);
        CREATE INDEX IF NOT EXISTS idx_plot_threads_status ON plot_threads(status);
        """
    )


def _apply_schema_v4(conn: sqlite3.Connection) -> None:
    """
    Memory pyramid: turn-indexed journal + session-level summaries.
    """
    # story_journal_entries.turn_index (optional but enables rollup ranges)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(story_journal_entries);").fetchall()}
    if "turn_index" not in cols:
        conn.execute("ALTER TABLE story_journal_entries ADD COLUMN turn_index INTEGER;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_story_journal_turn_index ON story_journal_entries(session_id, turn_index);")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS session_summaries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          level TEXT NOT NULL, -- chapter | campaign
          start_turn INTEGER NOT NULL,
          end_turn INTEGER NOT NULL,
          summary TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_session_summaries_session_level ON session_summaries(session_id, level);
        """
    )


def _apply_schema_v5(conn: sqlite3.Connection) -> None:
    """
    Structured character sheet + change requests workflow.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_sheets (
          session_id INTEGER PRIMARY KEY,
          json_text TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS state_change_requests (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          turn_index INTEGER NOT NULL,
          kind TEXT NOT NULL DEFAULT 'state_delta', -- state_delta | thread_updates
          delta_json_text TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', -- pending | applied | rejected
          error_text TEXT,
          created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
          FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_state_change_requests_session_status ON state_change_requests(session_id, status);
        """
    )

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
            current_version = 1

        # Sequential migrations
        if current_version < 2:
            _apply_schema_v2(conn)
            current_version = 2
        if current_version < 3:
            _apply_schema_v3(conn)
            current_version = 3
        if current_version < 4:
            _apply_schema_v4(conn)
            current_version = 4
        if current_version < 5:
            _apply_schema_v5(conn)
            current_version = 5

        conn.execute(f"PRAGMA user_version = {current_version};")
        conn.commit()
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"DB schema version {current_version} is newer than app supports ({SCHEMA_VERSION})."
            )
    finally:
        conn.close()


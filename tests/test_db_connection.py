from pathlib import Path
import tempfile
import unittest

from one_person_dnd.db.conn import get_connection


class TestDatabaseConnection(unittest.TestCase):
    def test_connection_defaults_support_local_concurrent_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = get_connection(Path(tmp) / "game.sqlite3")
            try:
                busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
                foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
                journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(busy_timeout, 5000)
        self.assertEqual(foreign_keys, 1)
        self.assertEqual(journal_mode, "wal")

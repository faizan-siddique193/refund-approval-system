"""
Tests for the SQLite database layer (database.py).

Covers:
- Schema creation (idempotency)
- Connection settings (WAL mode, foreign keys, row_factory)
"""

from __future__ import annotations

import sqlite3

from refund_approval_system.db.database import get_connection, init_db


class TestInitDb:
    def test_init_creates_tables(self, tmp_path):
        db = str(tmp_path / "test.db")
        init_db(db)
        with get_connection(db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "approvals" in tables
        assert "audit_events" in tables
        assert "refund_states" in tables

    def test_init_is_idempotent(self, tmp_path):
        """Calling init_db twice must not raise."""
        db = str(tmp_path / "idem.db")
        init_db(db)
        init_db(db)  # second call should be a no-op

    def test_row_factory_returns_row_objects(self, tmp_path):
        db = str(tmp_path / "row.db")
        init_db(db)
        with get_connection(db) as conn:
            conn.execute(
                "INSERT INTO audit_events (refund_id, event_type, details, created_at) "
                "VALUES (?, ?, ?, ?)",
                ("REF-X", "test", "detail", "2024-01-01T00:00:00.000000"),
            )
            row = conn.execute("SELECT * FROM audit_events").fetchone()
        # sqlite3.Row supports both index and key access
        assert row["refund_id"] == "REF-X"
        assert row["event_type"] == "test"

    def test_wal_journal_mode(self, tmp_path):
        db = str(tmp_path / "wal.db")
        init_db(db)
        with get_connection(db) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, tmp_path):
        db = str(tmp_path / "fk.db")
        init_db(db)
        with get_connection(db) as conn:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

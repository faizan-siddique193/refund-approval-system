from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Default path -- overridden by settings or tests
DEFAULT_DB_PATH = "refund_approval.db"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    Open (or create) the SQLite database and return a connection.

    Row factory is set so rows behave like dicts, which makes code
    downstream much more readable.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # safer for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Create all required tables if they do not already exist.

    This is idempotent -- safe to call on every application start.
    """
    logger.info("Initialising database at %s", db_path)
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id   TEXT PRIMARY KEY,
                refund_id     TEXT NOT NULL,
                order_id      TEXT NOT NULL,
                amount        REAL NOT NULL,
                required_level TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                reviewer_id   TEXT,
                created_at    TEXT NOT NULL,
                decided_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                refund_id   TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                details     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refund_states (
                refund_id       TEXT PRIMARY KEY,
                status          TEXT NOT NULL,
                amount          REAL NOT NULL,
                action          TEXT,
                rationale       TEXT,
                approval_id     TEXT,
                approval_level  TEXT,
                risk_flags      TEXT,
                transaction_id  TEXT,
                error           TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            """
        )
    logger.info("Database initialised successfully")

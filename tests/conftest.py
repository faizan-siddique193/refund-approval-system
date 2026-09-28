"""
Shared pytest fixtures for Phase 1 tests.

Uses an in-memory SQLite database so tests are fully isolated and fast.
"""

from __future__ import annotations

import pytest

from refund_approval_system.db.database import init_db


# --------------------------------------------------------------------------- #
# DB fixture                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def db_path(tmp_path) -> str:
    """
    Create a fresh, temporary SQLite database for each test.

    Using tmp_path (pytest's built-in temp-dir fixture) guarantees that
    every test gets an isolated, empty database and that the file is
    cleaned up after the test session ends.
    """
    path = str(tmp_path / "test_refund.db")
    init_db(path)
    return path

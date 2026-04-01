import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def db_conn(db_path: Path) -> sqlite3.Connection:
    from app.db import init_db

    conn = init_db(db_path)
    yield conn
    conn.close()

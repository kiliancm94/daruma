import sqlite3


def test_init_db_creates_tables(db_conn: sqlite3.Connection):
    cursor = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "tasks" in tables
    assert "runs" in tables


def test_tasks_table_has_expected_columns(db_conn: sqlite3.Connection):
    cursor = db_conn.execute("PRAGMA table_info(tasks)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {
        "id", "name", "prompt", "cron_expression",
        "allowed_tools", "enabled", "created_at", "updated_at",
    }


def test_runs_table_has_expected_columns(db_conn: sqlite3.Connection):
    cursor = db_conn.execute("PRAGMA table_info(runs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {
        "id", "task_id", "trigger", "status", "started_at",
        "finished_at", "duration_ms", "stdout", "stderr", "exit_code",
        "activity",
    }

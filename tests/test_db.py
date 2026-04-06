from sqlalchemy import inspect


def test_init_db_creates_tables(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "tasks" in tables
    assert "runs" in tables


def test_tasks_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("tasks")}
    assert columns == {
        "id",
        "name",
        "prompt",
        "cron_expression",
        "allowed_tools",
        "model",
        "enabled",
        "output_format",
        "output_destination",
        "created_at",
        "updated_at",
    }


def test_runs_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("runs")}
    assert columns == {
        "id",
        "task_id",
        "trigger",
        "status",
        "started_at",
        "finished_at",
        "duration_ms",
        "stdout",
        "stderr",
        "exit_code",
        "activity",
    }


def test_skills_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("skills")}
    assert columns == {
        "id",
        "name",
        "description",
        "content",
        "source",
        "created_at",
        "updated_at",
    }


def test_task_skills_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("task_skills")}
    assert columns == {"task_id", "skill_id"}

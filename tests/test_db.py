from sqlalchemy import inspect


def test_init_db_creates_tables(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "tasks" in tables
    assert "runs" in tables
    assert "pipelines" in tables
    assert "pipeline_steps" in tables
    assert "pipeline_runs" in tables


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
        "env_vars",
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
        "pipeline_run_id",
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


def test_pipelines_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("pipelines")}
    assert columns == {
        "id",
        "name",
        "description",
        "enabled",
        "created_at",
        "updated_at",
    }


def test_pipeline_steps_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("pipeline_steps")}
    assert columns == {
        "id",
        "pipeline_id",
        "task_id",
        "step_order",
    }


def test_pipeline_runs_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("pipeline_runs")}
    assert columns == {
        "id",
        "pipeline_id",
        "status",
        "trigger",
        "current_step",
        "started_at",
        "finished_at",
        "duration_ms",
    }


def test_runs_table_includes_pipeline_run_id(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("runs")}
    assert "pipeline_run_id" in columns

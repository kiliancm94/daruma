import pytest
from app.crud import TaskRepo, RunRepo


class TestTaskRepo:
    def test_create_and_get(self, db_session):
        repo = TaskRepo(db_session)
        task = repo.create(
            name="Test Task",
            prompt="Do something",
            cron_expression="0 * * * *",
            allowed_tools="bash,read",
            enabled=True,
        )
        assert task.name == "Test Task"
        assert task.prompt == "Do something"
        assert task.cron_expression == "0 * * * *"
        assert task.enabled is True

        fetched = repo.get(task.id)
        assert fetched is not None
        assert fetched.id == task.id

    def test_list_tasks(self, db_session):
        repo = TaskRepo(db_session)
        repo.create(name="A", prompt="p1")
        repo.create(name="B", prompt="p2")
        tasks = repo.list()
        assert len(tasks) == 2

    def test_update_task(self, db_session):
        repo = TaskRepo(db_session)
        task = repo.create(name="Old", prompt="p")
        updated = repo.update(task.id, name="New", enabled=False)
        assert updated.name == "New"
        assert updated.enabled is False

    def test_delete_task(self, db_session):
        repo = TaskRepo(db_session)
        task = repo.create(name="Doomed", prompt="p")
        assert repo.delete(task.id) is True
        assert repo.get(task.id) is None

    def test_get_nonexistent_returns_none(self, db_session):
        repo = TaskRepo(db_session)
        assert repo.get("nonexistent") is None

    def test_delete_nonexistent_returns_false(self, db_session):
        repo = TaskRepo(db_session)
        assert repo.delete("nonexistent") is False

    def test_get_by_name(self, db_session):
        repo = TaskRepo(db_session)
        repo.create(name="Webhook Task", prompt="p")
        found = repo.get_by_name("Webhook Task")
        assert found is not None
        assert found.name == "Webhook Task"


class TestRunRepo:
    def _make_task(self, db_session):
        return TaskRepo(db_session).create(name="T", prompt="p")

    def test_create_and_get_run(self, db_session):
        task = self._make_task(db_session)
        repo = RunRepo(db_session)
        run = repo.create(task_id=task.id, trigger="manual")
        assert run.status == "running"
        assert run.trigger == "manual"
        assert run.task_id == task.id

        fetched = repo.get(run.id)
        assert fetched.id == run.id

    def test_complete_run_success(self, db_session):
        task = self._make_task(db_session)
        repo = RunRepo(db_session)
        run = repo.create(task_id=task.id, trigger="cron")
        updated = repo.complete(
            run.id, status="success", stdout="output", stderr="", exit_code=0
        )
        assert updated.status == "success"
        assert updated.stdout == "output"
        assert updated.exit_code == 0
        assert updated.finished_at is not None
        assert updated.duration_ms is not None

    def test_complete_run_failed(self, db_session):
        task = self._make_task(db_session)
        repo = RunRepo(db_session)
        run = repo.create(task_id=task.id, trigger="webhook")
        updated = repo.complete(
            run.id, status="failed", stdout="", stderr="error", exit_code=1
        )
        assert updated.status == "failed"
        assert updated.exit_code == 1

    def test_list_runs_for_task(self, db_session):
        task = self._make_task(db_session)
        repo = RunRepo(db_session)
        repo.create(task_id=task.id, trigger="manual")
        repo.create(task_id=task.id, trigger="cron")
        runs = repo.list(task_id=task.id)
        assert len(runs) == 2

    def test_list_runs_all(self, db_session):
        task = self._make_task(db_session)
        repo = RunRepo(db_session)
        repo.create(task_id=task.id, trigger="manual")
        runs = repo.list()
        assert len(runs) >= 1

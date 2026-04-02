import pytest

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.crud.exceptions import NotFoundError


class TestTaskCrud:
    def test_create_and_get(self, db_session):
        task = task_crud.create(
            db_session,
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

        fetched = task_crud.get(db_session, task.id)
        assert fetched is not None
        assert fetched.id == task.id

    def test_list_tasks(self, db_session):
        task_crud.create(db_session, name="A", prompt="p1")
        task_crud.create(db_session, name="B", prompt="p2")
        tasks = task_crud.get_all(db_session)
        assert len(tasks) == 2

    def test_update_task(self, db_session):
        task = task_crud.create(db_session, name="Old", prompt="p")
        updated = task_crud.update(db_session, task.id, name="New", enabled=False)
        assert updated.name == "New"
        assert updated.enabled is False

    def test_update_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            task_crud.update(db_session, "nonexistent", name="X")

    def test_delete_task(self, db_session):
        task = task_crud.create(db_session, name="Doomed", prompt="p")
        task_crud.delete(db_session, task.id)
        assert task_crud.get(db_session, task.id) is None

    def test_get_nonexistent_returns_none(self, db_session):
        assert task_crud.get(db_session, "nonexistent") is None

    def test_delete_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            task_crud.delete(db_session, "nonexistent")

    def test_get_by_name(self, db_session):
        task_crud.create(db_session, name="Webhook Task", prompt="p")
        found = task_crud.get_by_name(db_session, "Webhook Task")
        assert found is not None
        assert found.name == "Webhook Task"


class TestRunCrud:
    def _make_task(self, db_session):
        return task_crud.create(db_session, name="T", prompt="p")

    def test_create_and_get_run(self, db_session):
        task = self._make_task(db_session)
        run = run_crud.create(db_session, task_id=task.id, trigger="manual")
        assert run.status == "running"
        assert run.trigger == "manual"
        assert run.task_id == task.id

        fetched = run_crud.get(db_session, run.id)
        assert fetched.id == run.id

    def test_complete_run_success(self, db_session):
        task = self._make_task(db_session)
        run = run_crud.create(db_session, task_id=task.id, trigger="cron")
        updated = run_crud.complete(
            db_session,
            run.id,
            status="success",
            stdout="output",
            stderr="",
            exit_code=0,
        )
        assert updated.status == "success"
        assert updated.stdout == "output"
        assert updated.exit_code == 0
        assert updated.finished_at is not None
        assert updated.duration_ms is not None

    def test_complete_run_failed(self, db_session):
        task = self._make_task(db_session)
        run = run_crud.create(db_session, task_id=task.id, trigger="webhook")
        updated = run_crud.complete(
            db_session, run.id, status="failed", stdout="", stderr="error", exit_code=1
        )
        assert updated.status == "failed"
        assert updated.exit_code == 1

    def test_list_runs_for_task(self, db_session):
        task = self._make_task(db_session)
        run_crud.create(db_session, task_id=task.id, trigger="manual")
        run_crud.create(db_session, task_id=task.id, trigger="cron")
        runs = run_crud.get_all(db_session, task_id=task.id)
        assert len(runs) == 2

    def test_list_runs_all(self, db_session):
        task = self._make_task(db_session)
        run_crud.create(db_session, task_id=task.id, trigger="manual")
        runs = run_crud.get_all(db_session)
        assert len(runs) >= 1

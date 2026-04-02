import time
from unittest.mock import MagicMock

import pytest

from app.crud import TaskRepo, RunRepo
from app.services import (
    TaskService,
    RunService,
    TaskNotFoundError,
    RunNotFoundError,
    execute_task,
    execute_task_background,
)


@pytest.fixture
def task_repo(db_session):
    return TaskRepo(db_session)


@pytest.fixture
def run_repo(db_session):
    return RunRepo(db_session)


@pytest.fixture
def task_svc(task_repo):
    return TaskService(task_repo)


@pytest.fixture
def run_svc(run_repo):
    return RunService(run_repo)


class TestTaskService:
    def test_create(self, task_svc):
        task = task_svc.create(name="Test", prompt="Do it")
        assert task.name == "Test"
        assert task.id

    def test_list(self, task_svc):
        task_svc.create(name="A", prompt="p")
        task_svc.create(name="B", prompt="p")
        assert len(task_svc.list()) == 2

    def test_get(self, task_svc):
        task = task_svc.create(name="X", prompt="p")
        assert task_svc.get(task.id).name == "X"

    def test_get_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.get("nonexistent")

    def test_get_by_name(self, task_svc):
        task_svc.create(name="Named", prompt="p")
        assert task_svc.get_by_name("Named").name == "Named"

    def test_get_by_name_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.get_by_name("nope")

    def test_update(self, task_svc):
        task = task_svc.create(name="Old", prompt="p")
        updated = task_svc.update(task.id, name="New")
        assert updated.name == "New"

    def test_update_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.update("nonexistent", name="X")

    def test_delete(self, task_svc):
        task = task_svc.create(name="Gone", prompt="p")
        task_svc.delete(task.id)
        with pytest.raises(TaskNotFoundError):
            task_svc.get(task.id)

    def test_delete_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.delete("nonexistent")


class TestRunService:
    def test_list(self, task_svc, run_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        run_repo.create(task_id=task.id, trigger="manual")
        assert len(run_svc.list()) == 1
        assert len(run_svc.list(task_id=task.id)) == 1

    def test_get(self, task_svc, run_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        run = run_repo.create(task_id=task.id, trigger="manual")
        assert run_svc.get(run.id).trigger == "manual"

    def test_get_not_found(self, run_svc):
        with pytest.raises(RunNotFoundError):
            run_svc.get("nonexistent")


class TestExecuteTask:
    def test_success(self, task_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        result = execute_task(task, run_repo, runner=mock_runner)
        assert result.status == "success"
        assert result.exit_code == 0

    def test_failure(self, task_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={"exit_code": 1, "stdout": "", "stderr": "err", "activity": ""}
        )
        result = execute_task(task, run_repo, runner=mock_runner)
        assert result.status == "failed"
        assert result.exit_code == 1

    def test_exception(self, task_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(side_effect=RuntimeError("boom"))
        result = execute_task(task, run_repo, runner=mock_runner)
        assert result.status == "failed"
        assert result.exit_code == -1
        assert "boom" in result.stderr

    def test_on_output_callback(self, task_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        output_calls = []
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )

        def capture(stdout: str, activity: str) -> None:
            output_calls.append((stdout, activity))

        execute_task(task, run_repo, runner=mock_runner, on_output=capture)
        mock_runner.assert_called_once()


class TestExecuteTaskBg:
    def test_returns_running(self, task_svc, session_factory):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        run = execute_task_background(task, session_factory, runner=mock_runner)
        assert run.status == "running"
        time.sleep(0.1)
        session = session_factory()
        completed = RunRepo(session).get(run.id)
        assert completed.status == "success"
        session.close()

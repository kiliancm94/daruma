"""Service layer — shared business logic for FastAPI routes and CLI."""

import threading
from typing import Callable

from sqlalchemy.orm import sessionmaker

from app.crud import TaskRepo, RunRepo
from app.models.database import Task, Run
from app.runner import run_claude, cancel_run


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class RunNotFoundError(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class TaskService:
    def __init__(self, repo: TaskRepo):
        self.repo = repo

    def list(self) -> list[Task]:
        return self.repo.list()

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        enabled: bool = True,
    ) -> Task:
        return self.repo.create(
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            enabled=enabled,
        )

    def get(self, task_id: str) -> Task:
        task = self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def get_by_name(self, name: str) -> Task:
        task = self.repo.get_by_name(name)
        if not task:
            raise TaskNotFoundError(name)
        return task

    def update(self, task_id: str, **fields) -> Task:
        task = self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return self.repo.update(task_id, **fields)

    def delete(self, task_id: str) -> None:
        if not self.repo.delete(task_id):
            raise TaskNotFoundError(task_id)


class RunService:
    def __init__(self, repo: RunRepo):
        self.repo = repo

    def list(self, task_id: str | None = None) -> list[Run]:
        return self.repo.list(task_id=task_id)

    def get(self, run_id: str) -> Run:
        run = self.repo.get(run_id)
        if not run:
            raise RunNotFoundError(run_id)
        return run

    def last_run(self, task_id: str) -> Run | None:
        return self.repo.last_run(task_id)


def execute_task(
    task: Task,
    run_repo: RunRepo,
    trigger: str = "manual",
    runner: Callable | None = None,
    on_output: Callable[[str, str], None] | None = None,
) -> Run:
    """Execute a task synchronously. Returns the completed Run."""
    if runner is None:
        runner = run_claude
    run = run_repo.create(task_id=task.id, trigger=trigger)
    run_id = run.id

    if on_output:

        def _combined(stdout: str, activity: str) -> None:
            run_repo.update_output(run_id, stdout, activity)
            on_output(stdout, activity)
    else:

        def _combined(stdout: str, activity: str) -> None:
            run_repo.update_output(run_id, stdout, activity)

    try:
        result = runner(
            task.prompt,
            allowed_tools=task.allowed_tools,
            run_id=run_id,
            on_output=_combined,
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        return run_repo.complete(
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
    except Exception as e:
        return run_repo.complete(
            run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )


def execute_task_background(
    task: Task,
    session_factory: sessionmaker,
    trigger: str = "manual",
    runner: Callable | None = None,
) -> Run:
    """Execute a task in a background thread. Returns the initial Run (status=running)."""
    if runner is None:
        runner = run_claude
    session = session_factory()
    try:
        run_repo = RunRepo(session)
        run = run_repo.create(task_id=task.id, trigger=trigger)
        session.expunge(run)
    finally:
        session.close()

    threading.Thread(
        target=_background_worker,
        args=(task.prompt, task.allowed_tools, run.id, runner, session_factory),
        daemon=True,
    ).start()
    return run


def _background_worker(
    prompt: str,
    allowed_tools: str | None,
    run_id: str,
    runner: Callable,
    session_factory: sessionmaker,
) -> None:
    session = session_factory()
    run_repo = RunRepo(session)
    try:
        result = runner(
            prompt,
            allowed_tools=allowed_tools,
            run_id=run_id,
            on_output=lambda stdout, activity: run_repo.update_output(
                run_id, stdout, activity
            ),
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        run_repo.complete(
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
    except Exception as e:
        run_repo.complete(
            run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )
    finally:
        session.close()


def cancel_task_run(run_id: str, run_repo: RunRepo) -> None:
    """Cancel a running task. Raises RunNotFoundError or ValueError."""
    run = run_repo.get(run_id)
    if not run:
        raise RunNotFoundError(run_id)
    if run.status != "running":
        raise ValueError("Run is not active")
    killed = cancel_run(run_id)
    if not killed:
        run_repo.complete(
            run_id, status="failed", stdout="", stderr="Cancelled", exit_code=-1
        )

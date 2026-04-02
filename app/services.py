"""Service layer — shared business logic for FastAPI routes and CLI."""

import threading
from typing import Callable

from app.repository import TaskRepo, RunRepo
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

    def list(self) -> list[dict]:
        return self.repo.list()

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        enabled: bool = True,
    ) -> dict:
        return self.repo.create(
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            enabled=enabled,
        )

    def get(self, task_id: str) -> dict:
        task = self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def get_by_name(self, name: str) -> dict:
        task = self.repo.get_by_name(name)
        if not task:
            raise TaskNotFoundError(name)
        return task

    def update(self, task_id: str, **fields) -> dict:
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

    def list(self, task_id: str | None = None) -> list[dict]:
        return self.repo.list(task_id=task_id)

    def get(self, run_id: str) -> dict:
        run = self.repo.get(run_id)
        if not run:
            raise RunNotFoundError(run_id)
        return run


def execute_task(
    task: dict,
    run_repo: RunRepo,
    trigger: str = "manual",
    runner: Callable = run_claude,
    on_output: Callable[[str], None] | None = None,
) -> dict:
    """Execute a task synchronously. Returns the completed run dict."""
    run = run_repo.create(task_id=task["id"], trigger=trigger)
    run_id = run["id"]

    if on_output:
        def _combined(stdout: str) -> None:
            run_repo.update_output(run_id, stdout)
            on_output(stdout)
    else:
        def _combined(stdout: str) -> None:
            run_repo.update_output(run_id, stdout)

    try:
        result = runner(
            task["prompt"],
            allowed_tools=task.get("allowed_tools"),
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
        )
    except Exception as e:
        return run_repo.complete(
            run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )


def execute_task_bg(
    task: dict,
    run_repo: RunRepo,
    trigger: str = "manual",
    runner: Callable = run_claude,
) -> dict:
    """Execute a task in a background thread. Returns the initial run dict (status=running)."""
    run = run_repo.create(task_id=task["id"], trigger=trigger)
    threading.Thread(
        target=_bg_worker,
        args=(task, run["id"], runner, run_repo),
        daemon=True,
    ).start()
    return run


def _bg_worker(task: dict, run_id: str, runner: Callable, run_repo: RunRepo) -> None:
    try:
        result = runner(
            task["prompt"],
            allowed_tools=task.get("allowed_tools"),
            run_id=run_id,
            on_output=lambda stdout: run_repo.update_output(run_id, stdout),
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        run_repo.complete(
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
        )
    except Exception as e:
        run_repo.complete(
            run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )


def cancel_task_run(run_id: str, run_repo: RunRepo) -> None:
    """Cancel a running task. Raises RunNotFoundError or ValueError."""
    run = run_repo.get(run_id)
    if not run:
        raise RunNotFoundError(run_id)
    if run["status"] != "running":
        raise ValueError("Run is not active")
    killed = cancel_run(run_id)
    if not killed:
        run_repo.complete(
            run_id, status="failed", stdout="", stderr="Cancelled", exit_code=-1
        )

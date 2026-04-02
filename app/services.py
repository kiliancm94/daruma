"""Service layer — shared business logic for FastAPI routes and CLI."""

import threading
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.crud.exceptions import NotFoundError
from app.models.task import Task
from app.models.run import Run
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
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Task]:
        return task_crud.get_all(self.session)

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        model: str = "sonnet",
        enabled: bool = True,
    ) -> Task:
        return task_crud.create(
            self.session,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            model=model,
            enabled=enabled,
        )

    def get(self, task_id: str) -> Task:
        task = task_crud.get(self.session, task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def get_by_name(self, name: str) -> Task:
        task = task_crud.get_by_name(self.session, name)
        if not task:
            raise TaskNotFoundError(name)
        return task

    def update(self, task_id: str, **fields) -> Task:
        try:
            return task_crud.update(self.session, task_id, **fields)
        except NotFoundError:
            raise TaskNotFoundError(task_id)

    def delete(self, task_id: str) -> None:
        try:
            task_crud.delete(self.session, task_id)
        except NotFoundError:
            raise TaskNotFoundError(task_id)


class RunService:
    def __init__(self, session: Session):
        self.session = session

    def list(self, task_id: str | None = None) -> list[Run]:
        return run_crud.get_all(self.session, task_id=task_id)

    def get(self, run_id: str) -> Run:
        run = run_crud.get(self.session, run_id)
        if not run:
            raise RunNotFoundError(run_id)
        return run

    def last_run(self, task_id: str) -> Run | None:
        return run_crud.get_last(self.session, task_id)


def execute_task(
    task: Task,
    session: Session,
    trigger: str = "manual",
    runner: Callable | None = None,
    on_output: Callable[[str, str], None] | None = None,
) -> Run:
    """Execute a task synchronously. Returns the completed Run."""
    if runner is None:
        runner = run_claude
    run = run_crud.create(session, task_id=task.id, trigger=trigger)
    run_id = run.id

    if on_output:

        def _combined(stdout: str, activity: str) -> None:
            run_crud.update_output(session, run_id, stdout, activity)
            on_output(stdout, activity)

    else:

        def _combined(stdout: str, activity: str) -> None:
            run_crud.update_output(session, run_id, stdout, activity)

    try:
        result = runner(
            task.prompt,
            allowed_tools=task.allowed_tools,
            model=task.model,
            run_id=run_id,
            on_output=_combined,
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        return run_crud.complete(
            session,
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
    except Exception as e:
        return run_crud.complete(
            session, run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
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
        run = run_crud.create(session, task_id=task.id, trigger=trigger)
        session.expunge(run)
    finally:
        session.close()

    threading.Thread(
        target=_background_worker,
        args=(
            task.prompt,
            task.allowed_tools,
            task.model,
            run.id,
            runner,
            session_factory,
        ),
        daemon=True,
    ).start()
    return run


def _background_worker(
    prompt: str,
    allowed_tools: str | None,
    model: str,
    run_id: str,
    runner: Callable,
    session_factory: sessionmaker,
) -> None:
    session = session_factory()
    try:
        result = runner(
            prompt,
            allowed_tools=allowed_tools,
            model=model,
            run_id=run_id,
            on_output=lambda stdout, activity: run_crud.update_output(
                session, run_id, stdout, activity
            ),
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        run_crud.complete(
            session,
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
    except Exception as e:
        run_crud.complete(
            session, run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )
    finally:
        session.close()


def cancel_task_run(run_id: str, session: Session) -> None:
    """Cancel a running task. Raises RunNotFoundError or ValueError."""
    run = run_crud.get(session, run_id)
    if not run:
        raise RunNotFoundError(run_id)
    if run.status != "running":
        raise ValueError("Run is not active")
    killed = cancel_run(run_id)
    if not killed:
        run_crud.complete(
            session,
            run_id,
            status="failed",
            stdout="",
            stderr="Cancelled",
            exit_code=-1,
        )

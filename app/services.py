"""Service layer — shared business logic for FastAPI routes and CLI."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.crud.exceptions import NotFoundError
from app.models.task import Task
from app.models.run import Run
from app.schemas.task import OutputFormat
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
        output_format: OutputFormat | None = None,
        output_destination: str | None = None,
    ) -> Task:
        return task_crud.create(
            self.session,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            model=model,
            enabled=enabled,
            output_format=output_format,
            output_destination=output_destination,
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


# ── Output writing ─────────────────────────────────────────────────────────────

_EXT = {OutputFormat.text: "txt", OutputFormat.json: "json", OutputFormat.md: "md"}


def _format_output(stdout: str, fmt: OutputFormat, task_name: str, run_id: str) -> str:
    """Format run stdout according to the task's output_format."""
    if fmt == OutputFormat.json:
        return json.dumps(
            {
                "task": task_name,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "output": stdout,
            },
            indent=2,
        )
    if fmt == OutputFormat.md:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"# {task_name}\n\n_Run {run_id[:8]} — {ts}_\n\n{stdout}\n"
    return stdout  # OutputFormat.text or None → raw


def _write_output(stdout: str, task: Task, run_id: str) -> None:
    """Write run output to a file if output_destination is configured.

    Destination can be:
    - A file path: written directly (overwritten each run)
    - A directory path (ends with / or has no extension): timestamped file created inside
    - "pipe": no file written; output is stored in Run.stdout for future task chaining
    """
    dest = task.output_destination
    if not dest or dest == "pipe":
        return

    fmt = task.output_format or OutputFormat.text
    content = _format_output(stdout, fmt, task.name, run_id)
    ext = _EXT.get(fmt, "txt")

    path = Path(dest)
    # Treat as directory if it ends with / or has no suffix
    if dest.endswith("/") or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = path / f"{task.name}_{ts}.{ext}"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(content, encoding="utf-8")


# ── Task execution ─────────────────────────────────────────────────────────────


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
        completed = run_crud.complete(
            session,
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
        if status == "success":
            _write_output(result["stdout"], task, run_id)
        return completed
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
            task,
            run.id,
            runner,
            session_factory,
        ),
        daemon=True,
    ).start()
    return run


def _background_worker(
    task: Task,
    run_id: str,
    runner: Callable,
    session_factory: sessionmaker,
) -> None:
    session = session_factory()
    try:
        result = runner(
            task.prompt,
            allowed_tools=task.allowed_tools,
            model=task.model,
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
        if status == "success":
            _write_output(result["stdout"], task, run_id)
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

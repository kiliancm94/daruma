# SQLAlchemy Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from raw sqlite3 to SQLAlchemy ORM, separate DB models (`app/models/`) from CRUD operations (`app/crud/`), Pydantic schemas with `from_attributes=True` for automatic ORM parsing, and add rich CLI output with `--json` support.

**Architecture:** SQLAlchemy ORM models define database tables. Pydantic schemas handle API/CLI input/output and auto-parse from ORM objects via `from_attributes=True`. CRUD repositories use SQLAlchemy `Session`. FastAPI dependencies create per-request sessions. Background threads get their own sessions via a session factory.

**Tech Stack:** SQLAlchemy 2.x (ORM), Pydantic v2 (`ConfigDict(from_attributes=True)`), rich (CLI formatting)

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add sqlalchemy and rich to dependencies**

In the `dependencies` list in `pyproject.toml`, add:

```
"sqlalchemy>=2.0",
"rich>=13.0",
```

**Step 2: Install**

Run: `uv sync`

**Step 3: Verify**

Run: `uv run python -c "import sqlalchemy; import rich; print('OK')"`
Expected: `OK`

---

## Task 2: Create `app/models/` package

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/database.py`
- Create: `app/models/schemas.py`

### `app/models/database.py` — SQLAlchemy ORM models

```python
"""SQLAlchemy ORM models — own the database table definitions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Task(Base):
    __tablename__ = "tasks"

    id: str = Column(String, primary_key=True, default=_new_id)
    name: str = Column(String, nullable=False)
    prompt: str = Column(Text, nullable=False)
    cron_expression: str | None = Column(String, nullable=True)
    allowed_tools: str | None = Column(String, nullable=True)
    enabled: bool = Column(Boolean, nullable=False, default=True)
    created_at: str = Column(String, nullable=False, default=_utcnow)
    updated_at: str = Column(String, nullable=False, default=_utcnow)

    runs = relationship("Run", back_populates="task", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    id: str = Column(String, primary_key=True, default=_new_id)
    task_id: str = Column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    trigger: str = Column(String, nullable=False)
    status: str = Column(String, nullable=False, default="running")
    started_at: str = Column(String, nullable=False, default=_utcnow)
    finished_at: str | None = Column(String, nullable=True)
    duration_ms: int | None = Column(Integer, nullable=True)
    stdout: str | None = Column(Text, nullable=True)
    stderr: str | None = Column(Text, nullable=True)
    exit_code: int | None = Column(Integer, nullable=True)
    activity: str | None = Column(Text, nullable=True)

    task = relationship("Task", back_populates="runs")
```

### `app/models/schemas.py` — Pydantic models (API/CLI input/output)

```python
"""Pydantic schemas — define input/output for API and CLI.

Base response models use from_attributes=True to auto-parse from ORM objects.
"""

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    name: str
    prompt: str
    cron_expression: str | None = None
    allowed_tools: str | None = None
    enabled: bool = True


class TaskUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    cron_expression: str | None = None
    allowed_tools: str | None = None
    enabled: bool | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt: str
    cron_expression: str | None
    allowed_tools: str | None
    enabled: bool
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    trigger: str
    status: str
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    activity: str | None = None
```

### `app/models/__init__.py`

```python
from app.models.database import Base, Task, Run
from app.models.schemas import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    RunResponse,
)
```

**Verify:**

Run: `uv run python -c "from app.models import Base, Task, Run, TaskCreate, TaskResponse, RunResponse; print('OK')"`
Expected: `OK`

---

## Task 3: Rewrite `app/db.py` with SQLAlchemy engine/session

**Files:**
- Rewrite: `app/db.py`

Replace the entire file with:

```python
"""Database engine and session management (SQLAlchemy)."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models.database import Base

_engine = None
_SessionLocal: sessionmaker | None = None


def _set_sqlite_pragmas(engine) -> None:
    """Enable WAL mode and foreign keys for every new SQLite connection."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db(db_path: Path) -> None:
    """Create engine, apply pragmas, create tables, configure session factory."""
    global _engine, _SessionLocal
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    _set_sqlite_pragmas(_engine)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_db():
    """FastAPI dependency — yields a session, closes on cleanup."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session() -> Session:
    """Create a standalone session (CLI, background workers)."""
    return _SessionLocal()


def get_session_factory() -> sessionmaker:
    """Return the session factory (for background thread spawning)."""
    return _SessionLocal


def dispose() -> None:
    """Dispose engine (for clean test teardown)."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
```

**Verify:**

Run: `uv run python -c "from app.db import init_db; print('OK')"`
Expected: `OK`

---

## Task 4: Create `app/crud/` package

**Files:**
- Create: `app/crud/__init__.py`
- Create: `app/crud/tasks.py`
- Create: `app/crud/runs.py`

### `app/crud/tasks.py`

```python
"""CRUD operations for tasks."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.database import Task


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRepo:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        enabled: bool = True,
    ) -> Task:
        now = _utcnow()
        task = Task(
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get(self, task_id: str) -> Task | None:
        return self.session.get(Task, task_id)

    def get_by_name(self, name: str) -> Task | None:
        return self.session.query(Task).filter(Task.name == name).first()

    def list(self) -> list[Task]:
        return self.session.query(Task).order_by(Task.created_at.desc()).all()

    _UPDATABLE_FIELDS = {"name", "prompt", "cron_expression", "allowed_tools", "enabled"}

    def update(self, task_id: str, **fields) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        updates = {
            k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS and v is not None
        }
        if not updates:
            return task
        for key, value in updates.items():
            setattr(task, key, value)
        task.updated_at = _utcnow()
        self.session.commit()
        self.session.refresh(task)
        return task

    def delete(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task is None:
            return False
        self.session.delete(task)
        self.session.commit()
        return True
```

### `app/crud/runs.py`

```python
"""CRUD operations for runs."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.database import Run


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRepo:
    def __init__(self, session: Session):
        self.session = session

    def create(self, task_id: str, trigger: str) -> Run:
        run = Run(task_id=task_id, trigger=trigger, started_at=_utcnow())
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, run_id: str) -> Run | None:
        return self.session.get(Run, run_id)

    def update_output(self, run_id: str, stdout: str, activity: str = "") -> None:
        """Update partial stdout/activity while a run is still in progress."""
        run = self.get(run_id)
        if run:
            run.stdout = stdout
            run.activity = activity
            self.session.commit()

    def complete(
        self,
        run_id: str,
        status: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        activity: str = "",
    ) -> Run | None:
        run = self.get(run_id)
        if run is None:
            return None
        now = _utcnow()
        started = datetime.fromisoformat(run.started_at)
        finished = datetime.fromisoformat(now)
        duration_ms = int((finished - started).total_seconds() * 1000)
        run.status = status
        run.finished_at = now
        run.duration_ms = duration_ms
        run.stdout = stdout
        run.stderr = stderr
        run.exit_code = exit_code
        run.activity = activity
        self.session.commit()
        self.session.refresh(run)
        return run

    def last_run(self, task_id: str) -> Run | None:
        return (
            self.session.query(Run)
            .filter(Run.task_id == task_id)
            .order_by(Run.started_at.desc())
            .first()
        )

    def list(self, task_id: str | None = None) -> list[Run]:
        query = self.session.query(Run)
        if task_id:
            query = query.filter(Run.task_id == task_id)
        return query.order_by(Run.started_at.desc()).all()
```

### `app/crud/__init__.py`

```python
from app.crud.tasks import TaskRepo
from app.crud.runs import RunRepo
```

**Verify:**

Run: `uv run python -c "from app.crud import TaskRepo, RunRepo; print('OK')"`
Expected: `OK`

**Commit:** `feat: add SQLAlchemy models, Pydantic schemas, CRUD layer, and db setup`

---

## Task 5: Update `app/services.py`

**Files:**
- Rewrite: `app/services.py`

Key changes:
- Import from `app.crud` instead of `app.repository`
- Methods accept/return ORM objects (`Task`, `Run`) instead of dicts
- `execute_task` accesses ORM attributes (`.id`, `.prompt`) instead of dict keys
- `execute_task_background` takes a `session_factory` for thread safety
- `_background_worker` creates its own session

```python
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
    """Execute a task in a background thread. Returns the initial Run (status=running).

    Uses session_factory to create thread-safe sessions for the background worker.
    """
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
    try:
        run_repo = RunRepo(session)
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
```

**Commit:** `refactor: update services for SQLAlchemy ORM objects and session_factory`

---

## Task 6: Update routers

**Files:**
- Rewrite: `app/routers/tasks.py`
- Rewrite: `app/routers/runs.py`
- Rewrite: `app/routers/triggers.py`
- Modify: `app/routers/ui.py`

All routers switch to per-request sessions via `Depends(get_db)`.

### `app/routers/tasks.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.crud import TaskRepo
from app.db import get_db
from app.models.schemas import TaskCreate, TaskUpdate, TaskResponse
from app.services import TaskService, TaskNotFoundError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepo(session))


@router.get("", response_model=list[TaskResponse])
def list_tasks(task_service: TaskService = Depends(get_task_service)):
    return task_service.list()


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreate, task_service: TaskService = Depends(get_task_service)):
    return task_service.create(
        name=body.name,
        prompt=body.prompt,
        cron_expression=body.cron_expression,
        allowed_tools=body.allowed_tools,
        enabled=body.enabled,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, task_service: TaskService = Depends(get_task_service)):
    try:
        return task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str, body: TaskUpdate, task_service: TaskService = Depends(get_task_service)
):
    try:
        return task_service.update(task_id, **body.model_dump(exclude_unset=True))
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, task_service: TaskService = Depends(get_task_service)):
    try:
        task_service.delete(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return Response(status_code=204)
```

### `app/routers/runs.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import RunRepo
from app.db import get_db
from app.models.schemas import RunResponse
from app.services import RunService, RunNotFoundError

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_service(session: Session = Depends(get_db)) -> RunService:
    return RunService(RunRepo(session))


@router.get("", response_model=list[RunResponse])
def list_runs(
    task_id: str | None = None, run_service: RunService = Depends(get_run_service)
):
    return run_service.list(task_id=task_id)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, run_service: RunService = Depends(get_run_service)):
    try:
        return run_service.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
```

### `app/routers/triggers.py`

```python
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.crud import TaskRepo, RunRepo
from app.db import get_db
from app.db import get_session_factory as _get_session_factory
from app.models.schemas import RunResponse
from app.runner import run_claude
from app.services import (
    TaskService,
    RunNotFoundError,
    TaskNotFoundError,
    execute_task_background,
    cancel_task_run,
)

router = APIRouter(tags=["triggers"])


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepo(session))


def get_run_repo(session: Session = Depends(get_db)) -> RunRepo:
    return RunRepo(session)


def get_session_factory() -> sessionmaker:
    return _get_session_factory()


def get_runner() -> Callable:
    return run_claude


@router.post("/api/tasks/{task_id}/run", response_model=RunResponse)
def manual_trigger(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    session_factory: sessionmaker = Depends(get_session_factory),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_background(task, session_factory, trigger="manual", runner=runner)


@router.post("/api/trigger/{task_name}", response_model=RunResponse)
def webhook_trigger(
    task_name: str,
    task_service: TaskService = Depends(get_task_service),
    session_factory: sessionmaker = Depends(get_session_factory),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_service.get_by_name(task_name)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_background(task, session_factory, trigger="webhook", runner=runner)


@router.post("/api/runs/{run_id}/cancel")
def cancel_run_endpoint(
    run_id: str,
    run_repo: RunRepo = Depends(get_run_repo),
):
    try:
        cancel_task_run(run_id, run_repo)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "cancelled"}
```

### `app/routers/ui.py`

```python
"""UI router serving Jinja2 templates with HTMX interactions."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud import TaskRepo, RunRepo
from app.db import get_db
from app.models.schemas import TaskResponse, RunResponse
from app.services import TaskService, RunService, TaskNotFoundError, RunNotFoundError

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent / "templates")
)


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepo(session))


def get_run_service(session: Session = Depends(get_db)) -> RunService:
    return RunService(RunRepo(session))


@router.get("/", response_class=HTMLResponse)
def tasks_list(
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    run_service: RunService = Depends(get_run_service),
):
    tasks = task_service.list()
    # Convert to dicts so templates can add last_run key
    task_data = []
    for task in tasks:
        d = TaskResponse.model_validate(task).model_dump()
        last_run = run_service.last_run(task.id)
        d["last_run"] = RunResponse.model_validate(last_run).model_dump() if last_run else None
        task_data.append(d)
    return templates.TemplateResponse(request, "tasks_list.html", {"tasks": task_data})


@router.get("/tasks/new", response_class=HTMLResponse)
def task_form_new(request: Request):
    return templates.TemplateResponse(request, "task_form.html", {"task": None})


@router.post("/tasks", response_class=HTMLResponse)
def task_create_form(
    name: str = Form(...),
    prompt: str = Form(...),
    cron_expression: str = Form(""),
    allowed_tools: str = Form(""),
    enabled: str = Form(""),
    task_service: TaskService = Depends(get_task_service),
):
    task_service.create(
        name=name,
        prompt=prompt,
        cron_expression=cron_expression or None,
        allowed_tools=allowed_tools or None,
        enabled=bool(enabled),
    )
    return RedirectResponse("/ui/", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(
    request: Request,
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    run_service: RunService = Depends(get_run_service),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    runs = run_service.list(task_id=task_id)
    return templates.TemplateResponse(
        request, "task_detail.html", {"task": task, "runs": runs}
    )


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def task_edit_form(
    request: Request,
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return templates.TemplateResponse(request, "task_form.html", {"task": task})


@router.post("/tasks/{task_id}", response_class=HTMLResponse)
def task_update_form(
    task_id: str,
    name: str = Form(...),
    prompt: str = Form(...),
    cron_expression: str = Form(""),
    allowed_tools: str = Form(""),
    enabled: str = Form(""),
    task_service: TaskService = Depends(get_task_service),
):
    try:
        task_service.update(
            task_id,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression or None,
            allowed_tools=allowed_tools or None,
            enabled=bool(enabled),
        )
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return RedirectResponse(f"/ui/tasks/{task_id}", status_code=303)


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = run_service.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse(request, "run_detail.html", {"run": run})


@router.get("/runs/{run_id}/card", response_class=HTMLResponse)
def run_card(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = run_service.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse(
        request, "partials/run_card.html", {"run": run}
    )
```

**Commit:** `refactor: update routers for SQLAlchemy session dependencies`

---

## Task 7: Update `app/main.py` and `app/scheduler.py`

**Files:**
- Rewrite: `app/main.py`
- Modify: `app/scheduler.py` (attribute access instead of dict keys)

### `app/main.py`

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import DB_PATH
from app.crud import TaskRepo, RunRepo
from app.db import init_db, get_session, dispose
from app.runner import run_claude
from app.scheduler import create_scheduler, sync_jobs
from app.services import execute_task
from app.routers import tasks as tasks_router
from app.routers import runs as runs_router
from app.routers import triggers as triggers_router
from app.routers import ui as ui_router

_scheduler = None


def _execute_cron_task(task_id: str) -> None:
    session = get_session()
    try:
        task_repo = TaskRepo(session)
        run_repo = RunRepo(session)
        task = task_repo.get(task_id)
        if not task:
            return
        execute_task(task, run_repo, trigger="cron")
    finally:
        session.close()


def _refresh_scheduler() -> None:
    if _scheduler:
        session = get_session()
        try:
            tasks = TaskRepo(session).list()
            sync_jobs(_scheduler, tasks, _execute_cron_task)
        finally:
            session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db(DB_PATH)
    _scheduler = create_scheduler()
    _refresh_scheduler()
    _scheduler.start()
    yield
    _scheduler.shutdown()
    dispose()


app = FastAPI(title="Daruma — Claude Automations Runner", lifespan=lifespan)

app.include_router(tasks_router.router)
app.include_router(runs_router.router)
app.include_router(triggers_router.router)
app.include_router(ui_router.router)

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}
```

### `app/scheduler.py` — change dict access to attribute access

Replace every `task["field"]` with `task.field`:

- `task["cron_expression"]` → `task.cron_expression`
- `task["enabled"]` → `task.enabled`
- `task["id"]` → `task.id`
- `task["name"]` → `task.name`

Full updated file:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


def create_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler()


def sync_jobs(
    scheduler: BackgroundScheduler,
    tasks: list,
    execute_fn,
) -> None:
    existing_job_ids = {job.id for job in scheduler.get_jobs()}
    desired_job_ids = set()

    for task in tasks:
        if not task.cron_expression or not task.enabled:
            continue
        desired_job_ids.add(task.id)

    # Remove jobs that should no longer exist
    for job_id in existing_job_ids:
        if job_id not in desired_job_ids:
            scheduler.remove_job(job_id)

    # Add jobs that don't exist yet
    for task in tasks:
        if task.id not in desired_job_ids:
            continue
        if task.id in existing_job_ids:
            continue
        parts = task.cron_expression.split()
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        scheduler.add_job(
            execute_fn,
            trigger=trigger,
            args=[task.id],
            id=task.id,
            name=task.name,
            replace_existing=True,
        )
```

**Commit:** `refactor: update main.py and scheduler for SQLAlchemy`

---

## Task 8: Update `app/cli.py` with rich output

**Files:**
- Rewrite: `app/cli.py`

Key changes:
- Import from `app.crud` instead of `app.repository`
- Use `init_db` + `get_session` instead of old `init_db` returning connection
- Dict access (`task["name"]`) → attribute access (`task.name`)
- Add `rich.console.Console`, `rich.table.Table`, `console.print_json` for output
- Add `--json` flag to `list` and `show` commands
- Use `TaskResponse.model_validate()` / `RunResponse.model_validate()` for JSON serialization

```python
"""Daruma CLI — manage and run Claude automation tasks."""

import sys

import click
from rich.console import Console
from rich.table import Table

from app.config import DB_PATH
from app.crud import TaskRepo, RunRepo
from app.db import init_db, get_session
from app.models.schemas import TaskResponse, RunResponse
from app.services import (
    TaskService,
    RunService,
    TaskNotFoundError,
    RunNotFoundError,
    execute_task,
)

console = Console()


def _connect():
    init_db(DB_PATH)
    return get_session()


@click.group()
def cli():
    """Daruma — Claude automation task runner."""


# ── Tasks ──────────────────────────────────────────────


@cli.group()
def tasks():
    """Manage tasks."""


@tasks.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_tasks(as_json):
    """List all tasks."""
    session = _connect()
    task_service = TaskService(TaskRepo(session))
    items = task_service.list()
    session.close()
    if not items:
        click.echo("No tasks found.")
        return
    if as_json:
        data = [TaskResponse.model_validate(t).model_dump() for t in items]
        console.print_json(data=data)
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name")
    table.add_column("Schedule", style="dim")
    table.add_column("Status")
    for t in items:
        status = "[green]enabled[/green]" if t.enabled else "[red]disabled[/red]"
        cron = t.cron_expression or "manual only"
        table.add_row(t.id[:8], t.name, cron, status)
    console.print(table)


@tasks.command("create")
@click.option("--name", required=True, help="Task name")
@click.option("--prompt", required=True, help="Claude prompt")
@click.option("--cron", default=None, help="Cron expression (5-field)")
@click.option("--tools", default=None, help="Comma-separated allowed tools")
@click.option("--disabled", is_flag=True, help="Create in disabled state")
def create_task(name, prompt, cron, tools, disabled):
    """Create a new task."""
    session = _connect()
    task_service = TaskService(TaskRepo(session))
    task = task_service.create(
        name=name,
        prompt=prompt,
        cron_expression=cron,
        allowed_tools=tools,
        enabled=not disabled,
    )
    session.close()
    click.echo(f"Created task: {task.name} ({task.id[:8]})")


@tasks.command("show")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_task(task_id, as_json):
    """Show task details. Accepts full ID, partial ID, or name."""
    session = _connect()
    task_service = TaskService(TaskRepo(session))
    task = _resolve_task(task_service, task_id)
    session.close()
    if as_json:
        console.print_json(data=TaskResponse.model_validate(task).model_dump())
        return
    click.echo(f"ID:      {task.id}")
    click.echo(f"Name:    {task.name}")
    click.echo(f"Prompt:  {task.prompt}")
    click.echo(f"Cron:    {task.cron_expression or 'none'}")
    click.echo(f"Tools:   {task.allowed_tools or 'all'}")
    click.echo(f"Enabled: {task.enabled}")
    click.echo(f"Created: {task.created_at}")
    click.echo(f"Updated: {task.updated_at}")


@tasks.command("edit")
@click.argument("task_id")
@click.option("--name", default=None)
@click.option("--prompt", default=None)
@click.option("--cron", default=None)
@click.option("--tools", default=None)
@click.option("--enable/--disable", default=None)
def edit_task(task_id, name, prompt, cron, tools, enable):
    """Update a task."""
    session = _connect()
    task_service = TaskService(TaskRepo(session))
    task = _resolve_task(task_service, task_id)
    fields = {}
    if name is not None:
        fields["name"] = name
    if prompt is not None:
        fields["prompt"] = prompt
    if cron is not None:
        fields["cron_expression"] = cron
    if tools is not None:
        fields["allowed_tools"] = tools
    if enable is not None:
        fields["enabled"] = enable
    if not fields:
        click.echo("Nothing to update.")
        return
    updated = task_service.update(task.id, **fields)
    session.close()
    click.echo(f"Updated task: {updated.name} ({updated.id[:8]})")


@tasks.command("delete")
@click.argument("task_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_task(task_id, yes):
    """Delete a task."""
    session = _connect()
    task_service = TaskService(TaskRepo(session))
    task = _resolve_task(task_service, task_id)
    if not yes:
        click.confirm(f"Delete task '{task.name}'?", abort=True)
    task_service.delete(task.id)
    session.close()
    click.echo(f"Deleted task: {task.name}")


# ── Runs ───────────────────────────────────────────────


@cli.group()
def runs():
    """View run history."""


@runs.command("list")
@click.option("--task", "task_id", default=None, help="Filter by task ID or name")
@click.option("--limit", default=20, help="Max runs to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_runs(task_id, limit, as_json):
    """List recent runs."""
    session = _connect()
    run_service = RunService(RunRepo(session))

    resolved_task_id = None
    if task_id:
        task_service = TaskService(TaskRepo(session))
        task = _resolve_task(task_service, task_id)
        resolved_task_id = task.id

    items = run_service.list(task_id=resolved_task_id)[:limit]
    session.close()
    if not items:
        click.echo("No runs found.")
        return
    if as_json:
        data = [RunResponse.model_validate(r).model_dump() for r in items]
        console.print_json(data=data)
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Trigger", style="dim")
    table.add_column("Duration", style="dim")
    table.add_column("Started")
    for r in items:
        duration = f"{r.duration_ms}ms" if r.duration_ms else "…"
        status_style = {"success": "green", "failed": "red", "running": "yellow"}.get(
            r.status, ""
        )
        table.add_row(
            r.id[:8],
            f"[{status_style}]{r.status}[/{status_style}]" if status_style else r.status,
            r.trigger,
            duration,
            r.started_at,
        )
    console.print(table)


@runs.command("show")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_run(run_id, as_json):
    """Show run details and output."""
    session = _connect()
    run_service = RunService(RunRepo(session))
    try:
        run = run_service.get(run_id)
    except RunNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise SystemExit(1)
    session.close()
    if as_json:
        console.print_json(data=RunResponse.model_validate(run).model_dump())
        return
    click.echo(f"ID:       {run.id}")
    click.echo(f"Task:     {run.task_id}")
    click.echo(f"Trigger:  {run.trigger}")
    click.echo(f"Status:   {run.status}")
    click.echo(f"Started:  {run.started_at}")
    click.echo(f"Finished: {run.finished_at or '…'}")
    click.echo(f"Duration: {run.duration_ms or '…'}ms")
    click.echo(f"Exit:     {run.exit_code}")
    if run.stdout:
        click.echo(f"\n--- stdout ---\n{run.stdout}")
    if run.stderr:
        click.echo(f"\n--- stderr ---\n{run.stderr}")


# ── Run (execute) ─────────────────────────────────────


@cli.command("run")
@click.argument("task_name_or_id")
def run_task(task_name_or_id):
    """Run a task now (blocks until complete, streams output)."""
    session = _connect()
    task_service = TaskService(TaskRepo(session))
    run_repo = RunRepo(session)

    task = _resolve_task(task_service, task_name_or_id)
    click.echo(f"Running task: {task.name}…\n")

    last_output = [""]

    def _on_output(stdout: str, activity: str) -> None:
        if stdout and stdout != last_output[0]:
            new = stdout[len(last_output[0]):]
            if new:
                click.echo(new, nl=False)
            last_output[0] = stdout

    result = execute_task(
        task, run_repo, trigger="manual", on_output=_on_output,
    )
    session.close()
    click.echo()
    click.echo(
        f"\nStatus: {result.status}  "
        f"Exit: {result.exit_code}  "
        f"Duration: {result.duration_ms}ms"
    )
    if result.status != "success":
        sys.exit(1)


# ── Helpers ────────────────────────────────────────────


def _resolve_task(task_service: TaskService, identifier: str):
    """Resolve a task by full ID, partial ID (prefix), or name."""
    try:
        return task_service.get(identifier)
    except TaskNotFoundError:
        pass
    try:
        return task_service.get_by_name(identifier)
    except TaskNotFoundError:
        pass
    all_tasks = task_service.list()
    matches = [t for t in all_tasks if t.id.startswith(identifier)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        click.echo(f"Ambiguous ID prefix '{identifier}', matches:", err=True)
        for t in matches:
            click.echo(f"  {t.id}  {t.name}", err=True)
        raise SystemExit(1)
    click.echo(f"Task not found: {identifier}", err=True)
    raise SystemExit(1)
```

**Commit:** `feat: update CLI for SQLAlchemy + rich output with --json flag`

---

## Task 9: Update tests

**Files:**
- Rewrite: `tests/conftest.py`
- Rewrite: `tests/test_db.py`
- Rename+Rewrite: `tests/test_repository.py` → `tests/test_crud.py`
- Rewrite: `tests/test_services.py`
- Rewrite: `tests/test_api_tasks.py`
- Rewrite: `tests/test_api_runs.py`
- Rewrite: `tests/test_api_triggers.py`
- Rewrite: `tests/test_cli.py`
- Modify: `tests/test_scheduler.py`
- No changes: `tests/test_runner.py`

### `tests/conftest.py`

```python
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def engine(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)
```

### `tests/test_db.py`

```python
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
        "id", "name", "prompt", "cron_expression",
        "allowed_tools", "enabled", "created_at", "updated_at",
    }


def test_runs_table_has_expected_columns(engine):
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("runs")}
    assert columns == {
        "id", "task_id", "trigger", "status", "started_at",
        "finished_at", "duration_ms", "stdout", "stderr", "exit_code",
        "activity",
    }
```

### `tests/test_crud.py` (was `test_repository.py`)

```python
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
    def _make_task(self, db_session) -> "Task":
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
```

### `tests/test_services.py`

```python
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
    cancel_task_run,
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


# ── TaskService ────────────────────────────────────────


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


# ── RunService ─────────────────────────────────────────


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


# ── execute_task ───────────────────────────────────────


class TestExecuteTask:
    def test_success(self, task_svc, run_repo):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={"exit_code": 0, "stdout": "done", "stderr": "", "activity": ""}
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
                "exit_code": 0, "stdout": "done", "stderr": "", "activity": ""
            }
        )

        def capture(stdout: str, activity: str) -> None:
            output_calls.append((stdout, activity))

        execute_task(task, run_repo, runner=mock_runner, on_output=capture)
        mock_runner.assert_called_once()


# ── execute_task_background ────────────────────────────────────


class TestExecuteTaskBg:
    def test_returns_running(self, task_svc, session_factory):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={"exit_code": 0, "stdout": "done", "stderr": "", "activity": ""}
        )
        run = execute_task_background(task, session_factory, runner=mock_runner)
        assert run.status == "running"
        time.sleep(0.1)
        # Verify completion in a fresh session
        session = session_factory()
        completed = RunRepo(session).get(run.id)
        assert completed.status == "success"
        session.close()
```

### `tests/test_api_tasks.py`

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.routers.tasks import router


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_create_task(client):
    resp = client.post("/api/tasks", json={
        "name": "Test", "prompt": "Do it"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test"
    assert data["id"]


def test_list_tasks(client):
    client.post("/api/tasks", json={"name": "A", "prompt": "p"})
    client.post("/api/tasks", json={"name": "B", "prompt": "p"})
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_task(client):
    create = client.post("/api/tasks", json={"name": "X", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "X"


def test_get_task_not_found(client):
    resp = client.get("/api/tasks/nonexistent")
    assert resp.status_code == 404


def test_update_task(client):
    create = client.post("/api/tasks", json={"name": "Old", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.put(f"/api/tasks/{task_id}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_delete_task(client):
    create = client.post("/api/tasks", json={"name": "Gone", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
```

### `tests/test_api_runs.py`

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crud import TaskRepo, RunRepo
from app.db import get_db
from app.routers.runs import router


@pytest.fixture
def repos(db_session):
    return TaskRepo(db_session), RunRepo(db_session)


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def task_with_runs(repos):
    task_repo, run_repo = repos
    task = task_repo.create(name="T", prompt="p")
    r1 = run_repo.create(task_id=task.id, trigger="manual")
    run_repo.complete(r1.id, status="success", stdout="ok", stderr="", exit_code=0)
    r2 = run_repo.create(task_id=task.id, trigger="cron")
    return task, r1, r2


def test_list_runs_for_task(client, task_with_runs):
    task, _, _ = task_with_runs
    resp = client.get(f"/api/runs?task_id={task.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_all_runs(client, task_with_runs):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_run(client, task_with_runs):
    _, r1, _ = task_with_runs
    resp = client.get(f"/api/runs/{r1.id}")
    assert resp.status_code == 200
    assert resp.json()["trigger"] == "manual"


def test_get_run_not_found(client):
    resp = client.get("/api/runs/nonexistent")
    assert resp.status_code == 404
```

### `tests/test_api_triggers.py`

```python
import time

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crud import TaskRepo, RunRepo
from app.db import get_db
from app.routers.triggers import router, get_session_factory, get_runner


@pytest.fixture
def repos(db_session):
    return TaskRepo(db_session), RunRepo(db_session)


@pytest.fixture
def app(db_session, session_factory):
    app = FastAPI()
    app.include_router(router)

    mock_runner = MagicMock(
        return_value={"exit_code": 0, "stdout": "done", "stderr": "", "activity": ""}
    )

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_runner] = lambda: mock_runner
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_manual_trigger(client, repos, session_factory):
    task_repo, _ = repos
    task = task_repo.create(name="T", prompt="Run me")
    resp = client.post(f"/api/tasks/{task.id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["trigger"] == "manual"
    # Wait for background thread
    time.sleep(0.1)
    session = session_factory()
    run = RunRepo(session).get(data["id"])
    assert run.status == "success"
    session.close()


def test_manual_trigger_not_found(client):
    resp = client.post("/api/tasks/nonexistent/run")
    assert resp.status_code == 404


def test_webhook_trigger(client, repos, session_factory):
    task_repo, _ = repos
    task_repo.create(name="my-webhook", prompt="Webhook prompt")
    resp = client.post("/api/trigger/my-webhook")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["trigger"] == "webhook"
    time.sleep(0.1)
    session = session_factory()
    run = RunRepo(session).get(data["id"])
    assert run.status == "success"
    session.close()


def test_webhook_trigger_not_found(client):
    resp = client.post("/api/trigger/no-such-task")
    assert resp.status_code == 404
```

### `tests/test_cli.py`

```python
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from app.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_db(db_path):
    """Patch DB_PATH so CLI uses the test database."""
    with patch("app.cli.DB_PATH", db_path):
        from app.db import init_db
        init_db(db_path)
        yield


class TestTaskCommands:
    def test_list_empty(self, runner, mock_db):
        result = runner.invoke(cli, ["tasks", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output

    def test_create_and_list(self, runner, mock_db):
        result = runner.invoke(
            cli, ["tasks", "create", "--name", "Test Task", "--prompt", "Do it"]
        )
        assert result.exit_code == 0
        assert "Created task: Test Task" in result.output

        result = runner.invoke(cli, ["tasks", "list"])
        assert result.exit_code == 0
        assert "Test Task" in result.output

    def test_create_with_options(self, runner, mock_db):
        result = runner.invoke(
            cli,
            [
                "tasks", "create",
                "--name", "Cron Task",
                "--prompt", "Run daily",
                "--cron", "0 8 * * 1-5",
                "--tools", "Bash,Read",
                "--disabled",
            ],
        )
        assert result.exit_code == 0
        assert "Created task: Cron Task" in result.output

    def test_show(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Show Me", "--prompt", "p"]
        )
        result = runner.invoke(cli, ["tasks", "show", "Show Me"])
        assert result.exit_code == 0
        assert "Name:    Show Me" in result.output
        assert "Prompt:  p" in result.output

    def test_show_json(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "JSON Task", "--prompt", "p"]
        )
        result = runner.invoke(cli, ["tasks", "show", "JSON Task", "--json"])
        assert result.exit_code == 0
        assert "JSON Task" in result.output

    def test_list_json(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "A", "--prompt", "p"]
        )
        result = runner.invoke(cli, ["tasks", "list", "--json"])
        assert result.exit_code == 0
        assert '"name"' in result.output

    def test_edit(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Old Name", "--prompt", "p"]
        )
        result = runner.invoke(
            cli, ["tasks", "edit", "Old Name", "--name", "New Name"]
        )
        assert result.exit_code == 0
        assert "Updated task: New Name" in result.output

    def test_delete_with_confirm(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Doomed", "--prompt", "p"]
        )
        result = runner.invoke(cli, ["tasks", "delete", "Doomed", "-y"])
        assert result.exit_code == 0
        assert "Deleted task: Doomed" in result.output

        result = runner.invoke(cli, ["tasks", "list"])
        assert "No tasks" in result.output

    def test_show_not_found(self, runner, mock_db):
        result = runner.invoke(cli, ["tasks", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestRunCommands:
    def test_list_empty(self, runner, mock_db):
        result = runner.invoke(cli, ["runs", "list"])
        assert result.exit_code == 0
        assert "No runs" in result.output

    def test_list_with_task_filter(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Filterable", "--prompt", "p"]
        )
        result = runner.invoke(cli, ["runs", "list", "--task", "Filterable"])
        assert result.exit_code == 0
        assert "No runs" in result.output


class TestRunExecution:
    def test_run_task(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Runnable", "--prompt", "Hello"]
        )
        with patch("app.services.run_claude") as mock_claude:
            mock_claude.return_value = {
                "exit_code": 0,
                "stdout": "Hello from Claude",
                "stderr": "",
                "activity": "[Bash] echo hi",
            }
            result = runner.invoke(cli, ["run", "Runnable"])
            assert result.exit_code == 0
            assert "Status: success" in result.output

    def test_run_task_failure(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Failing", "--prompt", "fail"]
        )
        with patch("app.services.run_claude") as mock_claude:
            mock_claude.return_value = {
                "exit_code": 1,
                "stdout": "",
                "stderr": "error occurred",
                "activity": "",
            }
            result = runner.invoke(cli, ["run", "Failing"])
            assert result.exit_code == 1
            assert "Status: failed" in result.output

    def test_run_task_not_found(self, runner, mock_db):
        result = runner.invoke(cli, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output
```

### `tests/test_scheduler.py` — update for ORM attribute access

```python
from types import SimpleNamespace
from unittest.mock import MagicMock
from app.scheduler import sync_jobs


def _make_task(**kwargs):
    """Create a task-like object with attribute access."""
    defaults = {"id": "abc", "name": "T", "prompt": "p",
                "cron_expression": None, "allowed_tools": None, "enabled": True}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_sync_adds_enabled_cron_tasks():
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []
    tasks = [_make_task(cron_expression="0 8 * * *")]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.add_job.assert_called_once()
    call_kwargs = scheduler.add_job.call_args
    assert call_kwargs.kwargs["id"] == "abc"


def test_sync_removes_disabled_tasks():
    job = MagicMock()
    job.id = "abc"
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [job]
    tasks = [_make_task(cron_expression="0 8 * * *", enabled=False)]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.remove_job.assert_called_once_with("abc")


def test_sync_removes_jobs_for_deleted_tasks():
    job = MagicMock()
    job.id = "deleted-task"
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [job]
    sync_jobs(scheduler, tasks=[], execute_fn=MagicMock())
    scheduler.remove_job.assert_called_once_with("deleted-task")


def test_sync_skips_tasks_without_cron():
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []
    tasks = [_make_task()]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.add_job.assert_not_called()
```

**Step: Run full test suite**

Run: `source .venv/bin/activate && pytest --tb=short -q`
Expected: All tests pass (≥76, plus new `--json` tests)

**Commit:** `test: migrate all tests to SQLAlchemy sessions`

---

## Task 10: Clean up old files and final verification

**Files:**
- Delete: `app/models.py` (replaced by `app/models/` package)
- Delete: `app/repository.py` (replaced by `app/crud/` package)
- Delete: `tests/test_repository.py` (replaced by `tests/test_crud.py`)

**Step 1: Delete old files**

```bash
rm app/models.py app/repository.py tests/test_repository.py
```

**Step 2: Run full test suite**

Run: `source .venv/bin/activate && pytest --tb=short -q`
Expected: All tests pass

**Step 3: Run linter and formatter**

Run: `uvx ruff check --fix . && uvx ruff format .`

**Step 4: Verify imports have no stale references**

Run: `rg "from app.repository" app/ tests/` — should find nothing
Run: `rg "from app.models import" app/ tests/` — should only find `from app.models import` (package), not the old file
Run: `rg "import sqlite3" app/` — should find nothing (sqlite3 gone from app code)

**Commit:** `refactor: remove old sqlite3 repository and flat models file`

---

## Summary of new file structure

```
app/
  models/
    __init__.py          # Re-exports Base, Task, Run, schemas
    database.py          # SQLAlchemy ORM: Task, Run (own table definitions)
    schemas.py           # Pydantic: TaskCreate, TaskUpdate, TaskResponse, RunResponse
  crud/
    __init__.py          # Re-exports TaskRepo, RunRepo
    tasks.py             # TaskRepo(Session)
    runs.py              # RunRepo(Session)
  routers/
    __init__.py          # (unchanged)
    tasks.py             # Updated imports + get_db dependency
    runs.py              # Updated imports + get_db dependency
    triggers.py          # Updated + session_factory for background execution
    ui.py                # Updated + Pydantic conversion for template context
  __init__.py            # (unchanged)
  cli.py                 # Updated + rich tables + --json flag
  config.py              # (unchanged)
  db.py                  # Rewritten: SQLAlchemy engine/session management
  main.py                # Rewritten: simplified lifespan, no dependency_overrides
  runner.py              # (unchanged)
  scheduler.py           # Attribute access instead of dict keys
  services.py            # ORM objects + session_factory for background
```

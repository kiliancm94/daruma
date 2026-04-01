# Claude Automations Runner — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Docker-based task scheduler with a web UI that runs Claude CLI agents on cron schedules, manual triggers, or webhooks.

**Architecture:** FastAPI serves both a JSON API and Jinja2+HTMX UI. APScheduler runs in-process for cron. Tasks and run history live in SQLite. Claude CLI runs as subprocess per execution. Single container, single user.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX, SQLite (stdlib sqlite3), APScheduler, Docker

**Reference:** `claude-runner-design.md` at project root.

---

## Project Structure

```
daruma/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, lifespan, scheduler wiring
│   ├── config.py          # Settings (DB path, port)
│   ├── db.py              # SQLite connection + schema init
│   ├── models.py          # Pydantic schemas
│   ├── repository.py      # All DB queries
│   ├── runner.py          # Claude CLI subprocess wrapper
│   ├── scheduler.py       # APScheduler setup + job sync
│   └── routers/
│       ├── __init__.py
│       ├── tasks.py       # Task CRUD API
│       ├── runs.py        # Run history API
│       ├── triggers.py    # Manual + webhook triggers
│       └── ui.py          # Jinja2 template routes
├── templates/
│   ├── base.html
│   ├── tasks_list.html
│   ├── task_detail.html
│   ├── task_form.html
│   ├── run_detail.html
│   └── partials/
│       ├── task_row.html
│       └── run_row.html
├── static/
│   └── style.css
└── tests/
    ├── conftest.py
    ├── test_db.py
    ├── test_repository.py
    ├── test_runner.py
    ├── test_api_tasks.py
    ├── test_api_runs.py
    ├── test_api_triggers.py
    └── test_scheduler.py
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `tests/__init__.py` (empty)

**Step 1: Create `pyproject.toml`**

```toml
[project]
name = "daruma"
version = "0.1.0"
description = "Docker-based task scheduler for Claude CLI automations"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.18",
    "apscheduler>=3.10.0,<4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
    "pytest-asyncio>=0.24",
]
```

**Step 2: Create `app/config.py`**

```python
from pathlib import Path

DATA_DIR = Path("/data")
DB_PATH = DATA_DIR / "automations.db"
PORT = 8080
```

**Step 3: Create `app/__init__.py`**

```python
```

(Empty file.)

**Step 4: Create `tests/__init__.py`**

```python
```

(Empty file.)

**Step 5: Install dependencies**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv sync --all-extras`

**Step 6: Commit**

```bash
git init
git add pyproject.toml app/__init__.py app/config.py tests/__init__.py
git commit -m "scaffold: project setup with dependencies"
```

---

## Task 2: Database Layer

**Files:**
- Create: `app/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db.py`

**Step 1: Write the failing test**

Create `tests/conftest.py`:

```python
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def db_conn(db_path: Path) -> sqlite3.Connection:
    from app.db import init_db

    conn = init_db(db_path)
    yield conn
    conn.close()
```

Create `tests/test_db.py`:

```python
import sqlite3


def test_init_db_creates_tables(db_conn: sqlite3.Connection):
    cursor = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "tasks" in tables
    assert "runs" in tables


def test_tasks_table_has_expected_columns(db_conn: sqlite3.Connection):
    cursor = db_conn.execute("PRAGMA table_info(tasks)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {
        "id", "name", "prompt", "cron_expression",
        "allowed_tools", "enabled", "created_at", "updated_at",
    }


def test_runs_table_has_expected_columns(db_conn: sqlite3.Connection):
    cursor = db_conn.execute("PRAGMA table_info(runs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert columns == {
        "id", "task_id", "trigger", "status", "started_at",
        "finished_at", "duration_ms", "stdout", "stderr", "exit_code",
    }
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError` for `app.db`

**Step 3: Write `app/db.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    cron_expression TEXT,
    allowed_tools   TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    task_id      TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    trigger      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'running',
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    duration_ms  INTEGER,
    stdout       TEXT,
    stderr       TEXT,
    exit_code    INTEGER
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add app/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: database layer with tasks and runs schema"
```

---

## Task 3: Pydantic Models

**Files:**
- Create: `app/models.py`

**Step 1: Create `app/models.py`**

```python
from datetime import datetime
from pydantic import BaseModel


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
    id: str
    name: str
    prompt: str
    cron_expression: str | None
    allowed_tools: str | None
    enabled: bool
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
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
```

**Step 2: Commit**

```bash
git add app/models.py
git commit -m "feat: pydantic request/response models"
```

---

## Task 4: Repository — Task CRUD

**Files:**
- Create: `app/repository.py`
- Create: `tests/test_repository.py`

**Step 1: Write failing tests**

Create `tests/test_repository.py`:

```python
import pytest
from app.repository import TaskRepo, RunRepo


class TestTaskRepo:
    def test_create_and_get(self, db_conn):
        repo = TaskRepo(db_conn)
        task = repo.create(
            name="Test Task",
            prompt="Do something",
            cron_expression="0 * * * *",
            allowed_tools="bash,read",
            enabled=True,
        )
        assert task["name"] == "Test Task"
        assert task["prompt"] == "Do something"
        assert task["cron_expression"] == "0 * * * *"
        assert task["enabled"] == 1

        fetched = repo.get(task["id"])
        assert fetched is not None
        assert fetched["id"] == task["id"]

    def test_list_tasks(self, db_conn):
        repo = TaskRepo(db_conn)
        repo.create(name="A", prompt="p1")
        repo.create(name="B", prompt="p2")
        tasks = repo.list()
        assert len(tasks) == 2

    def test_update_task(self, db_conn):
        repo = TaskRepo(db_conn)
        task = repo.create(name="Old", prompt="p")
        updated = repo.update(task["id"], name="New", enabled=False)
        assert updated["name"] == "New"
        assert updated["enabled"] == 0

    def test_delete_task(self, db_conn):
        repo = TaskRepo(db_conn)
        task = repo.create(name="Doomed", prompt="p")
        assert repo.delete(task["id"]) is True
        assert repo.get(task["id"]) is None

    def test_get_nonexistent_returns_none(self, db_conn):
        repo = TaskRepo(db_conn)
        assert repo.get("nonexistent") is None

    def test_delete_nonexistent_returns_false(self, db_conn):
        repo = TaskRepo(db_conn)
        assert repo.delete("nonexistent") is False

    def test_get_by_name(self, db_conn):
        repo = TaskRepo(db_conn)
        repo.create(name="Webhook Task", prompt="p")
        found = repo.get_by_name("Webhook Task")
        assert found is not None
        assert found["name"] == "Webhook Task"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repository.py::TestTaskRepo -v`
Expected: FAIL — `ImportError`

**Step 3: Implement `TaskRepo` in `app/repository.py`**

```python
import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


class TaskRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        enabled: bool = True,
    ) -> dict:
        task_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            """INSERT INTO tasks (id, name, prompt, cron_expression, allowed_tools, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, name, prompt, cron_expression, allowed_tools, int(enabled), now, now),
        )
        self.conn.commit()
        return _row_to_dict(self.get(task_id))

    def get(self, task_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_dict(row)

    def get_by_name(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE name = ?", (name,)).fetchone()
        return _row_to_dict(row)

    def list(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def update(self, task_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(task_id)
        # Convert bool enabled to int
        if "enabled" in fields and fields["enabled"] is not None:
            fields["enabled"] = int(fields["enabled"])
        # Filter out None values
        updates = {k: v for k, v in fields.items() if v is not None}
        if not updates:
            return self.get(task_id)
        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        self.conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        self.conn.commit()
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_repository.py::TestTaskRepo -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: task repository with CRUD operations"
```

---

## Task 5: Repository — Run Operations

**Files:**
- Modify: `app/repository.py` — add `RunRepo` class
- Modify: `tests/test_repository.py` — add `TestRunRepo` class

**Step 1: Write failing tests**

Append to `tests/test_repository.py`:

```python
class TestRunRepo:
    def _make_task(self, db_conn) -> dict:
        return TaskRepo(db_conn).create(name="T", prompt="p")

    def test_create_and_get_run(self, db_conn):
        task = self._make_task(db_conn)
        repo = RunRepo(db_conn)
        run = repo.create(task_id=task["id"], trigger="manual")
        assert run["status"] == "running"
        assert run["trigger"] == "manual"
        assert run["task_id"] == task["id"]

        fetched = repo.get(run["id"])
        assert fetched["id"] == run["id"]

    def test_complete_run_success(self, db_conn):
        task = self._make_task(db_conn)
        repo = RunRepo(db_conn)
        run = repo.create(task_id=task["id"], trigger="cron")
        updated = repo.complete(
            run["id"], status="success", stdout="output", stderr="", exit_code=0
        )
        assert updated["status"] == "success"
        assert updated["stdout"] == "output"
        assert updated["exit_code"] == 0
        assert updated["finished_at"] is not None
        assert updated["duration_ms"] is not None

    def test_complete_run_failed(self, db_conn):
        task = self._make_task(db_conn)
        repo = RunRepo(db_conn)
        run = repo.create(task_id=task["id"], trigger="webhook")
        updated = repo.complete(
            run["id"], status="failed", stdout="", stderr="error", exit_code=1
        )
        assert updated["status"] == "failed"
        assert updated["exit_code"] == 1

    def test_list_runs_for_task(self, db_conn):
        task = self._make_task(db_conn)
        repo = RunRepo(db_conn)
        repo.create(task_id=task["id"], trigger="manual")
        repo.create(task_id=task["id"], trigger="cron")
        runs = repo.list(task_id=task["id"])
        assert len(runs) == 2

    def test_list_runs_all(self, db_conn):
        task = self._make_task(db_conn)
        repo = RunRepo(db_conn)
        repo.create(task_id=task["id"], trigger="manual")
        runs = repo.list()
        assert len(runs) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repository.py::TestRunRepo -v`
Expected: FAIL — `ImportError` for `RunRepo`

**Step 3: Add `RunRepo` to `app/repository.py`**

```python
class RunRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, task_id: str, trigger: str) -> dict:
        run_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            """INSERT INTO runs (id, task_id, trigger, status, started_at)
               VALUES (?, ?, ?, 'running', ?)""",
            (run_id, task_id, trigger, now),
        )
        self.conn.commit()
        return _row_to_dict(self.get(run_id))

    def get(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_dict(row)

    def complete(
        self, run_id: str, status: str, stdout: str, stderr: str, exit_code: int
    ) -> dict | None:
        now = _now()
        run = self.get(run_id)
        if run is None:
            return None
        started = datetime.fromisoformat(run["started_at"])
        finished = datetime.fromisoformat(now)
        duration_ms = int((finished - started).total_seconds() * 1000)
        self.conn.execute(
            """UPDATE runs
               SET status = ?, finished_at = ?, duration_ms = ?,
                   stdout = ?, stderr = ?, exit_code = ?
               WHERE id = ?""",
            (status, now, duration_ms, stdout, stderr, exit_code, run_id),
        )
        self.conn.commit()
        return _row_to_dict(self.get(run_id))

    def list(self, task_id: str | None = None) -> list[dict]:
        if task_id:
            rows = self.conn.execute(
                "SELECT * FROM runs WHERE task_id = ? ORDER BY started_at DESC",
                (task_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_repository.py -v`
Expected: 12 passed

**Step 5: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: run repository with create, complete, list"
```

---

## Task 6: Claude CLI Runner

**Files:**
- Create: `app/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write failing tests**

Create `tests/test_runner.py`:

```python
from unittest.mock import patch, MagicMock
from app.runner import run_claude


def _make_completed_process(returncode=0, stdout="response", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@patch("app.runner.subprocess.run")
def test_run_claude_success(mock_run):
    mock_run.return_value = _make_completed_process(
        returncode=0, stdout="Hello from Claude"
    )
    result = run_claude("Say hello", allowed_tools=None)
    assert result["exit_code"] == 0
    assert result["stdout"] == "Hello from Claude"
    assert result["stderr"] == ""
    # Verify correct command
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"
    assert "-p" in cmd


@patch("app.runner.subprocess.run")
def test_run_claude_with_tools(mock_run):
    mock_run.return_value = _make_completed_process()
    run_claude("Do stuff", allowed_tools="bash,read")
    cmd = mock_run.call_args[0][0]
    assert "--allowedTools" in cmd
    tools_idx = cmd.index("--allowedTools")
    assert cmd[tools_idx + 1] == "bash,read"


@patch("app.runner.subprocess.run")
def test_run_claude_failure(mock_run):
    mock_run.return_value = _make_completed_process(
        returncode=1, stdout="", stderr="Error occurred"
    )
    result = run_claude("Fail please")
    assert result["exit_code"] == 1
    assert result["stderr"] == "Error occurred"


@patch("app.runner.subprocess.run")
def test_run_claude_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)
    result = run_claude("Slow task")
    assert result["exit_code"] == -1
    assert "timeout" in result["stderr"].lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement `app/runner.py`**

```python
import subprocess


def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    timeout: int = 300,
) -> dict:
    cmd = ["claude", "-p", prompt]
    if allowed_tools:
        cmd.extend(["--allowedTools", allowed_tools])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
        }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runner.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/runner.py tests/test_runner.py
git commit -m "feat: claude CLI runner with subprocess and timeout handling"
```

---

## Task 7: API — Task CRUD Endpoints

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/tasks.py`
- Create: `tests/test_api_tasks.py`

**Step 1: Write failing tests**

Create `tests/test_api_tasks.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import init_db
from app.repository import TaskRepo
from app.routers.tasks import router, get_task_repo


@pytest.fixture
def app(db_conn):
    app = FastAPI()
    app.include_router(router)

    def override_repo():
        return TaskRepo(db_conn)

    app.dependency_overrides[get_task_repo] = override_repo
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

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_tasks.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement `app/routers/tasks.py`**

Create `app/routers/__init__.py` (empty).

Create `app/routers/tasks.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import TaskCreate, TaskUpdate, TaskResponse
from app.repository import TaskRepo

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Placeholder dependency — overridden in main app and tests
def get_task_repo() -> TaskRepo:
    raise RuntimeError("task_repo dependency not configured")


@router.get("", response_model=list[TaskResponse])
def list_tasks(repo: TaskRepo = Depends(get_task_repo)):
    return repo.list()


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreate, repo: TaskRepo = Depends(get_task_repo)):
    return repo.create(
        name=body.name,
        prompt=body.prompt,
        cron_expression=body.cron_expression,
        allowed_tools=body.allowed_tools,
        enabled=body.enabled,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, repo: TaskRepo = Depends(get_task_repo)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, body: TaskUpdate, repo: TaskRepo = Depends(get_task_repo)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return repo.update(task_id, **body.model_dump(exclude_unset=True))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, repo: TaskRepo = Depends(get_task_repo)):
    if not repo.delete(task_id):
        raise HTTPException(404, "Task not found")
    return Response(status_code=204)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_tasks.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add app/routers/__init__.py app/routers/tasks.py tests/test_api_tasks.py
git commit -m "feat: task CRUD API endpoints"
```

---

## Task 8: API — Run History Endpoints

**Files:**
- Create: `app/routers/runs.py`
- Create: `tests/test_api_runs.py`

**Step 1: Write failing tests**

Create `tests/test_api_runs.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import init_db
from app.repository import TaskRepo, RunRepo
from app.routers.runs import router, get_run_repo


@pytest.fixture
def repos(db_conn):
    return TaskRepo(db_conn), RunRepo(db_conn)


@pytest.fixture
def app(repos):
    app = FastAPI()
    app.include_router(router)
    _, run_repo = repos
    app.dependency_overrides[get_run_repo] = lambda: run_repo
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def task_with_runs(repos):
    task_repo, run_repo = repos
    task = task_repo.create(name="T", prompt="p")
    r1 = run_repo.create(task_id=task["id"], trigger="manual")
    run_repo.complete(r1["id"], status="success", stdout="ok", stderr="", exit_code=0)
    r2 = run_repo.create(task_id=task["id"], trigger="cron")
    return task, r1, r2


def test_list_runs_for_task(client, task_with_runs):
    task, _, _ = task_with_runs
    resp = client.get(f"/api/runs?task_id={task['id']}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_all_runs(client, task_with_runs):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_run(client, task_with_runs):
    _, r1, _ = task_with_runs
    resp = client.get(f"/api/runs/{r1['id']}")
    assert resp.status_code == 200
    assert resp.json()["trigger"] == "manual"


def test_get_run_not_found(client):
    resp = client.get("/api/runs/nonexistent")
    assert resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_runs.py -v`
Expected: FAIL

**Step 3: Implement `app/routers/runs.py`**

```python
from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import RunRepo

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_repo() -> RunRepo:
    raise RuntimeError("run_repo dependency not configured")


@router.get("", response_model=list[RunResponse])
def list_runs(task_id: str | None = None, repo: RunRepo = Depends(get_run_repo)):
    return repo.list(task_id=task_id)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, repo: RunRepo = Depends(get_run_repo)):
    run = repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_runs.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/routers/runs.py tests/test_api_runs.py
git commit -m "feat: run history API endpoints"
```

---

## Task 9: API — Trigger Endpoints (Manual + Webhook)

**Files:**
- Create: `app/routers/triggers.py`
- Create: `tests/test_api_triggers.py`

**Step 1: Write failing tests**

Create `tests/test_api_triggers.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.repository import TaskRepo, RunRepo
from app.routers.triggers import router, get_task_repo, get_run_repo, get_runner


@pytest.fixture
def repos(db_conn):
    return TaskRepo(db_conn), RunRepo(db_conn)


@pytest.fixture
def app(repos):
    app = FastAPI()
    app.include_router(router)
    task_repo, run_repo = repos

    mock_runner = MagicMock(return_value={"exit_code": 0, "stdout": "done", "stderr": ""})

    app.dependency_overrides[get_task_repo] = lambda: task_repo
    app.dependency_overrides[get_run_repo] = lambda: run_repo
    app.dependency_overrides[get_runner] = lambda: mock_runner
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_manual_trigger(client, repos):
    task_repo, _ = repos
    task = task_repo.create(name="T", prompt="Run me")
    resp = client.post(f"/api/tasks/{task['id']}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["trigger"] == "manual"


def test_manual_trigger_not_found(client):
    resp = client.post("/api/tasks/nonexistent/run")
    assert resp.status_code == 404


def test_webhook_trigger(client, repos):
    task_repo, _ = repos
    task_repo.create(name="my-webhook", prompt="Webhook prompt")
    resp = client.post("/api/trigger/my-webhook")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trigger"] == "webhook"


def test_webhook_trigger_not_found(client):
    resp = client.post("/api/trigger/no-such-task")
    assert resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_triggers.py -v`
Expected: FAIL

**Step 3: Implement `app/routers/triggers.py`**

```python
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import TaskRepo, RunRepo
from app.runner import run_claude

router = APIRouter(tags=["triggers"])


def get_task_repo() -> TaskRepo:
    raise RuntimeError("not configured")


def get_run_repo() -> RunRepo:
    raise RuntimeError("not configured")


def get_runner() -> Callable:
    return run_claude


def _execute_task(
    task: dict, trigger: str, run_repo: RunRepo, runner: Callable
) -> dict:
    run = run_repo.create(task_id=task["id"], trigger=trigger)
    result = runner(task["prompt"], allowed_tools=task.get("allowed_tools"))
    status = "success" if result["exit_code"] == 0 else "failed"
    return run_repo.complete(
        run["id"],
        status=status,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
    )


@router.post("/api/tasks/{task_id}/run", response_model=RunResponse)
def manual_trigger(
    task_id: str,
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    task = task_repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return _execute_task(task, "manual", run_repo, runner)


@router.post("/api/trigger/{task_name}", response_model=RunResponse)
def webhook_trigger(
    task_name: str,
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    task = task_repo.get_by_name(task_name)
    if not task:
        raise HTTPException(404, "Task not found")
    return _execute_task(task, "webhook", run_repo, runner)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_triggers.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/routers/triggers.py tests/test_api_triggers.py
git commit -m "feat: manual and webhook trigger endpoints"
```

---

## Task 10: APScheduler Integration

**Files:**
- Create: `app/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1: Write failing tests**

Create `tests/test_scheduler.py`:

```python
from unittest.mock import MagicMock, patch
from app.scheduler import sync_jobs


def test_sync_adds_enabled_cron_tasks():
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []
    tasks = [
        {"id": "abc", "name": "T", "prompt": "p", "cron_expression": "0 8 * * *",
         "allowed_tools": None, "enabled": 1},
    ]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.add_job.assert_called_once()
    call_kwargs = scheduler.add_job.call_args
    assert call_kwargs.kwargs["id"] == "abc"


def test_sync_removes_disabled_tasks():
    job = MagicMock()
    job.id = "abc"
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [job]
    tasks = [
        {"id": "abc", "name": "T", "prompt": "p", "cron_expression": "0 8 * * *",
         "allowed_tools": None, "enabled": 0},
    ]
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
    tasks = [
        {"id": "abc", "name": "T", "prompt": "p", "cron_expression": None,
         "allowed_tools": None, "enabled": 1},
    ]
    sync_jobs(scheduler, tasks, execute_fn=MagicMock())
    scheduler.add_job.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: FAIL

**Step 3: Implement `app/scheduler.py`**

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


def create_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler()


def sync_jobs(
    scheduler: BackgroundScheduler,
    tasks: list[dict],
    execute_fn,
) -> None:
    existing_job_ids = {job.id for job in scheduler.get_jobs()}
    desired_job_ids = set()

    for task in tasks:
        if not task["cron_expression"] or not task["enabled"]:
            continue
        desired_job_ids.add(task["id"])

    # Remove jobs that should no longer exist
    for job_id in existing_job_ids:
        if job_id not in desired_job_ids:
            scheduler.remove_job(job_id)

    # Add jobs that don't exist yet
    for task in tasks:
        if task["id"] not in desired_job_ids:
            continue
        if task["id"] in existing_job_ids:
            continue
        parts = task["cron_expression"].split()
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        scheduler.add_job(
            execute_fn,
            trigger=trigger,
            args=[task["id"]],
            id=task["id"],
            name=task["name"],
            replace_existing=True,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add app/scheduler.py tests/test_scheduler.py
git commit -m "feat: APScheduler integration with job sync"
```

---

## Task 11: Main App Assembly + Health Check

**Files:**
- Create: `app/main.py`

**Step 1: Implement `app/main.py`**

```python
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import DB_PATH
from app.db import init_db
from app.repository import TaskRepo, RunRepo
from app.runner import run_claude
from app.scheduler import create_scheduler, sync_jobs
from app.routers import tasks as tasks_router
from app.routers import runs as runs_router
from app.routers import triggers as triggers_router

_conn = None
_scheduler = None


def _execute_cron_task(task_id: str) -> None:
    task_repo = TaskRepo(_conn)
    run_repo = RunRepo(_conn)
    task = task_repo.get(task_id)
    if not task:
        return
    run = run_repo.create(task_id=task["id"], trigger="cron")
    result = run_claude(task["prompt"], allowed_tools=task.get("allowed_tools"))
    status = "success" if result["exit_code"] == 0 else "failed"
    run_repo.complete(
        run["id"], status=status,
        stdout=result["stdout"], stderr=result["stderr"],
        exit_code=result["exit_code"],
    )


def _refresh_scheduler() -> None:
    if _conn and _scheduler:
        tasks = TaskRepo(_conn).list()
        sync_jobs(_scheduler, tasks, _execute_cron_task)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn, _scheduler
    _conn = init_db(DB_PATH)
    _scheduler = create_scheduler()

    # Wire up dependency overrides
    app.dependency_overrides[tasks_router.get_task_repo] = lambda: TaskRepo(_conn)
    app.dependency_overrides[runs_router.get_run_repo] = lambda: RunRepo(_conn)
    app.dependency_overrides[triggers_router.get_task_repo] = lambda: TaskRepo(_conn)
    app.dependency_overrides[triggers_router.get_run_repo] = lambda: RunRepo(_conn)
    app.dependency_overrides[triggers_router.get_runner] = lambda: run_claude

    _refresh_scheduler()
    _scheduler.start()
    yield
    _scheduler.shutdown()
    _conn.close()


app = FastAPI(title="Daruma — Claude Automations Runner", lifespan=lifespan)

app.include_router(tasks_router.router)
app.include_router(runs_router.router)
app.include_router(triggers_router.router)

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 2: Smoke test**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run python -c "from app.main import app; print('App created:', app.title)"`
Expected: `App created: Daruma — Claude Automations Runner`

**Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All previously passing tests still pass

**Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: main app assembly with lifespan, health check, dependency wiring"
```

---

## Task 12: UI — Base Template + Tasks List

**Files:**
- Create: `templates/base.html`
- Create: `templates/tasks_list.html`
- Create: `templates/partials/task_row.html`
- Create: `static/style.css`
- Create: `app/routers/ui.py`

**Step 1: Create `static/style.css`**

```css
:root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e2e4e9;
    --text-dim: #8b8fa3;
    --accent: #6c5ce7;
    --accent-hover: #7c6df7;
    --success: #2ecc71;
    --danger: #e74c3c;
    --warning: #f39c12;
    --radius: 8px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
}
.container { max-width: 960px; margin: 0 auto; padding: 2rem 1rem; }
h1 { font-size: 1.5rem; margin-bottom: 1.5rem; }
h2 { font-size: 1.2rem; margin-bottom: 1rem; }
a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); }

/* Header */
.header { border-bottom: 1px solid var(--border); padding: 1rem 0; margin-bottom: 2rem; }
.header .container { display: flex; justify-content: space-between; align-items: center; }
.logo { font-weight: 700; font-size: 1.2rem; }

/* Table */
table { width: 100%; border-collapse: collapse; }
th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--text-dim); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
tr:hover { background: var(--surface); }

/* Badges */
.badge {
    display: inline-block; padding: 0.15rem 0.5rem; border-radius: 99px;
    font-size: 0.75rem; font-weight: 600;
}
.badge-success { background: rgba(46,204,113,0.15); color: var(--success); }
.badge-danger { background: rgba(231,76,60,0.15); color: var(--danger); }
.badge-warning { background: rgba(243,156,18,0.15); color: var(--warning); }
.badge-dim { background: rgba(139,143,163,0.15); color: var(--text-dim); }

/* Buttons */
.btn {
    display: inline-block; padding: 0.4rem 1rem; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface); color: var(--text);
    cursor: pointer; font-size: 0.85rem; transition: all 0.15s;
}
.btn:hover { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-sm { padding: 0.25rem 0.6rem; font-size: 0.78rem; }
.btn-danger { border-color: var(--danger); color: var(--danger); }
.btn-danger:hover { background: var(--danger); color: #fff; }

/* Forms */
.form-group { margin-bottom: 1.25rem; }
label { display: block; margin-bottom: 0.35rem; font-size: 0.85rem; color: var(--text-dim); }
input, textarea, select {
    width: 100%; padding: 0.6rem 0.8rem; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface); color: var(--text);
    font-family: inherit; font-size: 0.9rem;
}
textarea { min-height: 120px; resize: vertical; }
input:focus, textarea:focus { outline: none; border-color: var(--accent); }

/* Toggle */
.toggle { cursor: pointer; }

/* Card */
.card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 1.5rem; margin-bottom: 1rem;
}

/* Log output */
.log-output {
    background: #000; color: #ddd; padding: 1rem; border-radius: var(--radius);
    font-family: "SF Mono", "Fira Code", monospace; font-size: 0.82rem;
    white-space: pre-wrap; word-break: break-word; max-height: 500px; overflow-y: auto;
}

/* Utilities */
.text-dim { color: var(--text-dim); }
.text-sm { font-size: 0.82rem; }
.mt-1 { margin-top: 1rem; }
.flex-between { display: flex; justify-content: space-between; align-items: center; }
```

**Step 2: Create `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Daruma{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
    <div class="header">
        <div class="container flex-between">
            <a href="/ui/" class="logo">Daruma</a>
            <span class="text-dim text-sm">Claude Automations Runner</span>
        </div>
    </div>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

**Step 3: Create `templates/partials/task_row.html`**

```html
<tr id="task-{{ task.id }}">
    <td><a href="/ui/tasks/{{ task.id }}">{{ task.name }}</a></td>
    <td class="text-dim text-sm">{{ task.cron_expression or "—" }}</td>
    <td>
        {% if task.enabled %}
            <span class="badge badge-success">enabled</span>
        {% else %}
            <span class="badge badge-dim">disabled</span>
        {% endif %}
    </td>
    <td>
        <button class="btn btn-sm"
                hx-post="/api/tasks/{{ task.id }}/run"
                hx-target="#task-{{ task.id }}"
                hx-swap="outerHTML"
                hx-indicator="#spinner-{{ task.id }}">
            Run now
        </button>
        <span id="spinner-{{ task.id }}" class="htmx-indicator text-dim text-sm">running…</span>
    </td>
</tr>
```

**Step 4: Create `templates/tasks_list.html`**

```html
{% extends "base.html" %}
{% block title %}Tasks — Daruma{% endblock %}
{% block content %}
<div class="flex-between">
    <h1>Tasks</h1>
    <a href="/ui/tasks/new" class="btn btn-primary">New Task</a>
</div>
<table>
    <thead>
        <tr><th>Name</th><th>Schedule</th><th>Status</th><th>Actions</th></tr>
    </thead>
    <tbody>
        {% for task in tasks %}
            {% include "partials/task_row.html" %}
        {% endfor %}
        {% if not tasks %}
            <tr><td colspan="4" class="text-dim text-sm" style="text-align:center; padding:2rem;">
                No tasks yet. Create one to get started.
            </td></tr>
        {% endif %}
    </tbody>
</table>
{% endblock %}
```

**Step 5: Create `app/routers/ui.py`**

```python
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.repository import TaskRepo, RunRepo
from app.routers.tasks import get_task_repo
from app.routers.runs import get_run_repo

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def tasks_list(request: Request, repo: TaskRepo = Depends(get_task_repo)):
    tasks = repo.list()
    return templates.TemplateResponse("tasks_list.html", {"request": request, "tasks": tasks})
```

**Step 6: Register UI router in `app/main.py`**

Add to imports:
```python
from app.routers import ui as ui_router
```

Add after other `include_router` calls:
```python
app.include_router(ui_router.router)
```

**Step 7: Commit**

```bash
git add templates/ static/ app/routers/ui.py app/main.py
git commit -m "feat: base UI with tasks list page (Jinja2 + HTMX)"
```

---

## Task 13: UI — Task Detail + Form

**Files:**
- Create: `templates/task_form.html`
- Create: `templates/task_detail.html`
- Create: `templates/partials/run_row.html`
- Modify: `app/routers/ui.py`

**Step 1: Create `templates/task_form.html`**

```html
{% extends "base.html" %}
{% block title %}{% if task %}Edit Task{% else %}New Task{% endif %} — Daruma{% endblock %}
{% block content %}
<h1>{% if task %}Edit Task{% else %}New Task{% endif %}</h1>
<form method="post" action="/ui/tasks{% if task %}/{{ task.id }}{% endif %}" class="card">
    <div class="form-group">
        <label for="name">Name</label>
        <input type="text" id="name" name="name" value="{{ task.name if task else '' }}" required>
    </div>
    <div class="form-group">
        <label for="prompt">Prompt</label>
        <textarea id="prompt" name="prompt" required>{{ task.prompt if task else '' }}</textarea>
    </div>
    <div class="form-group">
        <label for="cron_expression">Cron Expression <span class="text-dim">(optional)</span></label>
        <input type="text" id="cron_expression" name="cron_expression"
               value="{{ task.cron_expression if task and task.cron_expression else '' }}"
               placeholder="0 8 * * 1-5">
    </div>
    <div class="form-group">
        <label for="allowed_tools">Allowed Tools <span class="text-dim">(comma-separated, optional)</span></label>
        <input type="text" id="allowed_tools" name="allowed_tools"
               value="{{ task.allowed_tools if task and task.allowed_tools else '' }}"
               placeholder="bash,read">
    </div>
    <div class="form-group">
        <label>
            <input type="checkbox" name="enabled" value="1" {{ 'checked' if not task or task.enabled }}>
            Enabled
        </label>
    </div>
    <button type="submit" class="btn btn-primary">{% if task %}Save{% else %}Create{% endif %}</button>
    <a href="/ui/" class="btn">Cancel</a>
</form>
{% endblock %}
```

**Step 2: Create `templates/partials/run_row.html`**

```html
<tr>
    <td><a href="/ui/runs/{{ run.id }}">{{ run.started_at[:19] }}</a></td>
    <td>
        {% if run.status == "success" %}
            <span class="badge badge-success">success</span>
        {% elif run.status == "failed" %}
            <span class="badge badge-danger">failed</span>
        {% else %}
            <span class="badge badge-warning">running</span>
        {% endif %}
    </td>
    <td class="text-dim text-sm">{{ run.trigger }}</td>
    <td class="text-dim text-sm">{{ (run.duration_ms / 1000)|round(1) if run.duration_ms else "—" }}s</td>
</tr>
```

**Step 3: Create `templates/task_detail.html`**

```html
{% extends "base.html" %}
{% block title %}{{ task.name }} — Daruma{% endblock %}
{% block content %}
<div class="flex-between">
    <h1>{{ task.name }}</h1>
    <div>
        <button class="btn btn-sm" hx-post="/api/tasks/{{ task.id }}/run" hx-swap="none"
                onclick="setTimeout(()=>location.reload(), 1000)">Run now</button>
        <a href="/ui/tasks/{{ task.id }}/edit" class="btn btn-sm">Edit</a>
        <button class="btn btn-sm btn-danger"
                hx-delete="/api/tasks/{{ task.id }}"
                hx-confirm="Delete this task?"
                hx-swap="none"
                onclick="setTimeout(()=>location.href='/ui/', 500)">Delete</button>
    </div>
</div>

<div class="card mt-1">
    <div class="text-dim text-sm" style="margin-bottom:0.5rem;">Prompt</div>
    <div class="log-output">{{ task.prompt }}</div>
    <div style="margin-top:1rem; display:flex; gap:2rem;">
        <div><span class="text-dim text-sm">Schedule:</span> {{ task.cron_expression or "Manual only" }}</div>
        <div><span class="text-dim text-sm">Tools:</span> {{ task.allowed_tools or "All" }}</div>
        <div>
            {% if task.enabled %}
                <span class="badge badge-success">enabled</span>
            {% else %}
                <span class="badge badge-dim">disabled</span>
            {% endif %}
        </div>
    </div>
</div>

<h2 class="mt-1">Run History</h2>
<table>
    <thead><tr><th>Time</th><th>Status</th><th>Trigger</th><th>Duration</th></tr></thead>
    <tbody>
        {% for run in runs %}
            {% include "partials/run_row.html" %}
        {% endfor %}
        {% if not runs %}
            <tr><td colspan="4" class="text-dim text-sm" style="text-align:center; padding:1rem;">
                No runs yet.
            </td></tr>
        {% endif %}
    </tbody>
</table>
{% endblock %}
```

**Step 4: Add UI routes to `app/routers/ui.py`**

Append to existing file:

```python
from fastapi.responses import RedirectResponse
from starlette.datastructures import FormData


@router.get("/tasks/new", response_class=HTMLResponse)
def task_form_new(request: Request):
    return templates.TemplateResponse("task_form.html", {"request": request, "task": None})


@router.post("/tasks", response_class=HTMLResponse)
def task_create_form(
    request: Request,
    repo: TaskRepo = Depends(get_task_repo),
):
    import asyncio
    body = asyncio.get_event_loop().run_until_complete(request.form())
    repo.create(
        name=body["name"],
        prompt=body["prompt"],
        cron_expression=body.get("cron_expression") or None,
        allowed_tools=body.get("allowed_tools") or None,
        enabled="enabled" in body,
    )
    return RedirectResponse("/ui/", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(
    request: Request,
    task_id: str,
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
):
    task = task_repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    runs = run_repo.list(task_id=task_id)
    return templates.TemplateResponse("task_detail.html", {
        "request": request, "task": task, "runs": runs,
    })


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def task_edit_form(
    request: Request,
    task_id: str,
    repo: TaskRepo = Depends(get_task_repo),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return templates.TemplateResponse("task_form.html", {"request": request, "task": task})


@router.post("/tasks/{task_id}", response_class=HTMLResponse)
def task_update_form(
    request: Request,
    task_id: str,
    repo: TaskRepo = Depends(get_task_repo),
):
    import asyncio
    body = asyncio.get_event_loop().run_until_complete(request.form())
    repo.update(
        task_id,
        name=body["name"],
        prompt=body["prompt"],
        cron_expression=body.get("cron_expression") or None,
        allowed_tools=body.get("allowed_tools") or None,
        enabled="enabled" in body,
    )
    return RedirectResponse(f"/ui/tasks/{task_id}", status_code=303)
```

**Step 5: Commit**

```bash
git add templates/ app/routers/ui.py
git commit -m "feat: task detail, edit, and create UI pages"
```

---

## Task 14: UI — Run Detail Page

**Files:**
- Create: `templates/run_detail.html`
- Modify: `app/routers/ui.py`

**Step 1: Create `templates/run_detail.html`**

```html
{% extends "base.html" %}
{% block title %}Run — Daruma{% endblock %}
{% block content %}
<div class="flex-between">
    <h1>Run Detail</h1>
    <a href="/ui/tasks/{{ run.task_id }}" class="btn btn-sm">Back to Task</a>
</div>

<div class="card mt-1" {% if run.status == "running" %}hx-get="/ui/runs/{{ run.id }}" hx-trigger="every 3s" hx-select=".card" hx-swap="outerHTML"{% endif %}>
    <div style="display:flex; gap:2rem; margin-bottom:1rem;">
        <div>
            <span class="text-dim text-sm">Status</span><br>
            {% if run.status == "success" %}
                <span class="badge badge-success">success</span>
            {% elif run.status == "failed" %}
                <span class="badge badge-danger">failed</span>
            {% else %}
                <span class="badge badge-warning">running…</span>
            {% endif %}
        </div>
        <div>
            <span class="text-dim text-sm">Trigger</span><br>
            {{ run.trigger }}
        </div>
        <div>
            <span class="text-dim text-sm">Duration</span><br>
            {{ (run.duration_ms / 1000)|round(1) if run.duration_ms else "—" }}s
        </div>
        <div>
            <span class="text-dim text-sm">Exit Code</span><br>
            {{ run.exit_code if run.exit_code is not none else "—" }}
        </div>
        <div>
            <span class="text-dim text-sm">Started</span><br>
            {{ run.started_at[:19] }}
        </div>
    </div>

    {% if run.stdout %}
    <div style="margin-bottom:1rem;">
        <div class="text-dim text-sm" style="margin-bottom:0.35rem;">Output</div>
        <div class="log-output">{{ run.stdout }}</div>
    </div>
    {% endif %}

    {% if run.stderr %}
    <div>
        <div class="text-dim text-sm" style="margin-bottom:0.35rem;">Errors</div>
        <div class="log-output" style="color:#e74c3c;">{{ run.stderr }}</div>
    </div>
    {% endif %}
</div>
{% endblock %}
```

**Step 2: Add route to `app/routers/ui.py`**

Append:

```python
@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: str,
    repo: RunRepo = Depends(get_run_repo),
):
    run = repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse("run_detail.html", {"request": request, "run": run})
```

**Step 3: Commit**

```bash
git add templates/run_detail.html app/routers/ui.py
git commit -m "feat: run detail page with auto-refresh for running status"
```

---

## Task 15: Dockerfile + docker-compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

# Install Node.js (required by Claude CLI)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

COPY app/ app/
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p /data

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Step 2: Create `docker-compose.yml`**

```yaml
services:
  daruma:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - daruma-data:/data
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    restart: unless-stopped

volumes:
  daruma-data:
```

**Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Dockerfile and docker-compose for single-container deployment"
```

---

## Task 16: Final Integration — Run All Tests

**Step 1: Run full test suite**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/ -v`
Expected: All tests pass (21+ tests)

**Step 2: Manual smoke test**

Run: `uv run uvicorn app.main:app --port 8080`

Verify:
- `GET http://localhost:8080/health` → `{"status": "ok"}`
- `GET http://localhost:8080/ui/` → Tasks list page renders
- Create a task via UI → shows in list
- Click "Run now" → creates a run (will fail without Claude CLI, but verifies the flow)

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and integration verification"
```

---

Plan complete and saved to `docs/plans/2026-04-01-claude-runner.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?

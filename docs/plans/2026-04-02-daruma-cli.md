# Daruma CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a CLI that mirrors the web UI by extracting business logic into a shared service layer used by both FastAPI routes and the CLI.

**Architecture:** Extract business logic from FastAPI routers into `app/services.py`. Both FastAPI routes and the new `click`-based CLI (`app/cli.py`) call the same service functions. The service layer takes repos as constructor args — FastAPI injects them via dependency overrides, CLI creates them directly from `DB_PATH`.

**Tech Stack:** click (CLI framework), existing SQLite/repository stack

---

### Task 1: Create service layer with custom exceptions

**Files:**
- Create: `app/services.py`
- Test: `tests/test_services.py`

**Step 1: Write failing tests for TaskService**

```python
# tests/test_services.py
import pytest
from app.repository import TaskRepo, RunRepo
from app.services import TaskService, RunService, TaskNotFoundError, RunNotFoundError


@pytest.fixture
def task_repo(db_conn):
    return TaskRepo(db_conn)


@pytest.fixture
def run_repo(db_conn):
    return RunRepo(db_conn)


@pytest.fixture
def task_service(task_repo):
    return TaskService(task_repo)


@pytest.fixture
def run_service(run_repo):
    return RunService(run_repo)


def test_create_task(task_service):
    task = task_service.create(name="Test", prompt="Do it")
    assert task["name"] == "Test"
    assert task["id"]


def test_list_tasks(task_service):
    task_service.create(name="A", prompt="p")
    task_service.create(name="B", prompt="p")
    assert len(task_service.list()) == 2


def test_get_task(task_service):
    task = task_service.create(name="X", prompt="p")
    assert task_service.get(task["id"])["name"] == "X"


def test_get_task_not_found(task_service):
    with pytest.raises(TaskNotFoundError):
        task_service.get("nonexistent")


def test_update_task(task_service):
    task = task_service.create(name="Old", prompt="p")
    updated = task_service.update(task["id"], name="New")
    assert updated["name"] == "New"


def test_update_task_not_found(task_service):
    with pytest.raises(TaskNotFoundError):
        task_service.update("nonexistent", name="X")


def test_delete_task(task_service):
    task = task_service.create(name="Gone", prompt="p")
    task_service.delete(task["id"])
    with pytest.raises(TaskNotFoundError):
        task_service.get(task["id"])


def test_delete_task_not_found(task_service):
    with pytest.raises(TaskNotFoundError):
        task_service.delete("nonexistent")


def test_list_runs(task_service, run_service, run_repo):
    task = task_service.create(name="T", prompt="p")
    run_repo.create(task_id=task["id"], trigger="manual")
    assert len(run_service.list()) == 1
    assert len(run_service.list(task_id=task["id"])) == 1


def test_get_run(task_service, run_service, run_repo):
    task = task_service.create(name="T", prompt="p")
    run = run_repo.create(task_id=task["id"], trigger="manual")
    assert run_service.get(run["id"])["trigger"] == "manual"


def test_get_run_not_found(run_service):
    with pytest.raises(RunNotFoundError):
        run_service.get("nonexistent")
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/test_services.py -v`
Expected: FAIL — `app.services` does not exist

**Step 3: Implement service layer**

```python
# app/services.py
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

    def _default_on_output(stdout: str) -> None:
        run_repo.update_output(run["id"], stdout)

    combined_on_output = None
    if on_output and on_output is not _default_on_output:
        def combined_on_output(stdout: str) -> None:
            run_repo.update_output(run["id"], stdout)
            on_output(stdout)
    else:
        combined_on_output = _default_on_output

    try:
        result = runner(
            task["prompt"],
            allowed_tools=task.get("allowed_tools"),
            run_id=run["id"],
            on_output=combined_on_output,
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        return run_repo.complete(
            run["id"],
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
        )
    except Exception as e:
        return run_repo.complete(
            run["id"], status="failed", stdout="", stderr=str(e), exit_code=-1
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
        target=lambda: _bg_worker(task, run["id"], runner, run_repo),
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
    """Cancel a running task. Raises RunNotFoundError if not found."""
    run = run_repo.get(run_id)
    if not run:
        raise RunNotFoundError(run_id)
    if run["status"] != "running":
        raise ValueError("Run is not active")
    killed = cancel_run(run_id)
    if not killed:
        run_repo.complete(run_id, status="failed", stdout="", stderr="Cancelled", exit_code=-1)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/test_services.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add app/services.py tests/test_services.py
git commit -m "feat: extract service layer from routers"
```

---

### Task 2: Refactor FastAPI routers to use service layer

**Files:**
- Modify: `app/routers/tasks.py`
- Modify: `app/routers/runs.py`
- Modify: `app/routers/triggers.py`
- Modify: `app/main.py`

**Step 1: Refactor tasks router**

Replace `app/routers/tasks.py` to use `TaskService`:

```python
from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import TaskCreate, TaskUpdate, TaskResponse
from app.services import TaskService, TaskNotFoundError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_service() -> TaskService:
    raise RuntimeError("task_service dependency not configured")


@router.get("", response_model=list[TaskResponse])
def list_tasks(svc: TaskService = Depends(get_task_service)):
    return svc.list()


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreate, svc: TaskService = Depends(get_task_service)):
    return svc.create(
        name=body.name,
        prompt=body.prompt,
        cron_expression=body.cron_expression,
        allowed_tools=body.allowed_tools,
        enabled=body.enabled,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, svc: TaskService = Depends(get_task_service)):
    try:
        return svc.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, body: TaskUpdate, svc: TaskService = Depends(get_task_service)):
    try:
        return svc.update(task_id, **body.model_dump(exclude_unset=True))
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, svc: TaskService = Depends(get_task_service)):
    try:
        svc.delete(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return Response(status_code=204)
```

**Step 2: Refactor runs router**

```python
from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.services import RunService, RunNotFoundError

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_service() -> RunService:
    raise RuntimeError("run_service dependency not configured")


@router.get("", response_model=list[RunResponse])
def list_runs(task_id: str | None = None, svc: RunService = Depends(get_run_service)):
    return svc.list(task_id=task_id)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, svc: RunService = Depends(get_run_service)):
    try:
        return svc.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
```

**Step 3: Refactor triggers router**

```python
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import RunRepo
from app.services import (
    TaskService,
    RunService,
    TaskNotFoundError,
    RunNotFoundError,
    execute_task_bg,
    cancel_task_run,
)
from app.runner import run_claude

router = APIRouter(tags=["triggers"])


def get_task_service() -> TaskService:
    raise RuntimeError("not configured")


def get_run_service() -> RunService:
    raise RuntimeError("not configured")


def get_run_repo() -> RunRepo:
    raise RuntimeError("not configured")


def get_runner() -> Callable:
    return run_claude


@router.post("/api/tasks/{task_id}/run", response_model=RunResponse)
def manual_trigger(
    task_id: str,
    task_svc: TaskService = Depends(get_task_service),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_svc.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_bg(task, run_repo, trigger="manual", runner=runner)


@router.post("/api/trigger/{task_name}", response_model=RunResponse)
def webhook_trigger(
    task_name: str,
    task_svc: TaskService = Depends(get_task_service),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_svc.get_by_name(task_name)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_bg(task, run_repo, trigger="webhook", runner=runner)


@router.post("/api/runs/{run_id}/cancel")
def cancel_run_endpoint(
    run_id: str,
    run_svc: RunService = Depends(get_run_service),
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

**Step 4: Update main.py dependency wiring**

Update `app/main.py` to wire `TaskService` and `RunService` instead of raw repos into routers. Also replace `_execute_cron_task` to use `execute_task` from services.

```python
# In lifespan(), replace dependency overrides:
from app.services import TaskService, RunService, execute_task

# Wire services
task_service = TaskService(TaskRepo(_conn))
run_service = RunService(RunRepo(_conn))
run_repo = RunRepo(_conn)

app.dependency_overrides[tasks_router.get_task_service] = lambda: task_service
app.dependency_overrides[runs_router.get_run_service] = lambda: run_service
app.dependency_overrides[triggers_router.get_task_service] = lambda: task_service
app.dependency_overrides[triggers_router.get_run_service] = lambda: run_service
app.dependency_overrides[triggers_router.get_run_repo] = lambda: run_repo
app.dependency_overrides[triggers_router.get_runner] = lambda: run_claude

# Replace _execute_cron_task:
def _execute_cron_task(task_id):
    task_repo = TaskRepo(_conn)
    run_repo = RunRepo(_conn)
    task = task_repo.get(task_id)
    if not task:
        return
    execute_task(task, run_repo, trigger="cron")
```

**Step 5: Update existing API tests to use service dependencies**

Update `tests/test_api_tasks.py` to override `get_task_service` instead of `get_task_repo`. Similarly for runs and triggers test files.

**Step 6: Run all tests**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add app/routers/ app/main.py tests/
git commit -m "refactor: use service layer in FastAPI routers"
```

---

### Task 3: Add click dependency and create CLI

**Files:**
- Modify: `pyproject.toml` (add `click` dependency)
- Create: `app/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Add click to dependencies**

Add `"click>=8.1"` to `pyproject.toml` dependencies list and run `uv sync`.

**Step 2: Write failing tests for CLI**

```python
# tests/test_cli.py
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from app.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def _init_db(db_path):
    """Patch DB_PATH so CLI uses test database."""
    with patch("app.cli.DB_PATH", db_path):
        from app.db import init_db
        init_db(db_path)
        yield


class TestTaskCommands:
    def test_tasks_list_empty(self, runner, _init_db):
        result = runner.invoke(cli, ["tasks", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output

    def test_tasks_create(self, runner, _init_db):
        result = runner.invoke(cli, [
            "tasks", "create", "--name", "Test", "--prompt", "Do it"
        ])
        assert result.exit_code == 0
        assert "Test" in result.output

    def test_tasks_show(self, runner, _init_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Show me", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "list"])
        # Extract task id from list output, then show
        assert result.exit_code == 0

    def test_tasks_delete(self, runner, _init_db):
        create = runner.invoke(cli, ["tasks", "create", "--name", "Del", "--prompt", "p"])
        assert create.exit_code == 0
        # Get task from list, delete it
        list_result = runner.invoke(cli, ["tasks", "list"])
        assert "Del" in list_result.output

    def test_runs_list(self, runner, _init_db):
        result = runner.invoke(cli, ["runs", "list"])
        assert result.exit_code == 0

    def test_run_task(self, runner, _init_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Runnable", "--prompt", "Hello"])
        with patch("app.services.run_claude") as mock:
            mock.return_value = {"exit_code": 0, "stdout": "done", "stderr": ""}
            result = runner.invoke(cli, ["run", "Runnable"])
            assert result.exit_code == 0
```

**Step 3: Run tests to verify they fail**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/test_cli.py -v`
Expected: FAIL — `app.cli` does not exist

**Step 4: Implement CLI**

```python
# app/cli.py
"""Daruma CLI — manage and run Claude automation tasks."""
import sys

import click

from app.config import DB_PATH
from app.db import init_db
from app.repository import TaskRepo, RunRepo
from app.services import (
    TaskService,
    RunService,
    TaskNotFoundError,
    RunNotFoundError,
    execute_task,
)


def _connect():
    return init_db(DB_PATH)


@click.group()
def cli():
    """Daruma — Claude automation task runner."""
    pass


# ── Tasks ──────────────────────────────────────────────


@cli.group()
def tasks():
    """Manage tasks."""
    pass


@tasks.command("list")
def tasks_list():
    """List all tasks."""
    conn = _connect()
    svc = TaskService(TaskRepo(conn))
    items = svc.list()
    conn.close()
    if not items:
        click.echo("No tasks found.")
        return
    for t in items:
        status = "enabled" if t["enabled"] else "disabled"
        cron = t["cron_expression"] or "no schedule"
        click.echo(f"  {t['id'][:8]}  {t['name']:<30} {cron:<20} [{status}]")


@tasks.command("create")
@click.option("--name", required=True, help="Task name")
@click.option("--prompt", required=True, help="Claude prompt")
@click.option("--cron", default=None, help="Cron expression (5-field)")
@click.option("--tools", default=None, help="Comma-separated allowed tools")
@click.option("--disabled", is_flag=True, help="Create in disabled state")
def tasks_create(name, prompt, cron, tools, disabled):
    """Create a new task."""
    conn = _connect()
    svc = TaskService(TaskRepo(conn))
    task = svc.create(
        name=name,
        prompt=prompt,
        cron_expression=cron,
        allowed_tools=tools,
        enabled=not disabled,
    )
    conn.close()
    click.echo(f"Created task: {task['name']} ({task['id'][:8]})")


@tasks.command("show")
@click.argument("task_id")
def tasks_show(task_id):
    """Show task details. Accepts full or partial (8-char) ID."""
    conn = _connect()
    svc = TaskService(TaskRepo(conn))
    task = _resolve_task(svc, task_id)
    conn.close()
    click.echo(f"ID:      {task['id']}")
    click.echo(f"Name:    {task['name']}")
    click.echo(f"Prompt:  {task['prompt']}")
    click.echo(f"Cron:    {task['cron_expression'] or 'none'}")
    click.echo(f"Tools:   {task['allowed_tools'] or 'all'}")
    click.echo(f"Enabled: {bool(task['enabled'])}")
    click.echo(f"Created: {task['created_at']}")
    click.echo(f"Updated: {task['updated_at']}")


@tasks.command("edit")
@click.argument("task_id")
@click.option("--name", default=None)
@click.option("--prompt", default=None)
@click.option("--cron", default=None)
@click.option("--tools", default=None)
@click.option("--enable/--disable", default=None)
def tasks_edit(task_id, name, prompt, cron, tools, enable):
    """Update a task."""
    conn = _connect()
    svc = TaskService(TaskRepo(conn))
    task = _resolve_task(svc, task_id)
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
    updated = svc.update(task["id"], **fields)
    conn.close()
    click.echo(f"Updated task: {updated['name']} ({updated['id'][:8]})")


@tasks.command("delete")
@click.argument("task_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def tasks_delete(task_id, yes):
    """Delete a task."""
    conn = _connect()
    svc = TaskService(TaskRepo(conn))
    task = _resolve_task(svc, task_id)
    if not yes:
        click.confirm(f"Delete task '{task['name']}'?", abort=True)
    svc.delete(task["id"])
    conn.close()
    click.echo(f"Deleted task: {task['name']}")


# ── Runs ───────────────────────────────────────────────


@cli.group()
def runs():
    """View run history."""
    pass


@runs.command("list")
@click.option("--task", "task_id", default=None, help="Filter by task ID")
@click.option("--limit", default=20, help="Max runs to show")
def runs_list(task_id, limit):
    """List recent runs."""
    conn = _connect()
    svc = RunService(RunRepo(conn))
    items = svc.list(task_id=task_id)[:limit]
    conn.close()
    if not items:
        click.echo("No runs found.")
        return
    for r in items:
        duration = f"{r['duration_ms']}ms" if r["duration_ms"] else "…"
        click.echo(
            f"  {r['id'][:8]}  {r['status']:<8}  {r['trigger']:<8}  {duration:<10}  {r['started_at']}"
        )


@runs.command("show")
@click.argument("run_id")
def runs_show(run_id):
    """Show run details and output."""
    conn = _connect()
    svc = RunService(RunRepo(conn))
    try:
        run = svc.get(run_id)
    except RunNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise SystemExit(1)
    conn.close()
    click.echo(f"ID:       {run['id']}")
    click.echo(f"Task:     {run['task_id']}")
    click.echo(f"Trigger:  {run['trigger']}")
    click.echo(f"Status:   {run['status']}")
    click.echo(f"Started:  {run['started_at']}")
    click.echo(f"Finished: {run['finished_at'] or '…'}")
    click.echo(f"Duration: {run['duration_ms'] or '…'}ms")
    click.echo(f"Exit:     {run['exit_code']}")
    if run["stdout"]:
        click.echo(f"\n--- stdout ---\n{run['stdout']}")
    if run["stderr"]:
        click.echo(f"\n--- stderr ---\n{run['stderr']}")


# ── Run (execute) ─────────────────────────────────────


@cli.command("run")
@click.argument("task_name_or_id")
def run_task(task_name_or_id):
    """Run a task now (blocks until complete, streams output)."""
    conn = _connect()
    task_svc = TaskService(TaskRepo(conn))
    run_repo = RunRepo(conn)

    task = _resolve_task(task_svc, task_name_or_id)
    click.echo(f"Running task: {task['name']}…")

    def _on_output(stdout: str):
        # Clear and reprint last line for streaming effect
        click.echo(f"\r{stdout.splitlines()[-1] if stdout else ''}", nl=False)

    result = execute_task(
        task, run_repo, trigger="manual", on_output=_on_output,
    )
    conn.close()
    click.echo()  # newline after streaming
    click.echo(f"\nStatus: {result['status']}  Exit: {result['exit_code']}  Duration: {result['duration_ms']}ms")
    if result["status"] != "success":
        sys.exit(1)


# ── Helpers ────────────────────────────────────────────


def _resolve_task(svc: TaskService, identifier: str) -> dict:
    """Resolve a task by full ID, partial ID (prefix), or name."""
    # Try exact ID first
    try:
        return svc.get(identifier)
    except TaskNotFoundError:
        pass
    # Try by name
    try:
        return svc.get_by_name(identifier)
    except TaskNotFoundError:
        pass
    # Try prefix match on ID
    all_tasks = svc.list()
    matches = [t for t in all_tasks if t["id"].startswith(identifier)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        click.echo(f"Ambiguous ID prefix '{identifier}', matches:", err=True)
        for t in matches:
            click.echo(f"  {t['id']}  {t['name']}", err=True)
        raise SystemExit(1)
    click.echo(f"Task not found: {identifier}", err=True)
    raise SystemExit(1)
```

**Step 5: Add CLI entrypoint to pyproject.toml**

```toml
[project.scripts]
daruma = "app.cli:cli"
```

**Step 6: Run CLI tests**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/test_cli.py -v`
Expected: All PASS

**Step 7: Run all tests (regression)**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/ -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add app/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: add daruma CLI with click"
```

---

### Task 4: Update UI router to use service layer

**Files:**
- Modify: `app/routers/ui.py`
- Modify: `app/main.py` (wire UI dependencies)

The UI router likely also uses raw repos — refactor to use services for consistency.

**Step 1: Read and refactor ui.py**

Update to use `TaskService`/`RunService` instead of raw repos.

**Step 2: Run all tests**

Run: `cd /Users/kcanizares/vf/automations/daruma && uv run pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add app/routers/ui.py app/main.py
git commit -m "refactor: use service layer in UI router"
```

---

### Task 5: Smoke test CLI manually and update README

**Step 1: Smoke test CLI commands**

```bash
uv run daruma --help
uv run daruma tasks --help
uv run daruma tasks list
uv run daruma tasks create --name "CLI Test" --prompt "Say hello"
uv run daruma tasks list
uv run daruma tasks show <id>
uv run daruma tasks delete -y <id>
```

**Step 2: Update README with CLI usage**

Add a CLI section to the existing README.

**Step 3: Final commit**

```bash
git add README.md
git commit -m "docs: add CLI usage to README"
```

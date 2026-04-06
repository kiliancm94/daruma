# Per-Task Environment Variables — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow tasks to define key-value environment variables that are injected into the Claude subprocess at execution time.

**Architecture:** Add a nullable `env_vars` JSON text column to the `tasks` table. Store as `{"KEY": "value"}` dict. At execution time, merge `os.environ` + task env vars (task wins) and pass to `subprocess.Popen(env=...)`. Expose via CLI `--env KEY=VALUE` (repeatable) and UI textarea (one `KEY=VALUE` per line).

**Tech Stack:** SQLAlchemy (model), Pydantic (schema), Alembic (migration), Click (CLI), Jinja2 (UI)

---

### Task 1: Model + Schema + Migration

**Files:**
- Modify: `app/models/task.py:25-35`
- Modify: `app/schemas/task.py:18-54`
- Create: `alembic/versions/c4d5e6f7g8h9_add_env_vars_to_tasks.py`

**Step 1: Add `env_vars` column to model**

In `app/models/task.py`, add after the `output_destination` column:

```python
env_vars: Mapped[str | None] = mapped_column(Text, nullable=True)
```

**Step 2: Add `env_vars` to all three Pydantic schemas**

In `app/schemas/task.py`:

- `TaskCreate`: add `env_vars: dict[str, str] | None = None`
- `TaskUpdate`: add `env_vars: dict[str, str] | None = None`
- `TaskResponse`: add `env_vars: dict[str, str] | None`

The response schema needs a custom validator because the DB stores JSON text but we want a dict in the API response. Add a `field_validator` to `TaskResponse`:

```python
from pydantic import field_validator
import json

@field_validator("env_vars", mode="before")
@classmethod
def parse_env_vars(cls, v):
    if isinstance(v, str):
        return json.loads(v)
    return v
```

**Step 3: Create Alembic migration**

```bash
cd /Users/kcanizares/vf/automations/daruma
source .venv/bin/activate && alembic revision -m "add env_vars to tasks"
```

Then edit the generated file:

```python
def upgrade() -> None:
    op.add_column("tasks", sa.Column("env_vars", sa.Text(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("env_vars")
```

Update the `down_revision` to point at the latest: `"b623e165a31e"`.

**Step 4: Run migration and verify**

```bash
source .venv/bin/activate && alembic upgrade head
```

**Step 5: Run existing tests to ensure nothing broke**

```bash
source .venv/bin/activate && pytest -x -q
```

Expected: all 76 tests pass.

---

### Task 2: CRUD layer — serialize/deserialize env_vars

**Files:**
- Modify: `app/crud/tasks.py:11-35` (create function)
- Modify: `app/crud/tasks.py:50-62` (update function)
- Test: `tests/test_crud.py`

**Step 1: Write failing tests**

Add to `tests/test_crud.py`:

```python
def test_create_task_with_env_vars(db_session):
    from app.crud import tasks as task_crud
    task = task_crud.create(
        db_session, name="T", prompt="p",
        env_vars={"API_KEY": "secret123"}
    )
    assert task.env_vars is not None
    import json
    assert json.loads(task.env_vars) == {"API_KEY": "secret123"}

def test_update_task_env_vars(db_session):
    from app.crud import tasks as task_crud
    task = task_crud.create(db_session, name="T", prompt="p")
    assert task.env_vars is None
    updated = task_crud.update(
        db_session, task.id,
        env_vars={"TOKEN": "abc"}
    )
    import json
    assert json.loads(updated.env_vars) == {"TOKEN": "abc"}
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_crud.py -k "env_vars" -v
```

Expected: FAIL — `create()` doesn't accept `env_vars`.

**Step 3: Update CRUD create function**

In `app/crud/tasks.py`, add `env_vars: dict[str, str] | None = None` parameter to `create()`. Serialize before storing:

```python
import json

def create(
    session: Session,
    name: str,
    prompt: str,
    cron_expression: str | None = None,
    allowed_tools: str | None = None,
    model: str = "sonnet",
    enabled: bool = True,
    output_format: OutputFormat | None = None,
    output_destination: str | None = None,
    env_vars: dict[str, str] | None = None,
) -> Task:
    task = Task(
        name=name,
        prompt=prompt,
        cron_expression=cron_expression,
        allowed_tools=allowed_tools,
        model=model,
        enabled=enabled,
        output_format=output_format,
        output_destination=output_destination,
        env_vars=json.dumps(env_vars) if env_vars else None,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task
```

**Step 4: Update TaskUpdate schema**

The `env_vars` field is already added in Task 1. The `update()` function uses `TaskUpdate(**fields).model_dump(exclude_unset=True)`, so env_vars will flow through. But we need to serialize the dict to JSON string before setting it on the model. Add serialization in the update function:

```python
def update(session: Session, task_id: str, **fields) -> Task:
    if (task := get(session, task_id)) is None:
        raise NotFoundError(f"Task not found: {task_id}")
    validated = TaskUpdate(**fields).model_dump(exclude_unset=True)
    if not validated:
        return task
    # Serialize env_vars dict to JSON string for storage
    if "env_vars" in validated and validated["env_vars"] is not None:
        validated["env_vars"] = json.dumps(validated["env_vars"])
    for key, value in validated.items():
        setattr(task, key, value)
    task.updated_at = utcnow()
    session.commit()
    session.refresh(task)
    return task
```

**Step 5: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_crud.py -k "env_vars" -v
```

Expected: PASS

**Step 6: Run full test suite**

```bash
source .venv/bin/activate && pytest -x -q
```

Expected: all pass.

---

### Task 3: Runner — accept and inject env vars

**Files:**
- Modify: `app/runner.py:74-108`
- Test: `tests/test_runner.py`

**Step 1: Write failing test**

Add to `tests/test_runner.py`:

```python
@patch("app.runner.subprocess.Popen")
def test_run_claude_with_env_vars(mock_popen):
    import os
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff", env_vars={"MY_TOKEN": "secret"})
    call_kwargs = mock_popen.call_args[1]  # keyword args
    assert "env" in call_kwargs
    assert call_kwargs["env"]["MY_TOKEN"] == "secret"
    # Parent env should be inherited too
    assert call_kwargs["env"].get("PATH") == os.environ.get("PATH")

@patch("app.runner.subprocess.Popen")
def test_run_claude_without_env_vars(mock_popen):
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff")
    call_kwargs = mock_popen.call_args[1]
    # No env= kwarg means inherit parent env
    assert "env" not in call_kwargs
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_runner.py -k "env_vars" -v
```

Expected: FAIL — `run_claude()` doesn't accept `env_vars`.

**Step 3: Add `env_vars` parameter to `run_claude`**

In `app/runner.py`, update the `run_claude` signature and Popen call:

```python
import os

def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    model: str = DEFAULT_MODEL,
    system_prompt: str | None = None,
    timeout: int = 300,
    run_id: str | None = None,
    on_output: Callable[[str], None] | None = None,
    env_vars: dict[str, str] | None = None,
) -> dict:
    # ... cmd building stays the same ...

    popen_kwargs: dict = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if env_vars:
        popen_kwargs["env"] = {**os.environ, **env_vars}

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
```

**Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_runner.py -k "env_vars" -v
```

Expected: PASS

**Step 5: Full test suite**

```bash
source .venv/bin/activate && pytest -x -q
```

Expected: all pass.

---

### Task 4: Services — pass env_vars from task to runner

**Files:**
- Modify: `app/services.py:287-339` (execute_task)
- Modify: `app/services.py:342-368` (execute_task_background)
- Modify: `app/services.py:371-409` (_background_worker)
- Test: `tests/test_services.py`

**Step 1: Write failing test**

Add to `tests/test_services.py` inside `TestExecuteTask`:

```python
def test_env_vars_passed_to_runner(self, task_svc, db_session):
    import json
    from app.crud import tasks as task_crud
    task = task_svc.create(name="T", prompt="p",
                           env_vars={"MY_SECRET": "abc123"})
    mock_runner = MagicMock(
        return_value={
            "exit_code": 0, "stdout": "done",
            "stderr": "", "activity": "",
        }
    )
    execute_task(task, db_session, runner=mock_runner)
    call_kwargs = mock_runner.call_args.kwargs
    assert call_kwargs["env_vars"] == {"MY_SECRET": "abc123"}

def test_no_env_vars_passes_none(self, task_svc, db_session):
    task = task_svc.create(name="T", prompt="p")
    mock_runner = MagicMock(
        return_value={
            "exit_code": 0, "stdout": "done",
            "stderr": "", "activity": "",
        }
    )
    execute_task(task, db_session, runner=mock_runner)
    call_kwargs = mock_runner.call_args.kwargs
    assert call_kwargs.get("env_vars") is None
```

**Step 2: Run to verify failure**

```bash
source .venv/bin/activate && pytest tests/test_services.py -k "env_vars" -v
```

**Step 3: Update `execute_task`, `execute_task_background`, and `_background_worker`**

In `execute_task` and `_background_worker`, deserialize and pass env_vars:

```python
import json

# In execute_task and _background_worker, before calling runner:
env_vars = json.loads(task.env_vars) if task.env_vars else None

result = runner(
    task.prompt,
    allowed_tools=task.allowed_tools,
    model=task.model,
    system_prompt=system_prompt,
    run_id=run_id,
    on_output=_combined,
    env_vars=env_vars,
)
```

Same pattern in `_background_worker`.

**Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_services.py -k "env_vars" -v
```

Expected: PASS

**Step 5: Full suite**

```bash
source .venv/bin/activate && pytest -x -q
```

---

### Task 5: CLI — `--env` flag on create and edit, display on show

**Files:**
- Modify: `app/cli.py:75-114` (create_task)
- Modify: `app/cli.py:142-224` (edit_task)
- Modify: `app/cli.py:117-139` (show_task)
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_create_task_with_env(cli_runner):
    result = cli_runner.invoke(cli, [
        "tasks", "create",
        "--name", "EnvTask",
        "--prompt", "Do it",
        "--env", "API_KEY=secret",
        "--env", "TOKEN=abc",
    ])
    assert result.exit_code == 0
    assert "Created task" in result.output

def test_show_task_displays_env(cli_runner):
    cli_runner.invoke(cli, [
        "tasks", "create",
        "--name", "EnvShow",
        "--prompt", "p",
        "--env", "KEY=val",
    ])
    result = cli_runner.invoke(cli, ["tasks", "show", "EnvShow"])
    assert "KEY=val" in result.output
```

(Check existing test patterns in `tests/test_cli.py` for the exact fixture name — likely `cli_runner` or similar using Click's CliRunner.)

**Step 2: Implement `--env` on create**

Add a `--env` option (multiple=True) to `create_task`:

```python
@click.option("--env", "env_pairs", multiple=True, help="Environment variable KEY=VALUE (repeatable)")
```

Parse inside the function:

```python
env_vars = None
if env_pairs:
    env_vars = {}
    for pair in env_pairs:
        if "=" not in pair:
            click.echo(f"Invalid env var (expected KEY=VALUE): {pair}", err=True)
            raise SystemExit(1)
        key, _, value = pair.partition("=")
        env_vars[key] = value
```

Pass `env_vars=env_vars` to `task_service.create(...)`.

**Step 3: Implement `--env` on edit**

Same `--env` option on `edit_task`. When present, include in fields:

```python
if env_pairs is not None and len(env_pairs) > 0:
    env_vars = {}
    for pair in env_pairs:
        if "=" not in pair:
            click.echo(f"Invalid env var (expected KEY=VALUE): {pair}", err=True)
            raise SystemExit(1)
        key, _, value = pair.partition("=")
        env_vars[key] = value
    fields["env_vars"] = env_vars
```

**Step 4: Display env vars in `show_task`**

Add after the output_dest line in `show_task`:

```python
if task.env_vars:
    import json
    env = json.loads(task.env_vars)
    masked = ", ".join(f"{k}=***" for k in env)
    click.echo(f"Env vars: {masked}")
else:
    click.echo("Env vars: none")
```

Note: mask values in display for safety.

**Step 5: Update `TaskService.create` to accept `env_vars`**

In `app/services.py`, add `env_vars: dict[str, str] | None = None` parameter to `TaskService.create()` and pass through to `task_crud.create(...)`.

**Step 6: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_cli.py -k "env" -v
```

**Step 7: Full suite**

```bash
source .venv/bin/activate && pytest -x -q
```

---

### Task 6: API router — pass env_vars through

**Files:**
- Modify: `app/routers/tasks.py:20-31` (create_task)
- Test: `tests/test_api_tasks.py`

**Step 1: Write failing test**

Add to `tests/test_api_tasks.py`:

```python
def test_create_task_with_env_vars(client):
    resp = client.post("/api/tasks", json={
        "name": "EnvAPI", "prompt": "p",
        "env_vars": {"SECRET": "val"}
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["env_vars"] == {"SECRET": "val"}
```

**Step 2: Update router**

In `app/routers/tasks.py`, update `create_task` to pass `env_vars`:

```python
return task_service.create(
    name=body.name,
    prompt=body.prompt,
    cron_expression=body.cron_expression,
    allowed_tools=body.allowed_tools,
    model=body.model,
    enabled=body.enabled,
    env_vars=body.env_vars,
)
```

**Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_api_tasks.py -k "env_vars" -v
```

**Step 4: Full suite**

```bash
source .venv/bin/activate && pytest -x -q
```

---

### Task 7: UI — form and detail templates

**Files:**
- Modify: `templates/task_form.html:48-54`
- Modify: `templates/task_detail.html:24-31`
- Modify: `app/routers/ui.py:77-99` (task_create_form)
- Modify: `app/routers/ui.py:151-177` (task_update_form)

**Step 1: Add textarea to task form**

In `templates/task_form.html`, add before the Skills section (before line 34):

```html
<div class="form-group">
    <label for="env_vars">Environment Variables <span class="text-dim">(one KEY=VALUE per line)</span></label>
    <textarea id="env_vars" name="env_vars" rows="3" placeholder="API_KEY=secret&#10;TOKEN=abc123">{{ env_vars_text if env_vars_text else '' }}</textarea>
</div>
```

**Step 2: Update UI create endpoint**

In `app/routers/ui.py` `task_create_form`, add `env_vars: str = Form("")` parameter. Parse it:

```python
parsed_env = None
if env_vars.strip():
    parsed_env = {}
    for line in env_vars.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        key, _, value = line.partition("=")
        parsed_env[key] = value
```

Pass `env_vars=parsed_env` to `task_service.create(...)`.

**Step 3: Update UI update endpoint**

Same parsing in `task_update_form`.

**Step 4: Pass `env_vars_text` to edit form template**

In `task_edit_form` (GET handler), deserialize and format for textarea:

```python
import json
env_vars_text = ""
if task.env_vars:
    env = json.loads(task.env_vars)
    env_vars_text = "\n".join(f"{k}={v}" for k, v in env.items())
```

Add `"env_vars_text": env_vars_text` to the template context dict. Also add it to `task_form_new` as empty string.

**Step 5: Display env vars in task detail**

In `templates/task_detail.html`, add after the Skills div (around line 40):

```html
<div><span class="text-dim text-sm">Env vars:</span>
    {% if task.env_vars %}
        {% for k in task.env_vars_keys %}
            <span class="badge badge-dim">{{ k }}=***</span>
        {% endfor %}
    {% else %}
        none
    {% endif %}
</div>
```

In the `task_detail` route handler, parse env_vars keys and attach to task object or pass in context:

```python
env_vars_keys = []
if task.env_vars:
    import json
    env_vars_keys = list(json.loads(task.env_vars).keys())
```

Pass as `"env_vars_keys": env_vars_keys` in template context.

**Step 6: Manual test**

```bash
uv run uvicorn app.main:app --reload
```

Visit `http://localhost:8080/ui/`, create/edit a task with env vars, verify display.

---

### Task 8: Update the existing calendar task

**Step 1: Set env var on the existing task via CLI**

```bash
uv run daruma tasks edit "Morning Calendar Digest" --env "CALENDAR_TOKEN=$(cat /Users/kcanizares/vf/automations/calendar-api/.api-token)"
```

**Step 2: Run the task**

```bash
uv run daruma run "Morning Calendar Digest"
```

Expected: task succeeds, calendar events are fetched and summarized.

**Step 3: Full test suite one final time**

```bash
source .venv/bin/activate && pytest -x -q
```

Expected: all tests pass.

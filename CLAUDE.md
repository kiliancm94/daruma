# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

- **Name**: Daruma — task scheduler for Claude CLI automations
- **Language**: Python 3.14+
- **Framework**: FastAPI + SQLAlchemy 2.x + Click CLI + rich
- **UI**: Jinja2 + HTMX + marked.js (for markdown rendering)
- **Database**: SQLite with WAL mode, Alembic migrations
- **Package manager**: uv

## Commands

| Action | Command |
|--------|---------|
| Install | `uv sync --all-extras` |
| Run all tests | `source .venv/bin/activate && pytest` |
| Run single test | `source .venv/bin/activate && pytest tests/test_file.py::TestClass::test_name -v` |
| Lint | `uvx ruff check --fix .` |
| Format | `uvx ruff format .` |
| Run server (dev) | `uv run uvicorn app.main:app --reload` |
| Run server (CLI) | `uv run daruma server` |
| Run CLI | `uv run daruma` |
| Service install | `daruma service install` |
| Service status | `daruma service status` |
| New migration | `alembic revision --autogenerate -m "description"` |

## Architecture

```
app/
  models/        # SQLAlchemy ORM — one model per file
  schemas/       # Pydantic schemas — one file per domain
  crud/          # Data access — plain functions, session as first param
  routers/       # FastAPI routers — one per resource + ui.py for templates
  utils/         # Shared helpers (date_helpers.py, env_vars.py)
  services.py    # Business logic layer (Services + execute_task/execute_pipeline)
  runner.py      # Claude CLI subprocess wrapper (stream-json parsing)
  scheduler.py   # APScheduler integration (cron job sync)
  db.py          # Engine/session/migration management
  cli.py         # Click CLI with rich output + macOS service management
  main.py        # FastAPI app + lifespan (scheduler start, skill sync)
  config.py      # DB_PATH, PORT, HOST, HOSTNAME from env vars
templates/       # Jinja2 templates (base.html + page templates + partials/)
static/          # CSS (style.css — dark theme)
```

### Request flow

- **API**: Router → Service (injected via `Depends`) → CRUD → DB
- **CLI**: `_connect()` → Service → CRUD → DB
- **UI**: Router (Jinja2 templates) → Service → CRUD → DB

### Execution flow

1. `execute_task()` creates a `Run` record, builds Claude CLI command
2. `runner.run_claude()` spawns `claude -p --output-format stream-json` subprocess
3. `_read_stream()` parses stream events, extracts stdout + activity log, flushes to DB every 2s via callback
4. Background mode: `execute_task_background()` spawns a thread, returns `Run` with status="running" immediately

### Pipeline execution

- Steps run sequentially; each step's stdout is prepended to the next step's prompt
- Failure in any step halts the pipeline
- Background pipeline workers use `_pipeline_background_worker()` with isolated sessions

## Code Design Patterns

### File naming: 1:1 mapping across layers

Each entity has matching files across layers (e.g. for "skill"):
- `app/models/skill.py` → `app/schemas/skill.py` → `app/crud/skills.py` → `app/routers/skills.py`
- Models/schemas use singular names; CRUD/routers use plural
- Tests follow `test_crud_{resource}.py`, `test_api_{resource}.py`

### Schema naming convention

Each entity uses a three-schema pattern: `XCreate` (POST input), `XUpdate` (PUT input, all fields optional), `XResponse` (output with `from_attributes=True`). Read-only entities (Run, PipelineRun) only have `XResponse`.

### Models and schemas are separate concerns

- `app/models/` — SQLAlchemy ORM only; one model per file; owns table definition
- `app/schemas/` — Pydantic only; defines API/CLI input/output; NOT inside models
- Response schemas use `model_config = ConfigDict(from_attributes=True)` for ORM auto-parsing

### Data model conventions

- **IDs**: UUID strings generated via `default=lambda: str(uuid.uuid4())`
- **Timestamps**: ISO 8601 strings (not datetime), generated via `utcnow()` helper
- **Enums**: All use `StrEnum`, stored as String columns (human-readable in DB)
- **JSON fields**: `env_vars` stored as JSON string in Text column, deserialized in schema layer
- **Cascades**: Parent→child uses `cascade="all, delete-orphan"` on relationship + `ondelete="CASCADE"` on FK
- Task deletion is blocked if the task is used in any pipeline (raises `ValueError`)

### CRUD layer: plain functions, not classes

- Each CRUD file exposes plain functions with `session: Session` as first parameter
- Standard functions: `create()`, `get()`, `get_by_name()`, `get_all()`, `update()`, `delete()`
- `get()` returns `None` on miss; `update()` and `delete()` raise `NotFoundError`
- Junction tables (task_skills) use `assign()`, `unassign()`, `list_for_task()`, `replace()`
- No classes, no `__init__.py` re-exports — import as module: `from app.crud import tasks as task_crud`
- Use walrus operator for get-and-check: `if (task := get(session, task_id)) is None:`
- Don't define updatable field sets manually — use a Pydantic model to constrain which fields are updatable

### Error handling flow

Exceptions escalate through layers with translation at each boundary:

```
CRUD: raises NotFoundError / ValueError
  → Service: catches and raises TaskNotFoundError, SkillNotFoundError, etc.
    → API Router: catches and raises HTTPException(404) or HTTPException(422)
    → CLI: catches, prints to stderr via click.echo(..., err=True), raises SystemExit(1)
```

- Runner errors (subprocess failure, timeout, CLI not found) return `{"exit_code": -1, "stderr": "..."}` — never raise
- Stream JSON parse errors (`json.JSONDecodeError`) are silently skipped
- Background worker exceptions are caught and recorded as `status="failed"` with `stderr=str(e)` on the Run

### Push defaults into models/schemas, not CRUD

- Timestamps (`created_at`, `updated_at`) and IDs should use model-level defaults
- CRUD functions should not manually set values that the model can generate

### Don't duplicate utility functions

- Shared helpers (e.g. `utcnow()`) go in `app/utils/` — never duplicate across files
- If a function appears in more than one module, extract it

### Dependency injection and session management

**FastAPI routes** use `Depends()` with service factory functions:
```python
def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(session)
```

**Trigger routes** inject three dependencies for background execution:
- `get_db` → session for initial validation
- `get_session_factory` → sessionmaker passed to background thread
- `get_runner` → `run_claude` callable (mockable in tests)

**CLI** uses manual session management (`_connect()` → `get_session()`), no Depends mechanism.

**Background threads** receive `session_factory` and call `session_factory()` to create their own isolated session. Must `session.expunge(obj)` before spawning threads to detach ORM objects.

### CLI patterns

- Use `rich.Table` for list output, `console.print_json` for `--json` flag
- Services return ORM objects; CLI converts via `Schema.model_validate(obj).model_dump()` for JSON
- `_resolve_task()` / `_resolve_pipeline()` accept full ID, partial ID prefix, or name

### UI patterns

- HTMX fire-and-forget: `hx-swap="none"` + `onclick` with `setTimeout` for redirect
- Markdown rendering via marked.js (CDN) — use `| tojson` filter when passing text to JS
- Pipeline step builder uses JS array + hidden textarea that posts `steps_text` (newline-separated task names)

## Test patterns

- Tests use in-memory SQLite with `Base.metadata.create_all()` (skip migrations)
- CLI tests: `CliRunner` from Click with patched `DB_PATH`
- API tests: `TestClient` with `dependency_overrides[get_db]` to inject test session
- Trigger tests: override three deps — `get_db`, `get_session_factory`, `get_runner` (mock runner)
- Runner tests: mock `subprocess.Popen` with fake stream-json output
- Service tests: inject `db_session` fixture directly into Service constructor
- Test files: `test_crud_*.py`, `test_api_*.py`, `test_services.py`, `test_cli.py`, `test_runner.py`

## macOS service

The server runs as a launchd agent at `http://daruma.localhost:9090`:
- Plist at `~/Library/LaunchAgents/com.daruma.server.plist`
- Auto-starts on login (`RunAtLoad`), auto-restarts on crash (`KeepAlive`)
- `_find_project_root()` uses `git rev-parse --git-common-dir` to resolve the main repo (not a worktree)
- Logs at `data/server.log` and `data/server.err`

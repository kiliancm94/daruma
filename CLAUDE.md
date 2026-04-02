# Daruma — Project Instructions

## Project Context

- **Name**: Daruma — Docker-based task scheduler for Claude CLI automations
- **Language**: Python 3.14+
- **Framework**: FastAPI + SQLAlchemy 2.x + Click CLI + rich
- **Package manager**: uv

## Architecture

```
app/
  models/        # SQLAlchemy ORM models — one file per table (base.py, task.py, run.py)
  schemas/       # Pydantic schemas — one file per domain (task.py, run.py)
  crud/          # Data access — plain functions, session as first param
  routers/       # FastAPI routers — one file per resource
  utils/         # Shared helpers (date_helpers.py, etc.)
  services.py    # Business logic layer
  db.py          # Engine/session management
  cli.py         # Click CLI with rich output
  main.py        # FastAPI app + lifespan
```

## Code Design Patterns

### Models and schemas are separate concerns

- `app/models/` — SQLAlchemy ORM only; one model per file; owns table definition
- `app/schemas/` — Pydantic only; defines API/CLI input/output; NOT inside models
- Response schemas use `model_config = ConfigDict(from_attributes=True)` for ORM auto-parsing

### CRUD layer: plain functions, not classes

- Each CRUD file exposes plain functions with `session: Session` as first parameter
- No classes, no `__init__.py` re-exports — consumers import directly: `from app.crud import tasks as task_crud`
- Use walrus operator for get-and-check patterns: `if (task := get(session, task_id)) is None:`
- Raise exceptions on not-found — don't return `None` or `bool`; let the caller handle the exception
- Don't define updatable field sets manually — use a Pydantic model to constrain which fields are updatable

### Push defaults into models/schemas, not CRUD

- Timestamps (`created_at`, `updated_at`) and IDs should use model-level defaults
- CRUD functions should not manually set values that the model can generate

### Don't duplicate utility functions

- Shared helpers (e.g. `utcnow()`) go in `app/utils/` — never duplicate across files
- If a function appears in more than one module, extract it

### Session management

- FastAPI: per-request sessions via `Depends(get_db)` with rollback on exception
- CLI: `init_db()` + `get_session()` per command
- Background threads: `session_factory` — each thread creates its own session
- Always `session.close()` in `finally` blocks

### CLI output

- Use `rich.Table` for list output
- Use `console.print_json` for `--json` flag
- Services return ORM objects; CLI converts via `Schema.model_validate(obj).model_dump()` for JSON

## Commands

| Action | Command |
|--------|---------|
| Install | `uv sync --all-extras` |
| Run tests | `source .venv/bin/activate && pytest` |
| Lint | `uvx ruff check --fix .` |
| Format | `uvx ruff format .` |
| Run server | `uv run uvicorn app.main:app --reload` |
| Run CLI | `uv run daruma` |

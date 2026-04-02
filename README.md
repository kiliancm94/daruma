# Daruma

Lightweight task scheduler that runs Claude CLI agents on cron schedules, manual triggers, or webhooks. Comes with a web UI and a CLI.

## Stack

| Component | Choice |
|-----------|--------|
| Backend | Python 3.14 + FastAPI |
| UI | Jinja2 + HTMX |
| Database | SQLite |
| Scheduler | APScheduler |
| Agent | Claude CLI (`claude -p`) |
| Deployment | Docker |

## Quick Start

```bash
# Local
uv sync --all-extras
uv run uvicorn app.main:app --port 8080

# Docker
docker compose up --build
```

Open **http://localhost:8080/ui/** or use the CLI (see below).

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `DARUMA_DATA_DIR` | `./data` (local) or `/data` (Docker) | SQLite storage directory |
| `DARUMA_PORT` | `8080` | Server port |
| `ANTHROPIC_API_KEY` | — | Required for Claude CLI |

## CLI

```bash
# Task management
daruma tasks list
daruma tasks create --name "Daily Digest" --prompt "Summarize today" --cron "0 8 * * 1-5"
daruma tasks show <id-or-name>
daruma tasks edit <id-or-name> --name "New Name" --enable
daruma tasks delete <id-or-name> -y

# Run a task (blocks, streams output)
daruma run <id-or-name>

# View run history
daruma runs list --task <id-or-name> --limit 10
daruma runs show <run-id>
```

Tasks can be referenced by full ID, partial ID prefix, or name.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create task |
| PUT | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |
| POST | `/api/tasks/{id}/run` | Manual trigger |
| POST | `/api/trigger/{task_name}` | Webhook trigger |
| GET | `/api/runs?task_id=` | Run history |
| GET | `/api/runs/{id}` | Run detail + logs |
| GET | `/health` | Health check |

## Example Task

```json
{
  "name": "Morning Calendar Digest",
  "prompt": "Get my calendar events for today and summarize them.",
  "cron_expression": "0 8 * * 1-5",
  "allowed_tools": "Bash,Read",
  "enabled": true
}
```

## Tests

```bash
uv run pytest tests/ -v
```

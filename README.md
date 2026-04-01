# Daruma

Lightweight task scheduler with a web UI that runs Claude CLI agents on cron schedules, manual triggers, or webhooks.

## Stack

| Component | Choice |
|-----------|--------|
| Backend | Python 3.12 + FastAPI |
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

Open **http://localhost:8080/ui/**

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `DARUMA_DATA_DIR` | `./data` (local) or `/data` (Docker) | SQLite storage directory |
| `DARUMA_PORT` | `8080` | Server port |
| `ANTHROPIC_API_KEY` | — | Required for Claude CLI |

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

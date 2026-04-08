# Daruma

Task scheduler for [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) automations. Run agents on cron schedules, chain them into pipelines, attach reusable skills, and manage everything from a web UI or CLI.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

<!-- TODO: add screenshot of web UI -->

## Why Daruma?

Claude Code's built-in scheduling runs in the cloud, no access to your local calendar, MCP servers, or filesystem. Daruma runs on **your machine**, so your agents can use everything you can.

- **Cron scheduling**, run tasks on any cron expression, manually, or via webhook
- **Pipelines**, chain tasks sequentially, each step's output feeds the next step's prompt
- **Skills**, reusable instruction sets (markdown files) attached to tasks as system prompts
- **Web UI + CLI + API**, manage tasks however you prefer

## Quick Start

### Local

```bash
# Install
uv sync --all-extras

# Run the server
uv run daruma server

# Or install as macOS service (auto-starts on login)
uv run daruma service install
```

### Docker

```bash
docker compose up --build
```

Open **http://localhost:8080/ui/** or use the CLI.

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `DARUMA_DATA_DIR` | `./data` (local) / `/data` (Docker) | SQLite storage directory |
| `DARUMA_PORT` | `8080` | Server port |
| `DARUMA_HOST` | `0.0.0.0` | Bind address |
| `ANTHROPIC_API_KEY` |, | Required for Claude CLI |

## Features

### Tasks

A task has a **prompt**, optional **cron expression**, **model** (sonnet/opus/haiku), and optional **allowed tools**.

```bash
# Create a scheduled task
daruma tasks create --name "daily-digest" \
  --prompt "Summarize my calendar for today" \
  --cron "0 8 * * 1-5"

# Run manually
daruma run daily-digest

# Trigger via webhook
curl -X POST http://localhost:8080/api/trigger/daily-digest
```

### Skills

Skills are markdown files in `~/.claude/skills/{name}/SKILL.md` with YAML frontmatter. Daruma syncs them on startup and lets you attach them to tasks as system prompts.

```
~/.claude/skills/
  jira/SKILL.md          # Jira interaction instructions
  calendar-api/SKILL.md  # Calendar reading instructions
  sentry/SKILL.md        # Error triage instructions
```

Attach skills to a task via the web UI or API:

```bash
curl -X PUT http://localhost:8080/api/tasks/{id}/skills \
  -H "Content-Type: application/json" \
  -d '{"skill_ids": ["skill-uuid-1", "skill-uuid-2"]}'
```

### Pipelines

Chain multiple tasks into a sequential pipeline. Each step's stdout is prepended to the next step's prompt, enabling multi-agent workflows.

```
Step 1: "Read my calendar"     → stdout: "3 meetings today..."
Step 2: "Log hours to Jira"    → receives: "3 meetings today..." + its own prompt
Step 3: "Send Slack summary"   → receives: combined output + its own prompt
```

Pipelines can also be scheduled with cron or triggered manually.

### macOS Service

```bash
daruma service install   # Install launchd agent (auto-starts on login)
daruma service status    # Check if running
daruma service stop      # Stop the service
daruma service uninstall # Remove the service
```

## CLI Reference

```bash
# Task management
daruma tasks list
daruma tasks create --name "name" --prompt "prompt" --cron "0 8 * * *"
daruma tasks show <id-or-name>
daruma tasks edit <id-or-name> --name "New Name" --enable
daruma tasks delete <id-or-name> -y

# Run a task (blocks, streams output)
daruma run <id-or-name>

# View run history
daruma runs list --task <id-or-name> --limit 10
daruma runs show <run-id>

# Pipeline management
daruma pipelines list
daruma pipelines run <id-or-name>

# Server management
daruma server                # Start dev server
daruma service install       # Install as macOS service
daruma service status        # Check service status
```

Tasks can be referenced by full ID, partial ID prefix, or name.

## API

| Method | Path | Purpose |
|--------|------|---------|
| **Tasks** | | |
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create task |
| PUT | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |
| POST | `/api/tasks/{id}/run` | Manual trigger |
| POST | `/api/trigger/{name}` | Webhook trigger |
| **Skills** | | |
| GET | `/api/skills` | List skills |
| GET | `/api/tasks/{id}/skills` | Skills attached to task |
| PUT | `/api/tasks/{id}/skills` | Attach skills to task |
| **Pipelines** | | |
| GET | `/api/pipelines` | List pipelines |
| POST | `/api/pipelines` | Create pipeline |
| POST | `/api/pipelines/{id}/run` | Run pipeline |
| **Runs** | | |
| GET | `/api/runs?task_id=` | Run history |
| GET | `/api/runs/{id}` | Run detail + logs |
| POST | `/api/runs/{id}/cancel` | Cancel running task |
| **Health** | | |
| GET | `/health` | Health check |

## Architecture

```
FastAPI ──→ Service layer ──→ CRUD ──→ SQLite (WAL mode)
  │                │
  │                ├──→ APScheduler (cron sync)
  │                └──→ Claude CLI subprocess (stream-json parsing)
  │
  ├── Web UI (Jinja2 + HTMX)
  ├── REST API
  └── CLI (Click + rich)
```

| Component | Choice |
|-----------|--------|
| Backend | Python 3.11+ / FastAPI |
| Database | SQLite + Alembic migrations |
| Scheduler | APScheduler |
| UI | Jinja2 + HTMX |
| CLI | Click + rich |
| Agent | Claude CLI (`claude -p --output-format stream-json`) |
| Package manager | uv |

See [CLAUDE.md](CLAUDE.md) for detailed code conventions and architecture decisions.

## Development

```bash
# Setup
uv sync --all-extras
source .venv/bin/activate

# Tests
pytest

# Lint + format
uvx ruff check --fix .
uvx ruff format .

# New migration
alembic revision --autogenerate -m "description"
```

274 tests covering CRUD, API, CLI, services, runner, and UI layers.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)

# Claude Automations Runner — Design Document

> Date: 2026-04-01
> Status: Draft (MVP)

## Overview

Lightweight Docker-based task scheduler with a web UI that runs Claude CLI agents on cron schedules, manual triggers, or webhooks. A simpler alternative to n8n for Claude-specific automations.

## Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Backend | Python + FastAPI | Consistent with existing projects |
| UI | Jinja2 + HTMX | No build step, live updates via HTML attributes |
| Database | SQLite | Single file, zero config, sufficient for single-user |
| Scheduler | APScheduler | In-process cron, no external dependency |
| Agent | Claude CLI (`claude -p`) | Runs as subprocess with configurable permissions |
| Deployment | Docker | Single container, volume for persistence |

## Architecture

```
┌─────────────────────────────────────┐
│         Docker Container            │
│                                     │
│  FastAPI (port 8080)                │
│  ├── /ui/*        → Jinja2 + HTMX  │
│  ├── /api/tasks   → CRUD tasks     │
│  ├── /api/trigger  → webhook entry  │
│  └── /api/runs    → run history     │
│                                     │
│  APScheduler (in-process)           │
│  └── executes: claude -p "..."      │
│                                     │
│  SQLite (file: /data/automations.db)│
│  ├── tasks (name, cron, prompt,     │
│  │         allowed_tools, enabled)  │
│  └── runs  (task_id, status,        │
│             started_at, duration,   │
│             stdout, stderr)         │
│                                     │
│  Claude CLI (installed in image)    │
└─────────────────────────────────────┘
```

### Data Flow

1. APScheduler fires at cron time (or webhook/manual trigger hits API)
2. Runner spawns `claude -p "<prompt>" --allowedTools <tools>` as subprocess
3. Captures stdout/stderr, exit code, duration
4. Stores run result in SQLite
5. UI polls via HTMX for live updates

### Volume Mounts

- `/data` — SQLite persistence
- Host directories as needed (so Claude can access local projects/files)

## Data Model

### tasks

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| name | TEXT | Human-readable name |
| prompt | TEXT | The prompt sent to Claude CLI |
| cron_expression | TEXT | Cron schedule (nullable — webhook/manual only) |
| allowed_tools | TEXT | Comma-separated tools (nullable — no restrictions) |
| enabled | BOOLEAN | Toggle on/off without deleting |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### runs

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| task_id | TEXT (FK) | References tasks.id |
| trigger | TEXT | "cron", "manual", or "webhook" |
| status | TEXT | "running", "success", "failed" |
| started_at | DATETIME | |
| finished_at | DATETIME | Nullable while running |
| duration_ms | INTEGER | |
| stdout | TEXT | Claude's full response |
| stderr | TEXT | Error output if any |
| exit_code | INTEGER | |

## UI Pages

### 1. Tasks List (`/ui/`)

- Table: name, cron, enabled toggle, last run status, "Run now" button
- HTMX: toggle enabled/disabled inline, "Run now" triggers without page reload
- Link to create new task

### 2. Task Detail (`/ui/tasks/{id}`)

- Edit form: name, prompt, cron expression, allowed tools
- Run history table below: trigger type, status, duration, timestamp
- Click a run to expand and see logs

### 3. Run Logs (`/ui/runs/{id}`)

- Full stdout/stderr output
- Status, duration, trigger info
- Auto-refreshes via HTMX polling while status is "running"

## API Endpoints

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
  "prompt": "Get my calendar events for today and summarize them in a brief morning digest. Highlight any conflicts or back-to-back meetings.",
  "cron_expression": "0 8 * * 1-5",
  "allowed_tools": "bash,read",
  "enabled": true
}
```

## Future Considerations (not MVP)

- Task chaining (output of one feeds into another)
- Notifications on failure (Slack, email)
- Dashboard stats (success rate, avg duration)
- Task templates / presets
- API key auth for webhook triggers

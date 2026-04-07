# Task Pipelines — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow chaining tasks into linear pipelines where each task's output is prepended to the next task's prompt.

**Architecture:** New `pipelines`, `pipeline_steps`, and `pipeline_runs` tables. A pipeline executor loops through steps sequentially, calling `execute_task` and passing stdout forward. Stops on first failure. No changes to the runner — prompt prepend happens at the service layer.

**Tech Stack:** SQLAlchemy (models), Pydantic (schemas), Alembic (migration), Click (CLI), Jinja2 (UI)

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pipeline type | Linear only | Fan-out and conditional add complexity; can layer on later |
| Output passing | Prepend to next prompt | Simplest, always works, LLM handles "context then instruction" naturally |
| Pipeline definition | New `Pipeline` model | First-class entity, tasks reusable across pipelines |
| Scheduling | Manual only (v1) | Avoids conflicts with task-level cron; easy to add later |
| Failure behavior | Stop immediately | Output from failed step is unreliable; no point continuing |

## Future Considerations (not in v1)

- Pipeline-level cron scheduling
- Parallel fan-out steps
- Configurable continue-on-failure per step
- Step-level timeout overrides
- Pipeline-level env vars (merged with task-level)

---

## Data Model

### New tables

**`pipelines`**
- `id` (UUID, PK)
- `name` (string, unique)
- `description` (text, nullable)
- `enabled` (bool, default true)
- `created_at`, `updated_at`

**`pipeline_steps`**
- `id` (UUID, PK)
- `pipeline_id` (FK → pipelines, cascade delete)
- `task_id` (FK → tasks)
- `step_order` (int, 0-indexed)
- Unique constraint on `(pipeline_id, step_order)`

**`pipeline_runs`**
- `id` (UUID, PK)
- `pipeline_id` (FK → pipelines)
- `status` (string: `running`, `success`, `failed`)
- `trigger` (string: `manual`, future: `cron`)
- `current_step` (int, nullable) — which step is executing
- `started_at`, `finished_at`, `duration_ms`

### Modified tables

**`runs`** — add:
- `pipeline_run_id` (FK → pipeline_runs, nullable)

Individual task runs: `pipeline_run_id = NULL`. Pipeline step runs: linked to their pipeline run.

---

## Execution Flow

1. Create a `pipeline_run` record (status=`running`)
2. Load steps ordered by `step_order`
3. For each step:
   - If step 0: run task with its original prompt
   - If step N>0: prepend previous stdout to prompt:
     ```
     Output from previous step:

     {previous_stdout}

     ---

     {original_task_prompt}
     ```
   - Create a normal `Run` record with `pipeline_run_id` set
   - Execute via existing `execute_task`
   - Update `pipeline_run.current_step`
   - On failure: mark `pipeline_run` as `failed`, stop
4. All steps succeed: mark `pipeline_run` as `success`

The task's original prompt stays unchanged in the DB. Prepend is execution-time only.

---

## Validation and Edge Cases

- Creating a pipeline with zero steps → error
- Referencing a non-existent task name → error at creation time
- Deleting a task used in a pipeline → block with error message
- Disabled task hit during pipeline run → fail the pipeline run
- Empty stdout from a step → next step gets its own prompt with no prepend

---

## New Files

| File | Purpose |
|------|---------|
| `app/models/pipeline.py` | Pipeline, PipelineStep ORM models |
| `app/models/pipeline_run.py` | PipelineRun ORM model |
| `app/schemas/pipeline.py` | Pydantic schemas for pipelines and pipeline runs |
| `app/crud/pipelines.py` | CRUD for pipelines and steps |
| `app/crud/pipeline_runs.py` | CRUD for pipeline runs |
| `app/routers/pipelines.py` | API endpoints for pipeline CRUD |
| `app/routers/pipeline_triggers.py` | Run/cancel pipeline endpoints |
| `templates/pipelines_list.html` | Pipeline list page |
| `templates/pipeline_detail.html` | Pipeline detail + run history |
| `templates/pipeline_form.html` | Create/edit form |
| `templates/pipeline_run_detail.html` | Pipeline run detail with per-step view |
| Alembic migration | Three new tables + `runs.pipeline_run_id` |

## Modified Files

| File | Change |
|------|--------|
| `app/models/run.py` | Add nullable `pipeline_run_id` FK |
| `app/services.py` | Add `PipelineService` and `execute_pipeline` function |
| `app/cli.py` | Add `pipelines` command group |
| `app/routers/ui.py` | Add pipeline UI routes |
| `app/main.py` | Register new routers |
| `templates/base.html` | Add "Pipelines" to nav |

## Unchanged

- `app/runner.py` — prompt prepend happens before calling runner
- `app/crud/tasks.py` — tasks remain unaware of pipelines
- All existing task/run tests — pipelines are additive

---

## Tasks

### Task 1: Models + Schemas + Migration

**New files:** `app/models/pipeline.py`, `app/models/pipeline_run.py`, `app/schemas/pipeline.py`
**Modified:** `app/models/run.py`, `tests/test_db.py`
**Migration:** Add `pipelines`, `pipeline_steps`, `pipeline_runs` tables and `runs.pipeline_run_id` FK

Models follow existing conventions: UUID PK, `utcnow()` defaults, one model per file. Schemas follow existing pattern: separate Create/Update/Response with `ConfigDict(from_attributes=True)`.

Tests: verify tables exist with expected columns (same pattern as `test_tasks_table_has_expected_columns`).

### Task 2: CRUD layer for pipelines

**New files:** `app/crud/pipelines.py`, `app/crud/pipeline_runs.py`
**Tests:** `tests/test_crud_pipelines.py`

Pipeline CRUD:
- `create(session, name, description, task_ids)` — creates pipeline + ordered steps
- `get`, `get_by_name`, `get_all`
- `update(session, pipeline_id, **fields)` — update name/description/enabled
- `update_steps(session, pipeline_id, task_ids)` — replace steps (delete old, insert new)
- `delete` — cascade deletes steps

Pipeline run CRUD:
- `create(session, pipeline_id, trigger)` — creates with status=running
- `update_step(session, run_id, current_step)` — update progress
- `complete(session, run_id, status, ...)` — mark finished
- `get`, `get_all(pipeline_id=None)`

Validate: task_ids must all exist, at least one step required.

### Task 3: Pipeline executor in services

**Modified:** `app/services.py`
**Tests:** `tests/test_services.py` (add pipeline tests)

Add `PipelineService` class (list, create, get, update, delete) and `execute_pipeline` function.

`execute_pipeline` logic:
- Create pipeline_run
- Loop through steps in order
- Step 0: call `execute_task` normally
- Step N>0: build modified prompt with previous stdout prepended
- Pass `pipeline_run_id` to `run_crud.create` for each step's run
- On step failure: mark pipeline_run failed, return
- On all success: mark pipeline_run success, return

Use mock runners in tests (same pattern as existing `TestExecuteTask`).

### Task 4: CLI — pipelines command group

**Modified:** `app/cli.py`
**Tests:** `tests/test_cli.py` (add pipeline tests)

Commands:
- `daruma pipelines list [--json]`
- `daruma pipelines create --name "X" --steps "Task A,Task B"`
- `daruma pipelines show <name> [--json]`
- `daruma pipelines edit <name> [--name] [--steps] [--description] [--enable/--disable]`
- `daruma pipelines delete <name> [-y]`
- `daruma pipelines run <name>` — synchronous, streams each step with headers

Step output during run: print step headers like `[Step 1/3] Running: Morning Calendar Digest...` then stream that step's output, then `[Step 1/3] Done (success, 12345ms)`.

### Task 5: API router

**New files:** `app/routers/pipelines.py`, `app/routers/pipeline_triggers.py`
**Modified:** `app/main.py`
**Tests:** `tests/test_api_pipelines.py`

REST endpoints:
- `GET /api/pipelines` — list
- `POST /api/pipelines` — create
- `GET /api/pipelines/{id}` — get (includes steps)
- `PUT /api/pipelines/{id}` — update
- `DELETE /api/pipelines/{id}` — delete
- `POST /api/pipelines/{id}/run` — trigger (background)
- `GET /api/pipeline-runs/{id}` — run detail with step runs

### Task 6: UI — templates and routes

**New files:** `templates/pipelines_list.html`, `templates/pipeline_detail.html`, `templates/pipeline_form.html`, `templates/pipeline_run_detail.html`
**Modified:** `app/routers/ui.py`, `templates/base.html`

Pages:
- `/ui/pipelines/` — list with name, step count, last run status, "Run now" button
- `/ui/pipelines/new` — form: name, description, steps textarea (one task name per line)
- `/ui/pipelines/{id}` — detail: steps in order, run history table
- `/ui/pipelines/{id}/edit` — edit form
- `/ui/pipeline-runs/{id}` — run detail: each step with status, duration, output link

Add "Pipelines" link to base nav template.

### Task 7: Task deletion guard

**Modified:** `app/crud/tasks.py` or `app/services.py`
**Tests:** add to existing test files

When deleting a task, check if it's referenced by any pipeline step. If so, raise an error with the pipeline name(s). This prevents orphaned pipeline steps.

### Task 8: Integration test — end-to-end pipeline

**Tests:** `tests/test_pipeline_integration.py`

Create two tasks with mock runners. First returns known output. Second's runner verifies it received the prepended output. Run the pipeline, assert:
- Pipeline run status = success
- Both task runs exist with correct pipeline_run_id
- Second task received prepended output
- Pipeline run duration is set

Also test failure case: first task fails → pipeline run = failed, second task never runs.

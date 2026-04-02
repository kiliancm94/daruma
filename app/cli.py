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


# ── Tasks ──────────────────────────────────────────────


@cli.group()
def tasks():
    """Manage tasks."""


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
    # Header
    click.echo(f"  {'ID':<10} {'Name':<30} {'Schedule':<20} {'Status'}")
    click.echo(f"  {'─' * 10} {'─' * 30} {'─' * 20} {'─' * 10}")
    for t in items:
        status = "enabled" if t["enabled"] else "disabled"
        cron = t["cron_expression"] or "manual only"
        click.echo(f"  {t['id'][:8]:<10} {t['name']:<30} {cron:<20} [{status}]")


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
    """Show task details. Accepts full ID, partial ID, or name."""
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


@runs.command("list")
@click.option("--task", "task_id", default=None, help="Filter by task ID or name")
@click.option("--limit", default=20, help="Max runs to show")
def runs_list(task_id, limit):
    """List recent runs."""
    conn = _connect()
    run_svc = RunService(RunRepo(conn))

    resolved_task_id = None
    if task_id:
        task_svc = TaskService(TaskRepo(conn))
        task = _resolve_task(task_svc, task_id)
        resolved_task_id = task["id"]

    items = run_svc.list(task_id=resolved_task_id)[:limit]
    conn.close()
    if not items:
        click.echo("No runs found.")
        return
    click.echo(f"  {'ID':<10} {'Status':<10} {'Trigger':<10} {'Duration':<12} {'Started'}")
    click.echo(f"  {'─' * 10} {'─' * 10} {'─' * 10} {'─' * 12} {'─' * 20}")
    for r in items:
        duration = f"{r['duration_ms']}ms" if r["duration_ms"] else "…"
        click.echo(
            f"  {r['id'][:8]:<10} {r['status']:<10} {r['trigger']:<10} {duration:<12} {r['started_at']}"
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
    if run.get("stdout"):
        click.echo(f"\n--- stdout ---\n{run['stdout']}")
    if run.get("stderr"):
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
    click.echo(f"Running task: {task['name']}…\n")

    last_output = [""]

    def _on_output(stdout: str, activity: str) -> None:
        # Print new content since last callback
        if stdout and stdout != last_output[0]:
            new = stdout[len(last_output[0]):]
            if new:
                click.echo(new, nl=False)
            last_output[0] = stdout

    result = execute_task(
        task, run_repo, trigger="manual", on_output=_on_output,
    )
    conn.close()
    click.echo()
    click.echo(
        f"\nStatus: {result['status']}  "
        f"Exit: {result['exit_code']}  "
        f"Duration: {result['duration_ms']}ms"
    )
    if result["status"] != "success":
        sys.exit(1)


# ── Helpers ────────────────────────────────────────────


def _resolve_task(svc: TaskService, identifier: str) -> dict:
    """Resolve a task by full ID, partial ID (prefix), or name."""
    # Try exact ID
    try:
        return svc.get(identifier)
    except TaskNotFoundError:
        pass
    # Try by name
    try:
        return svc.get_by_name(identifier)
    except TaskNotFoundError:
        pass
    # Try prefix match
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

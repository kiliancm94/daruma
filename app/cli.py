"""Daruma CLI — manage and run Claude automation tasks."""

import sys

import click
from rich.console import Console
from rich.table import Table

from app.config import DB_PATH
from app.db import init_db, get_session
from app.runner import VALID_MODELS, DEFAULT_MODEL
from app.schemas.task import TaskResponse, OutputFormat, OutputDestination
from app.schemas.run import RunResponse
from app.crud import skills as skill_crud
from app.crud import task_skills as task_skill_crud
from app.services import (
    TaskService,
    RunService,
    SkillService,
    TaskNotFoundError,
    RunNotFoundError,
    execute_task,
    _parse_skill_frontmatter,
)

console = Console()


def _connect():
    init_db(DB_PATH)
    return get_session()


@click.group()
def cli():
    """Daruma — Claude automation task runner."""


# ── Tasks ──────────────────────────────────────────────


@cli.group()
def tasks():
    """Manage tasks."""


@tasks.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_tasks(as_json):
    """List all tasks."""
    session = _connect()
    task_service = TaskService(session)
    items = task_service.list()
    session.close()
    if not items:
        click.echo("No tasks found.")
        return
    if as_json:
        data = [TaskResponse.model_validate(t).model_dump() for t in items]
        console.print_json(data=data)
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name")
    table.add_column("Model", style="cyan")
    table.add_column("Schedule", style="dim")
    table.add_column("Status")
    for t in items:
        status = "[green]enabled[/green]" if t.enabled else "[red]disabled[/red]"
        cron = t.cron_expression or "manual only"
        table.add_row(t.id[:8], t.name, t.model, cron, status)
    console.print(table)


@tasks.command("create")
@click.option("--name", required=True, help="Task name")
@click.option("--prompt", required=True, help="Claude prompt")
@click.option("--cron", default=None, help="Cron expression (5-field)")
@click.option("--tools", default=None, help="Comma-separated allowed tools")
@click.option(
    "--model",
    type=click.Choice(VALID_MODELS, case_sensitive=False),
    default=DEFAULT_MODEL,
    show_default=True,
    help="Claude model to use",
)
@click.option("--disabled", is_flag=True, help="Create in disabled state")
@click.option(
    "--output-format",
    type=click.Choice(list(OutputFormat), case_sensitive=False),
    default=None,
    help="Output format: text, json, or md",
)
@click.option(
    "--output-dest",
    default=None,
    help=f"Where to write output: a file path, a folder path, or '{OutputDestination.pipeline}' for task chaining",
)
def create_task(name, prompt, cron, tools, model, disabled, output_format, output_dest):
    """Create a new task."""
    session = _connect()
    task_service = TaskService(session)
    task = task_service.create(
        name=name,
        prompt=prompt,
        cron_expression=cron,
        allowed_tools=tools,
        model=model,
        enabled=not disabled,
        output_format=output_format,
        output_destination=output_dest,
    )
    session.close()
    click.echo(f"Created task: {task.name} ({task.id[:8]})")


@tasks.command("show")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_task(task_id, as_json):
    """Show task details. Accepts full ID, partial ID, or name."""
    session = _connect()
    task_service = TaskService(session)
    task = _resolve_task(task_service, task_id)
    session.close()
    if as_json:
        console.print_json(data=TaskResponse.model_validate(task).model_dump())
        return
    click.echo(f"ID:      {task.id}")
    click.echo(f"Name:    {task.name}")
    click.echo(f"Prompt:  {task.prompt}")
    click.echo(f"Model:   {task.model}")
    click.echo(f"Cron:    {task.cron_expression or 'none'}")
    click.echo(f"Tools:   {task.allowed_tools or 'all'}")
    click.echo(f"Enabled: {task.enabled}")
    click.echo(f"Output format: {task.output_format or 'text (default)'}")
    click.echo(f"Output dest:   {task.output_destination or 'none'}")
    click.echo(f"Created: {task.created_at}")
    click.echo(f"Updated: {task.updated_at}")


@tasks.command("edit")
@click.argument("task_id")
@click.option("--name", default=None)
@click.option("--prompt", default=None)
@click.option("--cron", default=None)
@click.option("--tools", default=None)
@click.option(
    "--model",
    type=click.Choice(VALID_MODELS, case_sensitive=False),
    default=None,
    help="Claude model to use",
)
@click.option(
    "--skills",
    "skill_names",
    default=None,
    help="Comma-separated skill names to assign",
)
@click.option("--enable/--disable", default=None)
@click.option(
    "--output-format",
    type=click.Choice(list(OutputFormat), case_sensitive=False),
    default=None,
    help="Output format: text, json, or md",
)
@click.option(
    "--output-dest",
    default=None,
    help=f"Where to write output: a file path, a folder path, or '{OutputDestination.pipeline}' for task chaining",
)
def edit_task(
    task_id,
    name,
    prompt,
    cron,
    tools,
    model,
    skill_names,
    enable,
    output_format,
    output_dest,
):
    """Update a task."""
    session = _connect()
    task_service = TaskService(session)
    task = _resolve_task(task_service, task_id)
    task_name = task.name
    task_pk = task.id
    fields = {}
    if name is not None:
        fields["name"] = name
    if prompt is not None:
        fields["prompt"] = prompt
    if cron is not None:
        fields["cron_expression"] = cron
    if tools is not None:
        fields["allowed_tools"] = tools
    if model is not None:
        fields["model"] = model
    if enable is not None:
        fields["enabled"] = enable
    if output_format is not None:
        fields["output_format"] = output_format
    if output_dest is not None:
        fields["output_destination"] = output_dest
    if not fields and skill_names is None:
        click.echo("Nothing to update.")
        return
    if fields:
        updated = task_service.update(task_pk, **fields)
        task_name = updated.name
    if skill_names is not None:
        names = [n.strip() for n in skill_names.split(",") if n.strip()]
        skill_ids = []
        for sn in names:
            sk = skill_crud.get_by_name(session, sn)
            if not sk:
                click.echo(f"Skill not found: {sn}", err=True)
                raise SystemExit(1)
            skill_ids.append(sk.id)
        task_skill_crud.replace(session, task_pk, skill_ids)
    session.close()
    click.echo(f"Updated task: {task_name} ({task_pk[:8]})")


@tasks.command("delete")
@click.argument("task_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_task(task_id, yes):
    """Delete a task."""
    session = _connect()
    task_service = TaskService(session)
    task = _resolve_task(task_service, task_id)
    if not yes:
        click.confirm(f"Delete task '{task.name}'?", abort=True)
    task_service.delete(task.id)
    session.close()
    click.echo(f"Deleted task: {task.name}")


# ── Runs ───────────────────────────────────────────────


@cli.group()
def runs():
    """View run history."""


@runs.command("list")
@click.option("--task", "task_id", default=None, help="Filter by task ID or name")
@click.option("--limit", default=20, help="Max runs to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_runs(task_id, limit, as_json):
    """List recent runs."""
    session = _connect()
    run_service = RunService(session)

    resolved_task_id = None
    if task_id:
        task_service = TaskService(session)
        task = _resolve_task(task_service, task_id)
        resolved_task_id = task.id

    items = run_service.list(task_id=resolved_task_id)[:limit]
    session.close()
    if not items:
        click.echo("No runs found.")
        return
    if as_json:
        data = [RunResponse.model_validate(r).model_dump() for r in items]
        console.print_json(data=data)
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Trigger", style="dim")
    table.add_column("Duration", style="dim")
    table.add_column("Started")
    for r in items:
        duration = f"{r.duration_ms}ms" if r.duration_ms else "..."
        status_style = {"success": "green", "failed": "red", "running": "yellow"}.get(
            r.status, ""
        )
        table.add_row(
            r.id[:8],
            f"[{status_style}]{r.status}[/{status_style}]"
            if status_style
            else r.status,
            r.trigger,
            duration,
            r.started_at,
        )
    console.print(table)


@runs.command("show")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_run(run_id, as_json):
    """Show run details and output."""
    session = _connect()
    run_service = RunService(session)
    try:
        run = run_service.get(run_id)
    except RunNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        raise SystemExit(1)
    session.close()
    if as_json:
        console.print_json(data=RunResponse.model_validate(run).model_dump())
        return
    click.echo(f"ID:       {run.id}")
    click.echo(f"Task:     {run.task_id}")
    click.echo(f"Trigger:  {run.trigger}")
    click.echo(f"Status:   {run.status}")
    click.echo(f"Started:  {run.started_at}")
    click.echo(f"Finished: {run.finished_at or '...'}")
    click.echo(f"Duration: {run.duration_ms or '...'}ms")
    click.echo(f"Exit:     {run.exit_code}")
    if run.stdout:
        click.echo(f"\n--- stdout ---\n{run.stdout}")
    if run.stderr:
        click.echo(f"\n--- stderr ---\n{run.stderr}")


# ── Skills ─────────────────────────────────────────────


@cli.group()
def skills():
    """Manage skills."""


@skills.command("list")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include global skills from ~/.claude/skills/",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_skills(show_all, as_json):
    """List skills."""
    session = _connect()
    skill_service = SkillService(session)
    if show_all:
        items = skill_service.list_all()
    else:
        items = [
            {"name": s.name, "description": s.description, "source": s.source}
            for s in skill_service.list_local()
        ]
    session.close()
    if not items:
        click.echo("No skills found.")
        return
    if as_json:
        console.print_json(data=items)
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Source", style="dim")
    for s in items:
        table.add_row(s["name"], s.get("description", ""), s.get("source", "local"))
    console.print(table)


@skills.command("create")
@click.option("--name", required=True, help="Skill name")
@click.option("--description", default="", help="Short description")
@click.option("--content", required=True, help="Skill content (markdown)")
def create_skill(name, description, content):
    """Create a new skill."""
    session = _connect()
    skill_service = SkillService(session)
    skill_service.create(name=name, description=description, content=content)
    session.close()
    click.echo(f"Created skill: {name}")


@skills.command("show")
@click.argument("name")
def show_skill(name):
    """Show skill details and content."""
    session = _connect()
    skill = skill_crud.get_by_name(session, name)
    if not skill:
        click.echo(f"Skill not found: {name}", err=True)
        session.close()
        raise SystemExit(1)
    click.echo(f"Name:        {skill.name}")
    click.echo(f"Description: {skill.description}")
    click.echo(f"Source:      {skill.source}")
    click.echo(f"\n--- content ---\n{skill.content}")
    session.close()


@skills.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_skill(name, yes):
    """Delete a skill."""
    session = _connect()
    skill = skill_crud.get_by_name(session, name)
    if not skill:
        click.echo(f"Skill not found: {name}", err=True)
        session.close()
        raise SystemExit(1)
    if not yes:
        click.confirm(f"Delete skill '{name}'?", abort=True)
    skill_crud.delete(session, skill.id)
    session.close()
    click.echo(f"Deleted skill: {name}")


@skills.command("import")
@click.argument("file_path", type=click.Path(exists=True))
def import_skill(file_path):
    """Import a skill from a SKILL.md file."""
    from pathlib import Path

    parsed = _parse_skill_frontmatter(Path(file_path))
    session = _connect()
    skill_service = SkillService(session)
    skill_service.create(
        name=parsed["name"],
        description=parsed.get("description", ""),
        content=parsed["content"],
    )
    session.close()
    click.echo(f"Imported skill: {parsed['name']}")


@skills.command("sync")
def sync_skills():
    """Sync global skills from ~/.claude/skills/ into the database."""
    session = _connect()
    skill_service = SkillService(session)
    result = skill_service.sync_global()
    session.close()
    click.echo(
        f"Synced: {result['created']} created, "
        f"{result['updated']} updated, "
        f"{result['unchanged']} unchanged"
    )


# ── Run (execute) ─────────────────────────────────────


@cli.command("run")
@click.argument("task_name_or_id")
def run_task(task_name_or_id):
    """Run a task now (blocks until complete, streams output)."""
    session = _connect()
    task_service = TaskService(session)

    task = _resolve_task(task_service, task_name_or_id)
    click.echo(f"Running task: {task.name}...\n")

    last_output = [""]

    def _on_output(stdout: str, activity: str) -> None:
        if stdout and stdout != last_output[0]:
            new = stdout[len(last_output[0]) :]
            if new:
                click.echo(new, nl=False)
            last_output[0] = stdout

    result = execute_task(
        task,
        session,
        trigger="manual",
        on_output=_on_output,
    )
    session.close()
    click.echo()
    click.echo(
        f"\nStatus: {result.status}  "
        f"Exit: {result.exit_code}  "
        f"Duration: {result.duration_ms}ms"
    )
    if result.status != "success":
        sys.exit(1)


# ── Helpers ────────────────────────────────────────────


def _resolve_task(task_service: TaskService, identifier: str):
    """Resolve a task by full ID, partial ID (prefix), or name."""
    try:
        return task_service.get(identifier)
    except TaskNotFoundError:
        pass
    try:
        return task_service.get_by_name(identifier)
    except TaskNotFoundError:
        pass
    all_tasks = task_service.list()
    matches = [t for t in all_tasks if t.id.startswith(identifier)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        click.echo(f"Ambiguous ID prefix '{identifier}', matches:", err=True)
        for t in matches:
            click.echo(f"  {t.id}  {t.name}", err=True)
        raise SystemExit(1)
    click.echo(f"Task not found: {identifier}", err=True)
    raise SystemExit(1)

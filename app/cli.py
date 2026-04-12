"""Daruma CLI — manage and run Claude automation tasks."""

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from app.config import DB_PATH, PORT, HOST, HOSTNAME
from app.utils.env_vars import parse_env_pairs
from app.db import init_db, get_session
from app.runner import VALID_MODELS, DEFAULT_MODEL
from app.schemas.task import TaskResponse, OutputFormat, OutputDestination
from app.schemas.run import RunResponse
from app.crud import task_skills as task_skill_crud
from app.services import (
    TaskService,
    RunService,
    SkillService,
    PipelineService,
    TaskNotFoundError,
    RunNotFoundError,
    SkillNotFoundError,
    PipelineNotFoundError,
    execute_task,
    execute_pipeline,
    _parse_skill_frontmatter,
)
from app.schemas.pipeline import PipelineTrigger
from app.schemas.pipeline import PipelineResponse

console = Console()


def _connect():
    init_db(DB_PATH)
    return get_session()


@click.group()
def cli():
    """Daruma — Claude automation task runner."""


# ── Server ─────────────────────────────────────────────


@cli.command("server")
@click.option("--host", default=HOST, show_default=True, help="Bind address")
@click.option("--port", default=PORT, show_default=True, help="Bind port")
def server(host, port):
    """Start the Daruma web server."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port)


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
@click.option(
    "--env",
    "env_pairs",
    multiple=True,
    help="Environment variable KEY=VALUE (repeatable)",
)
def create_task(
    name, prompt, cron, tools, model, disabled, output_format, output_dest, env_pairs
):
    """Create a new task."""
    try:
        env_vars = parse_env_pairs(env_pairs)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
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
        env_vars=env_vars,
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
    if task.env_vars:
        env = (
            json.loads(task.env_vars)
            if isinstance(task.env_vars, str)
            else task.env_vars
        )
        masked = ", ".join(f"{k}=***" for k in env)
        click.echo(f"Env vars: {masked}")
    else:
        click.echo("Env vars: none")
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
@click.option(
    "--env",
    "env_pairs",
    multiple=True,
    help="Environment variable KEY=VALUE (repeatable)",
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
    env_pairs,
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
    if env_pairs is not None and len(env_pairs) > 0:
        try:
            fields["env_vars"] = parse_env_pairs(env_pairs)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
    if not fields and skill_names is None:
        click.echo("Nothing to update.")
        return
    if fields:
        updated = task_service.update(task_pk, **fields)
        task_name = updated.name
    if skill_names is not None:
        names = [n.strip() for n in skill_names.split(",") if n.strip()]
        # Validate each skill exists
        skill_service = SkillService(session)
        for sn in names:
            try:
                skill_service.resolve(sn)
            except SkillNotFoundError:
                click.echo(f"Skill not found: {sn}", err=True)
                raise SystemExit(1)
        task_skill_crud.replace(session, task_pk, names)
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
        items = skill_service.list_local()
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
@click.option(
    "--global",
    "is_global",
    is_flag=True,
    help="Create as global skill in ~/.claude/skills/",
)
def create_skill(name, description, content, is_global):
    """Create a new skill."""
    session = _connect()
    skill_service = SkillService(session)
    source = "global" if is_global else "local"
    skill_service.create(
        name=name, description=description, content=content, source=source
    )
    session.close()
    click.echo(f"Created skill: {name}")


@skills.command("show")
@click.argument("name")
def show_skill(name):
    """Show skill details and content."""
    session = _connect()
    skill_service = SkillService(session)
    try:
        skill = skill_service.get(name)
    except SkillNotFoundError:
        click.echo(f"Skill not found: {name}", err=True)
        session.close()
        raise SystemExit(1)
    click.echo(f"Name:        {skill['name']}")
    click.echo(f"Description: {skill['description']}")
    click.echo(f"Source:      {skill['source']}")
    click.echo(f"\n--- content ---\n{skill['content']}")
    session.close()


@skills.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_skill(name, yes):
    """Delete a skill."""
    session = _connect()
    skill_service = SkillService(session)
    try:
        skill_service.get(name)  # verify it exists
    except SkillNotFoundError:
        click.echo(f"Skill not found: {name}", err=True)
        session.close()
        raise SystemExit(1)
    if not yes:
        click.confirm(f"Delete skill '{name}'?", abort=True)
    skill_service.delete(name)
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


# ── Pipelines ──────────────────────────────────────────


@cli.group()
def pipelines():
    """Manage pipelines."""


@pipelines.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_pipelines(as_json):
    """List all pipelines."""
    session = _connect()
    pipeline_service = PipelineService(session)
    items = pipeline_service.list()
    if not items:
        session.close()
        click.echo("No pipelines found.")
        return
    if as_json:
        data = [PipelineResponse.model_validate(p).model_dump() for p in items]
        session.close()
        console.print_json(data=data)
        return
    table = Table(show_edge=False, pad_edge=False)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name")
    table.add_column("Steps", style="cyan")
    table.add_column("Status")
    for pipeline in items:
        status = "[green]enabled[/green]" if pipeline.enabled else "[red]disabled[/red]"
        table.add_row(pipeline.id[:8], pipeline.name, str(len(pipeline.steps)), status)
    session.close()
    console.print(table)


@pipelines.command("create")
@click.option("--name", required=True, help="Pipeline name")
@click.option("--steps", required=True, help="Comma-separated task names")
@click.option("--description", default=None, help="Pipeline description")
def create_pipeline(name, steps, description):
    """Create a new pipeline."""
    session = _connect()
    task_service = TaskService(session)
    task_names = [n.strip() for n in steps.split(",") if n.strip()]
    task_ids = []
    for task_name in task_names:
        try:
            task = task_service.get_by_name(task_name)
        except TaskNotFoundError:
            click.echo(f"Task not found: {task_name}", err=True)
            session.close()
            raise SystemExit(1)
        task_ids.append(task.id)
    pipeline_service = PipelineService(session)
    pipeline = pipeline_service.create(
        name=name,
        description=description,
        task_ids=task_ids,
    )
    session.close()
    click.echo(f"Created pipeline: {pipeline.name} ({pipeline.id[:8]})")


@pipelines.command("show")
@click.argument("name_or_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_pipeline(name_or_id, as_json):
    """Show pipeline details. Accepts full ID, partial ID, or name."""
    session = _connect()
    pipeline_service = PipelineService(session)
    task_service = TaskService(session)
    pipeline = _resolve_pipeline(pipeline_service, name_or_id)
    if as_json:
        data = PipelineResponse.model_validate(pipeline).model_dump()
        session.close()
        console.print_json(data=data)
        return
    click.echo(f"ID:          {pipeline.id}")
    click.echo(f"Name:        {pipeline.name}")
    click.echo(f"Description: {pipeline.description or 'none'}")
    click.echo(f"Enabled:     {pipeline.enabled}")
    click.echo("Steps:")
    for i, step in enumerate(sorted(pipeline.steps, key=lambda s: s.step_order), 1):
        try:
            task = task_service.get(step.task_id)
            task_name = task.name
        except TaskNotFoundError:
            task_name = f"(unknown: {step.task_id[:8]})"
        click.echo(f"  {i}. {task_name}")
    click.echo(f"Created:     {pipeline.created_at}")
    click.echo(f"Updated:     {pipeline.updated_at}")
    session.close()


@pipelines.command("edit")
@click.argument("name_or_id")
@click.option("--name", default=None, help="New pipeline name")
@click.option("--description", default=None, help="New description")
@click.option("--steps", default=None, help="Comma-separated task names")
@click.option("--enable/--disable", default=None)
def edit_pipeline(name_or_id, name, description, steps, enable):
    """Update a pipeline."""
    session = _connect()
    pipeline_service = PipelineService(session)
    pipeline = _resolve_pipeline(pipeline_service, name_or_id)
    pipeline_name = pipeline.name
    pipeline_pk = pipeline.id

    if steps is not None:
        task_service = TaskService(session)
        task_names = [n.strip() for n in steps.split(",") if n.strip()]
        task_ids = []
        for task_name in task_names:
            try:
                task = task_service.get_by_name(task_name)
            except TaskNotFoundError:
                click.echo(f"Task not found: {task_name}", err=True)
                session.close()
                raise SystemExit(1)
            task_ids.append(task.id)
        pipeline_service.update_steps(pipeline_pk, task_ids)

    fields = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if enable is not None:
        fields["enabled"] = enable

    if not fields and steps is None:
        click.echo("Nothing to update.")
        return

    if fields:
        updated = pipeline_service.update(pipeline_pk, **fields)
        pipeline_name = updated.name

    session.close()
    click.echo(f"Updated pipeline: {pipeline_name} ({pipeline_pk[:8]})")


@pipelines.command("delete")
@click.argument("name_or_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_pipeline(name_or_id, yes):
    """Delete a pipeline."""
    session = _connect()
    pipeline_service = PipelineService(session)
    pipeline = _resolve_pipeline(pipeline_service, name_or_id)
    if not yes:
        click.confirm(f"Delete pipeline '{pipeline.name}'?", abort=True)
    pipeline_service.delete(pipeline.id)
    session.close()
    click.echo(f"Deleted pipeline: {pipeline.name}")


@pipelines.command("run")
@click.argument("name_or_id")
def run_pipeline(name_or_id):
    """Run a pipeline now (blocks until complete, streams step output)."""
    session = _connect()
    pipeline_service = PipelineService(session)
    pipeline = _resolve_pipeline(pipeline_service, name_or_id)

    steps = sorted(pipeline.steps, key=lambda s: s.step_order)
    total = len(steps)
    click.echo(f"Running pipeline: {pipeline.name} ({total} steps)\n")

    result = execute_pipeline(
        pipeline,
        session,
        trigger=PipelineTrigger.manual,
    )
    session.close()

    click.echo(f"\nPipeline: {result.status}  Duration: {result.duration_ms}ms")
    if result.status != "success":
        sys.exit(1)


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


# ── Service ─────────────────────────────────────────────


PLIST_LABEL = "com.daruma.server"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def _find_project_root() -> Path:
    """Find the main git checkout root (not a worktree)."""
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        git_dir = Path(result.stdout.strip()).resolve()
        return git_dir.parent
    return Path(__file__).resolve().parent.parent


def _build_plist(host: str, port: int) -> str:
    """Generate launchd plist XML for the Daruma server."""
    project_dir = _find_project_root()
    daruma_bin = project_dir / ".venv" / "bin" / "daruma"
    data_dir = project_dir / "data"
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{daruma_bin}</string>
        <string>server</string>
        <string>--host</string>
        <string>{host}</string>
        <string>--port</string>
        <string>{port}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DARUMA_DATA_DIR</key>
        <string>{data_dir}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{data_dir / "server.log"}</string>
    <key>StandardErrorPath</key>
    <string>{data_dir / "server.err"}</string>
</dict>
</plist>
"""


@cli.group()
def service():
    """Manage the Daruma macOS background service."""


@service.command("install")
@click.option("--host", default=HOST, show_default=True, help="Bind address")
@click.option("--port", default=PORT, show_default=True, help="Bind port")
def service_install(host, port):
    """Install and start the Daruma launchd agent."""
    import subprocess

    plist_content = _build_plist(host, port)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    if PLIST_PATH.exists():
        subprocess.run(
            ["launchctl", "unload", str(PLIST_PATH)],
            capture_output=True,
        )

    PLIST_PATH.write_text(plist_content)
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(f"Failed to load service: {result.stderr}", err=True)
        raise SystemExit(1)

    click.echo(f"Service installed and started — http://{HOSTNAME}:{port}")
    click.echo(f"Plist: {PLIST_PATH}")


@service.command("uninstall")
def service_uninstall():
    """Stop and remove the Daruma launchd agent."""
    import subprocess

    if not PLIST_PATH.exists():
        click.echo("Service not installed.")
        return
    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )
    PLIST_PATH.unlink()

    click.echo("Service stopped and removed.")


@service.command("status")
def service_status():
    """Check whether the Daruma service is running."""
    import subprocess

    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo("Service is not running.")
        if not PLIST_PATH.exists():
            click.echo("(Not installed)")
        raise SystemExit(1)
    for line in result.stdout.strip().splitlines():
        click.echo(line)


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


def _resolve_pipeline(pipeline_service: PipelineService, identifier: str):
    """Resolve a pipeline by full ID, partial ID (prefix), or name."""
    try:
        return pipeline_service.get(identifier)
    except PipelineNotFoundError:
        pass
    try:
        return pipeline_service.get_by_name(identifier)
    except PipelineNotFoundError:
        pass
    all_pipelines = pipeline_service.list()
    matches = [p for p in all_pipelines if p.id.startswith(identifier)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        click.echo(f"Ambiguous ID prefix '{identifier}', matches:", err=True)
        for p in matches:
            click.echo(f"  {p.id}  {p.name}", err=True)
        raise SystemExit(1)
    click.echo(f"Pipeline not found: {identifier}", err=True)
    raise SystemExit(1)

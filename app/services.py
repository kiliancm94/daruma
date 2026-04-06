"""Service layer — shared business logic for FastAPI routes and CLI."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.crud import skills as skill_crud
from app.crud import task_skills as task_skill_crud
from app.crud.exceptions import NotFoundError
from app.models.task import Task
from app.models.run import Run
from app.models.skill import Skill
from app.schemas.skill import SkillSource
from app.schemas.task import OutputFormat, OutputDestination
from app.runner import run_claude, cancel_run

GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class RunNotFoundError(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class SkillNotFoundError(Exception):
    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        super().__init__(f"Skill not found: {skill_id}")


class TaskService:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Task]:
        return task_crud.get_all(self.session)

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        model: str = "sonnet",
        enabled: bool = True,
        output_format: OutputFormat | None = None,
        output_destination: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> Task:
        return task_crud.create(
            self.session,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            model=model,
            enabled=enabled,
            output_format=output_format,
            output_destination=output_destination,
            env_vars=env_vars,
        )

    def get(self, task_id: str) -> Task:
        task = task_crud.get(self.session, task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def get_by_name(self, name: str) -> Task:
        task = task_crud.get_by_name(self.session, name)
        if not task:
            raise TaskNotFoundError(name)
        return task

    def update(self, task_id: str, **fields) -> Task:
        try:
            return task_crud.update(self.session, task_id, **fields)
        except NotFoundError:
            raise TaskNotFoundError(task_id)

    def delete(self, task_id: str) -> None:
        try:
            task_crud.delete(self.session, task_id)
        except NotFoundError:
            raise TaskNotFoundError(task_id)


class RunService:
    def __init__(self, session: Session):
        self.session = session

    def list(self, task_id: str | None = None) -> list[Run]:
        return run_crud.get_all(self.session, task_id=task_id)

    def get(self, run_id: str) -> Run:
        run = run_crud.get(self.session, run_id)
        if not run:
            raise RunNotFoundError(run_id)
        return run

    def last_run(self, task_id: str) -> Run | None:
        return run_crud.get_last(self.session, task_id)


def _parse_skill_frontmatter(path: Path) -> dict:
    """Parse name and description from SKILL.md frontmatter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"name": path.parent.name, "description": "", "content": text}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"name": path.parent.name, "description": "", "content": text}
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return {
        "name": meta.get("name", path.parent.name),
        "description": meta.get("description", ""),
        "content": text,
    }


class SkillService:
    """Service layer for skill management (local DB + global filesystem)."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, name: str, description: str = "", content: str = "") -> Skill:
        return skill_crud.create(
            self.session, name=name, description=description, content=content
        )

    def get(self, skill_id: str) -> Skill:
        skill = skill_crud.get(self.session, skill_id)
        if not skill:
            raise SkillNotFoundError(skill_id)
        return skill

    def list_local(self) -> list[Skill]:
        return skill_crud.get_all(self.session)

    def list_global(self) -> list[dict]:
        """Discover skills from ~/.claude/skills/."""
        results: list[dict] = []
        if not GLOBAL_SKILLS_DIR.exists():
            return results
        for skill_dir in sorted(GLOBAL_SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            for candidate in ("SKILL.md", "skill.md"):
                skill_file = skill_dir / candidate
                if skill_file.exists():
                    results.append(
                        {
                            **_parse_skill_frontmatter(skill_file),
                            "source": SkillSource.global_,
                            "path": str(skill_file),
                        }
                    )
                    break
        return results

    def sync_global(self) -> dict:
        """Sync global skills from ~/.claude/skills/ into DB. Returns counts."""
        created, updated, unchanged = 0, 0, 0
        for global_skill in self.list_global():
            existing = skill_crud.get_by_name(self.session, global_skill["name"])
            if existing:
                if (
                    existing.content != global_skill["content"]
                    or existing.description != global_skill["description"]
                ):
                    skill_crud.update(
                        self.session,
                        existing.id,
                        content=global_skill["content"],
                        description=global_skill["description"],
                    )
                    updated += 1
                else:
                    unchanged += 1
            else:
                skill_crud.create(
                    self.session,
                    name=global_skill["name"],
                    description=global_skill.get("description", ""),
                    content=global_skill["content"],
                    source=SkillSource.global_,
                )
                created += 1
        return {"created": created, "updated": updated, "unchanged": unchanged}

    def list_all(self) -> list[dict]:
        """Unified list: all DB skills (local + synced global)."""
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "source": s.source,
                "content": s.content,
            }
            for s in self.list_local()
        ]

    def update(self, skill_id: str, **fields) -> Skill:
        try:
            return skill_crud.update(self.session, skill_id, **fields)
        except NotFoundError:
            raise SkillNotFoundError(skill_id)

    def delete(self, skill_id: str) -> None:
        try:
            skill_crud.delete(self.session, skill_id)
        except NotFoundError:
            raise SkillNotFoundError(skill_id)


# ── Output writing ─────────────────────────────────────────────────────────────

_EXT = {OutputFormat.text: "txt", OutputFormat.json: "json", OutputFormat.md: "md"}


def _format_output(stdout: str, fmt: OutputFormat, task_name: str, run_id: str) -> str:
    """Format run stdout according to the task's output_format."""
    if fmt == OutputFormat.json:
        return json.dumps(
            {
                "task": task_name,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "output": stdout,
            },
            indent=2,
        )
    if fmt == OutputFormat.md:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"# {task_name}\n\n_Run {run_id[:8]} — {ts}_\n\n{stdout}\n"
    return stdout  # OutputFormat.text or None → raw


def _write_output(stdout: str, task: Task, run_id: str) -> None:
    """Write run output to a file if output_destination is configured.

    Destination can be:
    - A file path: written directly (overwritten each run)
    - A directory path (ends with / or has no extension): timestamped file created inside
    - "pipeline": no file written; output is stored in Run.stdout for future task chaining
    """
    dest = task.output_destination
    if not dest or dest == OutputDestination.pipeline:
        return

    fmt = task.output_format or OutputFormat.text
    content = _format_output(stdout, fmt, task.name, run_id)
    ext = _EXT.get(fmt, "txt")

    path = Path(dest)
    # Treat as directory if it ends with / or has no suffix
    if dest.endswith("/") or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = path / f"{task.name}_{ts}.{ext}"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(content, encoding="utf-8")


# ── Task execution ─────────────────────────────────────────────────────────────


def execute_task(
    task: Task,
    session: Session,
    trigger: str = "manual",
    runner: Callable | None = None,
    on_output: Callable[[str, str], None] | None = None,
) -> Run:
    """Execute a task synchronously. Returns the completed Run."""
    if runner is None:
        runner = run_claude
    run = run_crud.create(session, task_id=task.id, trigger=trigger)
    run_id = run.id

    if on_output:

        def _combined(stdout: str, activity: str) -> None:
            run_crud.update_output(session, run_id, stdout, activity)
            on_output(stdout, activity)

    else:

        def _combined(stdout: str, activity: str) -> None:
            run_crud.update_output(session, run_id, stdout, activity)

    try:
        skills = task_skill_crud.list_for_task(session, task.id)
        system_prompt = "\n\n".join(s.content for s in skills) if skills else None
        env_vars = json.loads(task.env_vars) if task.env_vars else None

        result = runner(
            task.prompt,
            allowed_tools=task.allowed_tools,
            model=task.model,
            system_prompt=system_prompt,
            run_id=run_id,
            on_output=_combined,
            env_vars=env_vars,
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        completed = run_crud.complete(
            session,
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
        if status == "success":
            _write_output(result["stdout"], task, run_id)
        return completed
    except Exception as e:
        return run_crud.complete(
            session, run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )


def execute_task_background(
    task: Task,
    session_factory: sessionmaker,
    trigger: str = "manual",
    runner: Callable | None = None,
) -> Run:
    """Execute a task in a background thread. Returns the initial Run (status=running)."""
    if runner is None:
        runner = run_claude
    session = session_factory()
    try:
        run = run_crud.create(session, task_id=task.id, trigger=trigger)
        session.expunge(run)
    finally:
        session.close()

    threading.Thread(
        target=_background_worker,
        args=(
            task,
            run.id,
            runner,
            session_factory,
        ),
        daemon=True,
    ).start()
    return run


def _background_worker(
    task: Task,
    run_id: str,
    runner: Callable,
    session_factory: sessionmaker,
) -> None:
    session = session_factory()
    try:
        skills = task_skill_crud.list_for_task(session, task.id)
        system_prompt = "\n\n".join(s.content for s in skills) if skills else None
        env_vars = json.loads(task.env_vars) if task.env_vars else None

        result = runner(
            task.prompt,
            allowed_tools=task.allowed_tools,
            model=task.model,
            system_prompt=system_prompt,
            run_id=run_id,
            on_output=lambda stdout, activity: run_crud.update_output(
                session, run_id, stdout, activity
            ),
            env_vars=env_vars,
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        run_crud.complete(
            session,
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            activity=result.get("activity", ""),
        )
        if status == "success":
            _write_output(result["stdout"], task, run_id)
    except Exception as e:
        run_crud.complete(
            session, run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
        )
    finally:
        session.close()


def cancel_task_run(run_id: str, session: Session) -> None:
    """Cancel a running task. Raises RunNotFoundError or ValueError."""
    run = run_crud.get(session, run_id)
    if not run:
        raise RunNotFoundError(run_id)
    if run.status != "running":
        raise ValueError("Run is not active")
    killed = cancel_run(run_id)
    if not killed:
        run_crud.complete(
            session,
            run_id,
            status="failed",
            stdout="",
            stderr="Cancelled",
            exit_code=-1,
        )

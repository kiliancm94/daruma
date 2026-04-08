"""Service layer — shared business logic for FastAPI routes and CLI."""

import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.crud import skills as skill_crud
from app.crud import task_skills as task_skill_crud
from app.crud import pipelines as pipeline_crud
from app.crud import pipeline_runs as pipeline_run_crud
from app.crud.exceptions import NotFoundError
from app.models.task import Task
from app.models.run import Run
from app.models.skill import Skill
from app.models.pipeline import Pipeline
from app.models.pipeline_run import PipelineRun
from app.schemas.pipeline import PipelineRunStatus, PipelineTrigger
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
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Skill not found: {name}")


class PipelineNotFoundError(Exception):
    def __init__(self, pipeline_id: str):
        self.pipeline_id = pipeline_id
        super().__init__(f"Pipeline not found: {pipeline_id}")


class PipelineRunNotFoundError(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Pipeline run not found: {run_id}")


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


def _local_to_dict(skill: Skill) -> dict:
    """Convert an ORM Skill to a dict with ``"source": "local"`` and ``"id"`` key."""
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "source": "local",
    }


def _write_skill_file(name: str, description: str, content: str) -> None:
    """Write ``GLOBAL_SKILLS_DIR / name / SKILL.md`` with YAML frontmatter."""
    skill_dir = GLOBAL_SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = f"---\nname: {name}\ndescription: {description}\n---\n{content}"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def _delete_skill_dir(name: str) -> None:
    """Remove ``GLOBAL_SKILLS_DIR / name /`` directory."""
    skill_dir = GLOBAL_SKILLS_DIR / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)


class SkillService:
    """Service layer for skill management — routes between filesystem (global) and DB (local)."""

    def __init__(self, session: Session):
        self.session = session

    # ── Private helpers ────────────────────────────────────────────────────

    def _list_global_raw(self) -> list[dict]:
        """Scan the filesystem for global skills."""
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
                            "source": "global",
                            "path": str(skill_file),
                        }
                    )
                    break
        return results

    def _check_name_available(self, name: str) -> None:
        """Raise ``ValueError`` if *name* is already taken in either backend."""
        # Check global
        for g in self._list_global_raw():
            if g["name"] == name:
                raise ValueError(f"Skill name already taken: {name}")
        # Check local
        if skill_crud.get_by_name(self.session, name) is not None:
            raise ValueError(f"Skill name already taken: {name}")

    def _update_global(self, existing: dict, **fields) -> dict:
        """Update a global skill on disk. Handles rename (delete old + write new)."""
        new_name = fields.get("name", existing["name"])
        new_desc = fields.get("description", existing["description"])
        new_content = fields.get("content", existing["content"])

        if new_name != existing["name"]:
            _delete_skill_dir(existing["name"])
        _write_skill_file(new_name, new_desc, new_content)

        return {
            "name": new_name,
            "description": new_desc,
            "content": f"---\nname: {new_name}\ndescription: {new_desc}\n---\n{new_content}",
            "source": "global",
            "path": str(GLOBAL_SKILLS_DIR / new_name / "SKILL.md"),
        }

    def _update_local(self, existing: dict, **fields) -> dict:
        """Update a local (DB) skill."""
        try:
            updated = skill_crud.update(self.session, existing["id"], **fields)
        except NotFoundError:
            raise SkillNotFoundError(existing["name"])
        return _local_to_dict(updated)

    # ── Public API ─────────────────────────────────────────────────────────

    def resolve(self, name: str) -> dict:
        """Look up a skill by name — filesystem first, then DB.

        Raises ``SkillNotFoundError`` if not found in either backend.
        """
        for g in self._list_global_raw():
            if g["name"] == name:
                return g
        local = skill_crud.get_by_name(self.session, name)
        if local:
            return _local_to_dict(local)
        raise SkillNotFoundError(name)

    def get(self, name: str) -> dict:
        """Alias for :meth:`resolve`."""
        return self.resolve(name)

    def create(
        self,
        name: str,
        description: str = "",
        content: str = "",
        source: str = "local",
    ) -> dict:
        """Create a skill in the appropriate backend. Returns a dict."""
        self._check_name_available(name)
        if source == "global":
            _write_skill_file(name, description, content)
            return {
                "name": name,
                "description": description,
                "content": f"---\nname: {name}\ndescription: {description}\n---\n{content}",
                "source": "global",
                "path": str(GLOBAL_SKILLS_DIR / name / "SKILL.md"),
            }
        skill = skill_crud.create(
            self.session, name=name, description=description, content=content
        )
        return _local_to_dict(skill)

    def update(self, current_name: str, **fields) -> dict:
        """Update a skill by name — resolves to the correct backend first."""
        existing = self.resolve(current_name)
        if existing["source"] == "global":
            return self._update_global(existing, **fields)
        return self._update_local(existing, **fields)

    def delete(self, name: str) -> None:
        """Delete a skill by name — resolves to the correct backend first."""
        existing = self.resolve(name)
        if existing["source"] == "global":
            _delete_skill_dir(existing["name"])
            return
        try:
            skill_crud.delete(self.session, existing["id"])
        except NotFoundError:
            raise SkillNotFoundError(name)

    def list_local(self) -> list[dict]:
        """Return all DB-backed (local) skills as dicts."""
        return [_local_to_dict(s) for s in skill_crud.get_all(self.session)]

    def list_global(self) -> list[dict]:
        """Return all filesystem-backed (global) skills as dicts."""
        return self._list_global_raw()

    def list_all(self) -> list[dict]:
        """Merge local + global skills, sorted by name."""
        merged = self.list_local() + self.list_global()
        return sorted(merged, key=lambda s: s["name"])


class PipelineService:
    """Service layer for pipeline management."""

    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[Pipeline]:
        return pipeline_crud.get_all(self.session)

    def create(
        self,
        name: str,
        description: str | None = None,
        task_ids: list[str] | None = None,
        enabled: bool = True,
    ) -> Pipeline:
        return pipeline_crud.create(
            self.session,
            name=name,
            description=description,
            task_ids=task_ids,
            enabled=enabled,
        )

    def get(self, pipeline_id: str) -> Pipeline:
        pipeline = pipeline_crud.get(self.session, pipeline_id)
        if not pipeline:
            raise PipelineNotFoundError(pipeline_id)
        return pipeline

    def get_by_name(self, name: str) -> Pipeline:
        pipeline = pipeline_crud.get_by_name(self.session, name)
        if not pipeline:
            raise PipelineNotFoundError(name)
        return pipeline

    def update(self, pipeline_id: str, **fields) -> Pipeline:
        try:
            return pipeline_crud.update(self.session, pipeline_id, **fields)
        except NotFoundError:
            raise PipelineNotFoundError(pipeline_id)

    def update_steps(self, pipeline_id: str, task_ids: list[str]) -> None:
        try:
            pipeline_crud.update_steps(self.session, pipeline_id, task_ids)
        except NotFoundError:
            raise PipelineNotFoundError(pipeline_id)

    def delete(self, pipeline_id: str) -> None:
        try:
            pipeline_crud.delete(self.session, pipeline_id)
        except NotFoundError:
            raise PipelineNotFoundError(pipeline_id)


class PipelineRunService:
    """Service layer for pipeline run queries."""

    def __init__(self, session: Session):
        self.session = session

    def list(self, pipeline_id: str | None = None) -> list[PipelineRun]:
        return pipeline_run_crud.get_all(self.session, pipeline_id=pipeline_id)

    def get(self, run_id: str) -> PipelineRun:
        run = pipeline_run_crud.get(self.session, run_id)
        if not run:
            raise PipelineRunNotFoundError(run_id)
        return run

    def last_run(self, pipeline_id: str) -> PipelineRun | None:
        return pipeline_run_crud.get_last(self.session, pipeline_id)


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
        skill_names = task_skill_crud.list_for_task(session, task.id)
        if skill_names:
            skill_svc = SkillService(session)
            system_prompt = "\n\n".join(
                skill_svc.resolve(n)["content"] for n in skill_names
            )
        else:
            system_prompt = None
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
        skill_names = task_skill_crud.list_for_task(session, task.id)
        if skill_names:
            skill_svc = SkillService(session)
            system_prompt = "\n\n".join(
                skill_svc.resolve(n)["content"] for n in skill_names
            )
        else:
            system_prompt = None
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


# ── Pipeline execution ────────────────────────────────────────────────────────


def execute_pipeline(
    pipeline: Pipeline,
    session: Session,
    trigger: PipelineTrigger = PipelineTrigger.manual,
    runner: Callable | None = None,
) -> PipelineRun:
    """Execute all steps of a pipeline sequentially. Returns the completed PipelineRun."""
    if runner is None:
        runner = run_claude

    pipeline_run = pipeline_run_crud.create(
        session, pipeline_id=pipeline.id, trigger=trigger
    )

    steps = sorted(pipeline.steps, key=lambda s: s.step_order)
    previous_stdout: str | None = None

    for step in steps:
        task = step.task

        # Build prompt — step 0 uses task prompt as-is; later steps prepend previous output
        if previous_stdout is not None:
            prompt = f"Output from previous step:\n\n{previous_stdout}\n\n---\n\n{task.prompt}"
        else:
            prompt = task.prompt

        # Create a Run record linked to the pipeline run
        run = run_crud.create(
            session,
            task_id=task.id,
            trigger=trigger,
            pipeline_run_id=pipeline_run.id,
        )
        run_id = run.id

        try:
            skill_names = task_skill_crud.list_for_task(session, task.id)
            if skill_names:
                skill_svc = SkillService(session)
                system_prompt = "\n\n".join(
                    skill_svc.resolve(n)["content"] for n in skill_names
                )
            else:
                system_prompt = None
            env_vars = json.loads(task.env_vars) if task.env_vars else None

            result = runner(
                prompt,
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
        except Exception as e:
            run_crud.complete(
                session,
                run_id,
                status="failed",
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )
            status = "failed"

        # Update current step on pipeline run
        pipeline_run_crud.update_step(session, pipeline_run.id, step.step_order)

        if status == "failed":
            return pipeline_run_crud.complete(
                session, pipeline_run.id, status=PipelineRunStatus.failed
            )

        # Store stdout for the next step
        previous_stdout = result["stdout"]

    return pipeline_run_crud.complete(
        session, pipeline_run.id, status=PipelineRunStatus.success
    )


def execute_pipeline_background(
    pipeline: Pipeline,
    session_factory: sessionmaker,
    trigger: PipelineTrigger = PipelineTrigger.manual,
    runner: Callable | None = None,
) -> PipelineRun:
    """Execute a pipeline in a background thread. Returns the initial PipelineRun (status=running)."""
    if runner is None:
        runner = run_claude
    session = session_factory()
    try:
        pipeline_run = pipeline_run_crud.create(
            session, pipeline_id=pipeline.id, trigger=trigger
        )
        session.expunge(pipeline_run)
    finally:
        session.close()

    threading.Thread(
        target=_pipeline_background_worker,
        args=(pipeline, pipeline_run.id, runner, session_factory),
        daemon=True,
    ).start()
    return pipeline_run


def _pipeline_background_worker(
    pipeline: Pipeline,
    pipeline_run_id: str,
    runner: Callable,
    session_factory: sessionmaker,
) -> None:
    """Background worker that executes all pipeline steps sequentially."""
    session = session_factory()
    try:
        # Re-load pipeline within this session
        fresh_pipeline = pipeline_crud.get(session, pipeline.id)
        if not fresh_pipeline:
            pipeline_run_crud.complete(
                session, pipeline_run_id, status=PipelineRunStatus.failed
            )
            return

        steps = sorted(fresh_pipeline.steps, key=lambda s: s.step_order)
        previous_stdout: str | None = None

        for step in steps:
            task = step.task
            if previous_stdout is not None:
                prompt = f"Output from previous step:\n\n{previous_stdout}\n\n---\n\n{task.prompt}"
            else:
                prompt = task.prompt

            run = run_crud.create(
                session,
                task_id=task.id,
                trigger="pipeline",
                pipeline_run_id=pipeline_run_id,
            )
            run_id = run.id

            try:
                skill_names = task_skill_crud.list_for_task(session, task.id)
                if skill_names:
                    skill_svc = SkillService(session)
                    system_prompt = "\n\n".join(
                        skill_svc.resolve(n)["content"] for n in skill_names
                    )
                else:
                    system_prompt = None
                env_vars = json.loads(task.env_vars) if task.env_vars else None

                result = runner(
                    prompt,
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
            except Exception as e:
                run_crud.complete(
                    session,
                    run_id,
                    status="failed",
                    stdout="",
                    stderr=str(e),
                    exit_code=-1,
                )
                status = "failed"

            pipeline_run_crud.update_step(session, pipeline_run_id, step.step_order)

            if status == "failed":
                pipeline_run_crud.complete(
                    session, pipeline_run_id, status=PipelineRunStatus.failed
                )
                return

            previous_stdout = result["stdout"]

        pipeline_run_crud.complete(
            session, pipeline_run_id, status=PipelineRunStatus.success
        )
    except Exception:
        try:
            pipeline_run_crud.complete(
                session, pipeline_run_id, status=PipelineRunStatus.failed
            )
        except Exception:
            pass
    finally:
        session.close()

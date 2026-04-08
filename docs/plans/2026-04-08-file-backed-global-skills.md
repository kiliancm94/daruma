# File-Backed Global Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace DB-synced global skills with direct filesystem read/write, keeping local skills in SQLite, and switch all skill references from UUID to name.

**Architecture:** Two backends behind a unified `SkillService` — global skills read/write `~/.claude/skills/<name>/SKILL.md` directly, local skills stay in SQLite. The `task_skills` junction table switches from `skill_id` (UUID FK) to `skill_name` (String). All API/CLI/UI endpoints use skill name as identifier.

**Tech Stack:** Python 3.14+, FastAPI, SQLAlchemy 2.x, Alembic, Click CLI, Jinja2+HTMX

---

### Task 1: Alembic Migration — Junction Table + Drop Source

**Files:**
- Create: `alembic/versions/e1f2a3b4c5d6_file_backed_global_skills.py`
- Reference: `app/models/task_skill.py`, `app/models/skill.py`

**Step 1: Create Alembic migration**

```python
"""File-backed global skills: task_skills uses skill_name, drop global rows and source column."""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add skill_name column to task_skills
    op.add_column("task_skills", sa.Column("skill_name", sa.String(), nullable=True))

    # 2. Backfill skill_name from skills.name via skill_id join
    op.execute(
        "UPDATE task_skills SET skill_name = "
        "(SELECT skills.name FROM skills WHERE skills.id = task_skills.skill_id)"
    )

    # 3. Recreate task_skills with new schema (SQLite lacks ALTER TABLE DROP COLUMN)
    op.execute(
        "CREATE TABLE task_skills_new ("
        "  task_id VARCHAR NOT NULL, "
        "  skill_name VARCHAR NOT NULL, "
        "  PRIMARY KEY (task_id, skill_name), "
        "  FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE"
        ")"
    )
    op.execute(
        "INSERT INTO task_skills_new (task_id, skill_name) "
        "SELECT task_id, skill_name FROM task_skills WHERE skill_name IS NOT NULL"
    )
    op.drop_table("task_skills")
    op.rename_table("task_skills_new", "task_skills")

    # 4. Delete global skill rows from skills table
    op.execute("DELETE FROM skills WHERE source = 'global'")

    # 5. Recreate skills without source column (SQLite)
    op.execute(
        "CREATE TABLE skills_new ("
        "  id VARCHAR PRIMARY KEY, "
        "  name VARCHAR UNIQUE NOT NULL, "
        "  description VARCHAR NOT NULL, "
        "  content TEXT NOT NULL, "
        "  created_at VARCHAR NOT NULL, "
        "  updated_at VARCHAR NOT NULL"
        ")"
    )
    op.execute(
        "INSERT INTO skills_new (id, name, description, content, created_at, updated_at) "
        "SELECT id, name, description, content, created_at, updated_at FROM skills"
    )
    op.drop_table("skills")
    op.rename_table("skills_new", "skills")


def downgrade() -> None:
    # Add source column back
    op.add_column(
        "skills",
        sa.Column("source", sa.String(), nullable=False, server_default="local"),
    )

    # Recreate task_skills with skill_id
    op.execute(
        "CREATE TABLE task_skills_new ("
        "  task_id VARCHAR NOT NULL, "
        "  skill_id VARCHAR NOT NULL, "
        "  PRIMARY KEY (task_id, skill_id), "
        "  FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE, "
        "  FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE"
        ")"
    )
    op.execute(
        "INSERT INTO task_skills_new (task_id, skill_id) "
        "SELECT ts.task_id, s.id FROM task_skills ts "
        "JOIN skills s ON s.name = ts.skill_name"
    )
    op.drop_table("task_skills")
    op.rename_table("task_skills_new", "task_skills")
```

**Step 2: Commit**

```bash
git add alembic/versions/e1f2a3b4c5d6_file_backed_global_skills.py
git commit -m "migration: task_skills to skill_name, drop source column"
```

---

### Task 2: Update Models — Skill Drops Source, TaskSkill Uses skill_name

**Files:**
- Modify: `app/models/skill.py`
- Modify: `app/models/task_skill.py`

**Step 1: Update Skill model — remove source column**

In `app/models/skill.py`, remove the `source` mapped_column. Final model:

```python
"""SQLAlchemy ORM model for skills."""

import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.date_helpers import utcnow


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
```

**Step 2: Update TaskSkill model — skill_id → skill_name, drop FK to skills**

In `app/models/task_skill.py`, replace `skill_id` with `skill_name`:

```python
"""SQLAlchemy association table for task-skill many-to-many."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskSkill(Base):
    __tablename__ = "task_skills"

    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    skill_name: Mapped[str] = mapped_column(String, primary_key=True)
```

**Step 3: Commit**

```bash
git add app/models/skill.py app/models/task_skill.py
git commit -m "models: drop source from Skill, use skill_name in TaskSkill"
```

---

### Task 3: Update Schemas

**Files:**
- Modify: `app/schemas/skill.py`

**Step 1: Update schemas**

- `SkillCreate` gets optional `source` field
- `SkillResponse` drops `id`, uses `name` as identifier, `source` is a plain string
- Keep `SkillSource` enum

```python
"""Pydantic schemas for skills."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SkillSource(StrEnum):
    local = "local"
    global_ = "global"


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    content: str
    source: SkillSource = SkillSource.local


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    content: str
    source: str = "local"
```

**Step 2: Commit**

```bash
git add app/schemas/skill.py
git commit -m "schemas: add source to SkillCreate, drop id from SkillResponse"
```

---

### Task 4: Update CRUD — Skills + Task-Skills

**Files:**
- Modify: `app/crud/skills.py`
- Modify: `app/crud/task_skills.py`

**Step 1: Update skills CRUD — drop source parameter**

```python
"""CRUD operations for skills."""

from sqlalchemy.orm import Session

from app.crud.exceptions import NotFoundError
from app.models.skill import Skill
from app.schemas.skill import SkillUpdate
from app.utils.date_helpers import utcnow


def create(
    session: Session,
    name: str,
    description: str = "",
    content: str = "",
) -> Skill:
    skill = Skill(name=name, description=description, content=content)
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


def get(session: Session, skill_id: str) -> Skill | None:
    return session.get(Skill, skill_id)


def get_by_name(session: Session, name: str) -> Skill | None:
    return session.query(Skill).filter(Skill.name == name).first()


def get_all(session: Session) -> list[Skill]:
    return session.query(Skill).order_by(Skill.name).all()


def update(session: Session, skill_id: str, **fields) -> Skill:
    """Update a skill. Raises NotFoundError if the skill does not exist."""
    if (skill := get(session, skill_id)) is None:
        raise NotFoundError(f"Skill not found: {skill_id}")
    validated = SkillUpdate(**fields).model_dump(exclude_unset=True)
    if not validated:
        return skill
    for key, value in validated.items():
        setattr(skill, key, value)
    skill.updated_at = utcnow()
    session.commit()
    session.refresh(skill)
    return skill


def delete(session: Session, skill_id: str) -> None:
    """Delete a skill. Raises NotFoundError if the skill does not exist."""
    if (skill := get(session, skill_id)) is None:
        raise NotFoundError(f"Skill not found: {skill_id}")
    session.delete(skill)
    session.commit()
```

**Step 2: Update task_skills CRUD — skill_id → skill_name**

```python
"""CRUD for task-skill assignments."""

from sqlalchemy.orm import Session

from app.models.task_skill import TaskSkill


def assign(session: Session, task_id: str, skill_name: str) -> None:
    if not session.get(TaskSkill, (task_id, skill_name)):
        session.add(TaskSkill(task_id=task_id, skill_name=skill_name))
        session.commit()


def unassign(session: Session, task_id: str, skill_name: str) -> None:
    link = session.get(TaskSkill, (task_id, skill_name))
    if link:
        session.delete(link)
        session.commit()


def list_for_task(session: Session, task_id: str) -> list[str]:
    """Return skill names assigned to a task."""
    rows = (
        session.query(TaskSkill.skill_name)
        .filter(TaskSkill.task_id == task_id)
        .order_by(TaskSkill.skill_name)
        .all()
    )
    return [r.skill_name for r in rows]


def replace(session: Session, task_id: str, skill_names: list[str]) -> None:
    session.query(TaskSkill).filter(TaskSkill.task_id == task_id).delete()
    for name in skill_names:
        session.add(TaskSkill(task_id=task_id, skill_name=name))
    session.commit()
```

**Step 3: Write CRUD tests**

Update `tests/test_crud_skills.py`:
- `TestSkillCrud`: remove assertions on `source` field
- `TestTaskSkillCrud`: use `skill_name` (string) instead of `skill_id`

**Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_crud_skills.py -v
```

**Step 5: Commit**

```bash
git add app/crud/skills.py app/crud/task_skills.py tests/test_crud_skills.py
git commit -m "crud: drop source param, task_skills uses skill_name"
```

---

### Task 5: Update Service Layer — File-Backed Global CRUD

**Files:**
- Modify: `app/services.py`

**Step 1: Rewrite SkillService**

Key changes:
- Add `resolve(name)` — check filesystem first, then DB; returns a dict
- Add `_write_skill_file(name, description, content)` — writes `SKILL.md`
- `create()` routes to filesystem or DB based on `source` param
- `update(name, ...)` and `delete(name)` resolve backend first
- `list_all()` merges filesystem + DB
- Remove `sync_global()`
- Name collision check on create

The service returns dicts (not ORM objects) for global skills since they have no DB row. For local skills, convert ORM to dict at the service boundary for consistency.

```python
class SkillService:
    """Service layer for skill management (local DB + global filesystem)."""

    def __init__(self, session: Session):
        self.session = session

    def resolve(self, name: str) -> dict:
        """Find a skill by name. Checks filesystem first, then DB."""
        for gs in self._list_global_raw():
            if gs["name"] == name:
                return gs
        if (skill := skill_crud.get_by_name(self.session, name)) is not None:
            return _local_to_dict(skill)
        raise SkillNotFoundError(name)

    def create(
        self,
        name: str,
        description: str = "",
        content: str = "",
        source: str = "local",
    ) -> dict:
        # Check name collision across both backends
        self._check_name_available(name)
        if source == "global":
            _write_skill_file(name, description, content)
            return self.resolve(name)
        skill = skill_crud.create(
            self.session, name=name, description=description, content=content
        )
        return _local_to_dict(skill)

    def update(self, name: str, **fields) -> dict:
        existing = self.resolve(name)
        if existing["source"] == "global":
            return self._update_global(existing, **fields)
        return self._update_local(existing, **fields)

    def delete(self, name: str) -> None:
        existing = self.resolve(name)
        if existing["source"] == "global":
            _delete_skill_dir(existing["name"])
        else:
            skill_crud.delete(self.session, existing["id"])

    def get(self, name: str) -> dict:
        return self.resolve(name)

    def list_local(self) -> list[dict]:
        return [_local_to_dict(s) for s in skill_crud.get_all(self.session)]

    def list_global(self) -> list[dict]:
        return self._list_global_raw()

    def list_all(self) -> list[dict]:
        all_skills = self._list_global_raw() + self.list_local()
        return sorted(all_skills, key=lambda s: s["name"])

    def _list_global_raw(self) -> list[dict]:
        results: list[dict] = []
        if not GLOBAL_SKILLS_DIR.exists():
            return results
        for skill_dir in sorted(GLOBAL_SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            for candidate in ("SKILL.md", "skill.md"):
                skill_file = skill_dir / candidate
                if skill_file.exists():
                    parsed = _parse_skill_frontmatter(skill_file)
                    parsed["source"] = "global"
                    parsed["path"] = str(skill_file)
                    results.append(parsed)
                    break
        return results

    def _check_name_available(self, name: str) -> None:
        for gs in self._list_global_raw():
            if gs["name"] == name:
                raise ValueError(f"Skill name already taken (global): {name}")
        if skill_crud.get_by_name(self.session, name) is not None:
            raise ValueError(f"Skill name already taken (local): {name}")

    def _update_global(self, existing: dict, **fields) -> dict:
        validated = SkillUpdate(**fields).model_dump(exclude_unset=True)
        if not validated:
            return existing
        new_name = validated.get("name", existing["name"])
        new_desc = validated.get("description", existing["description"])
        new_content = validated.get("content", existing["content"])
        if new_name != existing["name"]:
            # Check new name not taken
            try:
                self.resolve(new_name)
                raise ValueError(f"Skill name already taken: {new_name}")
            except SkillNotFoundError:
                pass
            _delete_skill_dir(existing["name"])
        _write_skill_file(new_name, new_desc, new_content)
        return self.resolve(new_name)

    def _update_local(self, existing: dict, **fields) -> dict:
        try:
            skill = skill_crud.update(self.session, existing["id"], **fields)
        except NotFoundError:
            raise SkillNotFoundError(existing["name"])
        return _local_to_dict(skill)
```

Helper functions (module-level):

```python
def _local_to_dict(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "source": "local",
    }


def _write_skill_file(name: str, description: str, content: str) -> None:
    skill_dir = GLOBAL_SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    # Build markdown with frontmatter
    frontmatter = f"---\nname: {name}\ndescription: {description}\n---\n"
    (skill_dir / "SKILL.md").write_text(frontmatter + content, encoding="utf-8")


def _delete_skill_dir(name: str) -> None:
    import shutil
    skill_dir = GLOBAL_SKILLS_DIR / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
```

**Step 2: Update execute_task and related functions**

Everywhere that currently does:
```python
skills = task_skill_crud.list_for_task(session, task.id)
system_prompt = "\n\n".join(s.content for s in skills) if skills else None
```

Change to:
```python
skill_names = task_skill_crud.list_for_task(session, task.id)
if skill_names:
    skill_svc = SkillService(session)
    skill_contents = [skill_svc.resolve(n)["content"] for n in skill_names]
    system_prompt = "\n\n".join(skill_contents)
else:
    system_prompt = None
```

Apply this in: `execute_task()`, `_background_worker()`, `execute_pipeline()`, `_pipeline_background_worker()`.

**Step 3: Remove sync_global, _sync_global_skills**

- Delete `sync_global()` method from `SkillService`
- In `app/main.py`: remove `_sync_global_skills()` function and its call in `lifespan()`
- Remove the `SkillService` import in `main.py` if no longer needed

**Step 4: Write service tests**

Update `tests/test_services.py` `TestSkillService`:
- Replace `sync_global` tests with file-backed CRUD tests
- Test `resolve()` checks filesystem then DB
- Test `create()` with `source="global"` writes to filesystem
- Test `create()` name collision across backends
- Test `update()` on global skill rewrites file
- Test `delete()` on global skill removes directory
- Test `list_all()` merges both backends
- Test `_write_skill_file()` creates correct frontmatter
- Update `test_skills_injected` to use new skill resolution

**Step 5: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_services.py -v
```

**Step 6: Commit**

```bash
git add app/services.py app/main.py tests/test_services.py
git commit -m "services: file-backed global skills, remove sync"
```

---

### Task 6: Update API Router — Name-Based Endpoints

**Files:**
- Modify: `app/routers/skills.py`

**Step 1: Rewrite router to use name-based endpoints**

```python
"""API router for skills management."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.crud import task_skills as task_skill_crud
from app.schemas.skill import SkillCreate, SkillUpdate, SkillResponse
from app.services import SkillService, SkillNotFoundError

router = APIRouter(prefix="/api", tags=["skills"])


def get_skill_service(session: Session = Depends(get_db)) -> SkillService:
    return SkillService(session)


@router.get("/skills", response_model=list[SkillResponse])
def list_skills(skill_service: SkillService = Depends(get_skill_service)):
    return skill_service.list_all()


@router.post("/skills", response_model=SkillResponse, status_code=201)
def create_skill(
    body: SkillCreate, skill_service: SkillService = Depends(get_skill_service)
):
    try:
        return skill_service.create(
            name=body.name,
            description=body.description,
            content=body.content,
            source=body.source,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/skills/{name}", response_model=SkillResponse)
def get_skill(name: str, skill_service: SkillService = Depends(get_skill_service)):
    try:
        return skill_service.get(name)
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")


@router.put("/skills/{name}", response_model=SkillResponse)
def update_skill(
    name: str,
    body: SkillUpdate,
    skill_service: SkillService = Depends(get_skill_service),
):
    try:
        return skill_service.update(name, **body.model_dump(exclude_unset=True))
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/skills/{name}", status_code=204)
def delete_skill(
    name: str, skill_service: SkillService = Depends(get_skill_service)
):
    try:
        skill_service.delete(name)
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    return Response(status_code=204)


# ── Task-Skill assignment ────────────────────────────


class TaskSkillsBody(BaseModel):
    skill_names: list[str]


@router.get("/tasks/{task_id}/skills", response_model=list[SkillResponse])
def list_task_skills(
    task_id: str,
    session: Session = Depends(get_db),
):
    skill_svc = SkillService(session)
    names = task_skill_crud.list_for_task(session, task_id)
    results = []
    for n in names:
        try:
            results.append(skill_svc.resolve(n))
        except SkillNotFoundError:
            pass  # skill was deleted, skip
    return results


@router.put("/tasks/{task_id}/skills")
def replace_task_skills(
    task_id: str, body: TaskSkillsBody, session: Session = Depends(get_db)
):
    task_skill_crud.replace(session, task_id, body.skill_names)
    return {"status": "ok"}
```

**Step 2: Update API tests**

Update `tests/test_api_skills.py` — all endpoints use name, `skill_names` body for assignment.

**Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_api_skills.py -v
```

**Step 4: Commit**

```bash
git add app/routers/skills.py tests/test_api_skills.py
git commit -m "api: name-based skill endpoints, skill_names for assignment"
```

---

### Task 7: Update CLI — --global Flag, Remove Sync

**Files:**
- Modify: `app/cli.py`

**Step 1: Update CLI skill commands**

- `skills list`: service returns dicts, no need for `.name`/`.source` attribute access
- `skills create`: add `--global` flag → passes `source="global"` to service
- `skills show <name>`: use `skill_service.get(name)` (returns dict)
- `skills delete <name>`: use `skill_service.delete(name)`
- `skills import`: pass `source` param
- Remove `skills sync` command
- `tasks edit --skills`: use `task_skill_crud.replace(session, task_pk, names)` directly (already name-based)

**Step 2: Update CLI tests**

Update `tests/test_cli.py` `TestSkillCommands`:
- `test_create_and_list`: stays mostly the same
- `test_show`: use dict access pattern
- `test_delete`: same
- `test_import_from_file`: same
- `test_assign_to_task`: stays (already name-based in CLI)
- Add: `test_create_global` (with patched `GLOBAL_SKILLS_DIR`)
- Remove any sync-related tests

**Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_cli.py -v
```

**Step 4: Commit**

```bash
git add app/cli.py tests/test_cli.py
git commit -m "cli: --global flag for skill create, remove sync command"
```

---

### Task 8: Update UI Router + Templates

**Files:**
- Modify: `app/routers/ui.py`
- Modify: `templates/skills_list.html`
- Modify: `templates/skill_detail.html`
- Modify: `templates/skill_form.html`
- Modify: `templates/task_form.html`

**Step 1: Update UI router — name-based skill URLs**

- `skills_list`: already uses `list_all()` which returns dicts — works
- `skill_form_new`: add source field context
- `skill_create_form`: accept `source` form field, pass to service
- `skill_detail`: change from `skill_id` to `name` in URL, use `service.get(name)`
- `skill_edit_form`: same
- `skill_update_form`: same
- Task forms: use `skill_names` instead of `skill_ids`

**Step 2: Update templates**

`skills_list.html` — change links from `/ui/skills/{{ skill.id }}` to `/ui/skills/{{ skill.name }}`

`skill_detail.html` — change URLs from `skill.id` to `skill.name`, hx-delete uses name

`skill_form.html` — add source toggle (radio: local/global), action URL uses name

`task_form.html` — change checkbox `name="skill_ids"` to `name="skill_names"`, value is always `skill.name`

**Step 3: Run full test suite**

```bash
source .venv/bin/activate && pytest -v
```

**Step 4: Commit**

```bash
git add app/routers/ui.py templates/
git commit -m "ui: name-based skill URLs, source toggle in form"
```

---

### Task 9: Final Cleanup + Full Test Run

**Files:**
- Modify: `app/main.py` (if not already cleaned in Task 5)
- Review all files for dead imports

**Step 1: Verify main.py is clean**

Ensure `_sync_global_skills` is removed and `SkillService` import is removed from main.py if unused.

**Step 2: Run lint + format**

```bash
uvx ruff check --fix . && uvx ruff format .
```

**Step 3: Run full test suite**

```bash
source .venv/bin/activate && pytest -v
```

**Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "cleanup: remove dead imports, lint"
```

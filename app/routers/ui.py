"""UI router serving Jinja2 templates with HTMX interactions."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.crud import task_skills as task_skill_crud
from app.schemas.task import TaskResponse
from app.schemas.run import RunResponse
from app.services import (
    TaskService,
    RunService,
    SkillService,
    TaskNotFoundError,
    RunNotFoundError,
    SkillNotFoundError,
)

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent / "templates")
)


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(session)


def get_run_service(session: Session = Depends(get_db)) -> RunService:
    return RunService(session)


def get_skill_service(session: Session = Depends(get_db)) -> SkillService:
    return SkillService(session)


@router.get("/", response_class=HTMLResponse)
def tasks_list(
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    run_service: RunService = Depends(get_run_service),
):
    tasks = task_service.list()
    task_data = []
    for task in tasks:
        d = TaskResponse.model_validate(task).model_dump()
        last_run = run_service.last_run(task.id)
        d["last_run"] = (
            RunResponse.model_validate(last_run).model_dump() if last_run else None
        )
        task_data.append(d)
    return templates.TemplateResponse(request, "tasks_list.html", {"tasks": task_data})


@router.get("/tasks/new", response_class=HTMLResponse)
def task_form_new(
    request: Request,
    skill_service: SkillService = Depends(get_skill_service),
):
    all_skills = skill_service.list_all()
    return templates.TemplateResponse(
        request,
        "task_form.html",
        {
            "task": None,
            "all_skills": all_skills,
            "task_skill_ids": [],
            "task_skill_names": [],
        },
    )


@router.post("/tasks", response_class=HTMLResponse)
def task_create_form(
    name: str = Form(...),
    prompt: str = Form(...),
    cron_expression: str = Form(""),
    allowed_tools: str = Form(""),
    model: str = Form("sonnet"),
    enabled: str = Form(""),
    skill_ids: list[str] = Form(default=[]),
    task_service: TaskService = Depends(get_task_service),
    session: Session = Depends(get_db),
):
    task = task_service.create(
        name=name,
        prompt=prompt,
        cron_expression=cron_expression or None,
        allowed_tools=allowed_tools or None,
        model=model,
        enabled=bool(enabled),
    )
    if skill_ids:
        task_skill_crud.replace(session, task.id, skill_ids)
    return RedirectResponse("/ui/", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(
    request: Request,
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    run_service: RunService = Depends(get_run_service),
    session: Session = Depends(get_db),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    runs = run_service.list(task_id=task_id)
    task_skills = task_skill_crud.list_for_task(session, task_id)
    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {"task": task, "runs": runs, "task_skills": task_skills},
    )


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def task_edit_form(
    request: Request,
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    skill_service: SkillService = Depends(get_skill_service),
    session: Session = Depends(get_db),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    all_skills = skill_service.list_all()
    assigned = task_skill_crud.list_for_task(session, task_id)
    task_skill_ids = [s.id for s in assigned]
    task_skill_names = [s.name for s in assigned]
    return templates.TemplateResponse(
        request,
        "task_form.html",
        {
            "task": task,
            "all_skills": all_skills,
            "task_skill_ids": task_skill_ids,
            "task_skill_names": task_skill_names,
        },
    )


@router.post("/tasks/{task_id}", response_class=HTMLResponse)
def task_update_form(
    task_id: str,
    name: str = Form(...),
    prompt: str = Form(...),
    cron_expression: str = Form(""),
    allowed_tools: str = Form(""),
    model: str = Form("sonnet"),
    enabled: str = Form(""),
    skill_ids: list[str] = Form(default=[]),
    task_service: TaskService = Depends(get_task_service),
    session: Session = Depends(get_db),
):
    try:
        task_service.update(
            task_id,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression or None,
            allowed_tools=allowed_tools or None,
            model=model,
            enabled=bool(enabled),
        )
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    task_skill_crud.replace(session, task_id, skill_ids)
    return RedirectResponse(f"/ui/tasks/{task_id}", status_code=303)


# ── Skills UI ─────────────────────────────────────────


@router.get("/skills/", response_class=HTMLResponse)
def skills_list(
    request: Request,
    skill_service: SkillService = Depends(get_skill_service),
):
    local = [
        {"id": s.id, "name": s.name, "description": s.description, "source": s.source}
        for s in skill_service.list_local()
    ]
    global_skills = skill_service.list_global()
    all_skills = local + global_skills
    return templates.TemplateResponse(
        request, "skills_list.html", {"skills": all_skills}
    )


@router.get("/skills/new", response_class=HTMLResponse)
def skill_form_new(request: Request):
    return templates.TemplateResponse(request, "skill_form.html", {"skill": None})


@router.post("/skills", response_class=HTMLResponse)
def skill_create_form(
    name: str = Form(...),
    description: str = Form(""),
    content: str = Form(...),
    skill_service: SkillService = Depends(get_skill_service),
):
    skill_service.create(name=name, description=description, content=content)
    return RedirectResponse("/ui/skills/", status_code=303)


@router.get("/skills/{skill_id}", response_class=HTMLResponse)
def skill_detail(
    request: Request,
    skill_id: str,
    skill_service: SkillService = Depends(get_skill_service),
):
    try:
        skill = skill_service.get(skill_id)
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    return templates.TemplateResponse(request, "skill_detail.html", {"skill": skill})


@router.get("/skills/{skill_id}/edit", response_class=HTMLResponse)
def skill_edit_form(
    request: Request,
    skill_id: str,
    skill_service: SkillService = Depends(get_skill_service),
):
    try:
        skill = skill_service.get(skill_id)
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    return templates.TemplateResponse(request, "skill_form.html", {"skill": skill})


@router.post("/skills/{skill_id}", response_class=HTMLResponse)
def skill_update_form(
    skill_id: str,
    name: str = Form(...),
    description: str = Form(""),
    content: str = Form(...),
    skill_service: SkillService = Depends(get_skill_service),
):
    try:
        skill_service.update(
            skill_id, name=name, description=description, content=content
        )
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    return RedirectResponse(f"/ui/skills/{skill_id}", status_code=303)


# ── Runs UI ───────────────────────────────────────────


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = run_service.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse(request, "run_detail.html", {"run": run})


@router.get("/runs/{run_id}/card", response_class=HTMLResponse)
def run_card(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(get_run_service),
):
    try:
        run = run_service.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse(request, "partials/run_card.html", {"run": run})

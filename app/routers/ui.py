"""UI router serving Jinja2 templates with HTMX interactions."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.crud import task_skills as task_skill_crud
from app.utils.env_vars import parse_env_text
from app.schemas.task import TaskResponse
from app.schemas.run import RunResponse
from app.services import (
    TaskService,
    RunService,
    SkillService,
    PipelineService,
    PipelineRunService,
    TaskNotFoundError,
    RunNotFoundError,
    SkillNotFoundError,
    PipelineNotFoundError,
    PipelineRunNotFoundError,
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


def get_pipeline_service(session: Session = Depends(get_db)) -> PipelineService:
    return PipelineService(session)


def get_pipeline_run_service(
    session: Session = Depends(get_db),
) -> PipelineRunService:
    return PipelineRunService(session)


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
            "env_vars_text": "",
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
    env_vars: str = Form(""),
    skill_ids: list[str] = Form(default=[]),
    task_service: TaskService = Depends(get_task_service),
    session: Session = Depends(get_db),
):
    parsed_env = parse_env_text(env_vars)
    task = task_service.create(
        name=name,
        prompt=prompt,
        cron_expression=cron_expression or None,
        allowed_tools=allowed_tools or None,
        model=model,
        enabled=bool(enabled),
        env_vars=parsed_env,
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
    env_vars_keys: list[str] = []
    if task.env_vars:
        env_vars_keys = list(json.loads(task.env_vars).keys())
    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "task": task,
            "runs": runs,
            "task_skills": task_skills,
            "env_vars_keys": env_vars_keys,
        },
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
    env_vars_text = ""
    if task.env_vars:
        env = json.loads(task.env_vars)
        env_vars_text = "\n".join(f"{k}={v}" for k, v in env.items())
    return templates.TemplateResponse(
        request,
        "task_form.html",
        {
            "task": task,
            "all_skills": all_skills,
            "task_skill_ids": task_skill_ids,
            "task_skill_names": task_skill_names,
            "env_vars_text": env_vars_text,
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
    env_vars: str = Form(""),
    skill_ids: list[str] = Form(default=[]),
    task_service: TaskService = Depends(get_task_service),
    session: Session = Depends(get_db),
):
    parsed_env = parse_env_text(env_vars)
    try:
        task_service.update(
            task_id,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression or None,
            allowed_tools=allowed_tools or None,
            model=model,
            enabled=bool(enabled),
            env_vars=parsed_env,
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
    all_skills = skill_service.list_all()
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


# ── Pipelines UI ──────────────────────────────────────


@router.get("/pipelines/", response_class=HTMLResponse)
def pipelines_list(
    request: Request,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
    pipeline_run_service: PipelineRunService = Depends(get_pipeline_run_service),
):
    pipelines = pipeline_service.list()
    pipeline_data = []
    for pipeline in pipelines:
        d = {
            "id": pipeline.id,
            "name": pipeline.name,
            "description": pipeline.description,
            "enabled": pipeline.enabled,
            "steps_count": len(pipeline.steps),
        }
        last_run = pipeline_run_service.last_run(pipeline.id)
        d["last_run"] = (
            {
                "status": last_run.status,
                "duration_ms": last_run.duration_ms,
            }
            if last_run
            else None
        )
        pipeline_data.append(d)
    return templates.TemplateResponse(
        request, "pipelines_list.html", {"pipelines": pipeline_data}
    )


@router.get("/pipelines/new", response_class=HTMLResponse)
def pipeline_form_new(
    request: Request,
    task_service: TaskService = Depends(get_task_service),
):
    all_tasks = [{"id": t.id, "name": t.name} for t in task_service.list()]
    return templates.TemplateResponse(
        request,
        "pipeline_form.html",
        {"pipeline": None, "steps_text": "", "all_tasks": all_tasks},
    )


@router.post("/pipelines", response_class=HTMLResponse)
def pipeline_create_form(
    name: str = Form(...),
    description: str = Form(""),
    steps_text: str = Form(""),
    enabled: str = Form(""),
    task_service: TaskService = Depends(get_task_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    task_ids = _resolve_task_names(steps_text, task_service)
    pipeline_service.create(
        name=name,
        description=description or None,
        task_ids=task_ids,
        enabled=bool(enabled),
    )
    return RedirectResponse("/ui/pipelines/", status_code=303)


@router.get("/pipelines/{pipeline_id}", response_class=HTMLResponse)
def pipeline_detail(
    request: Request,
    pipeline_id: str,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
    pipeline_run_service: PipelineRunService = Depends(get_pipeline_run_service),
):
    try:
        pipeline = pipeline_service.get(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")
    runs = pipeline_run_service.list(pipeline_id=pipeline_id)
    return templates.TemplateResponse(
        request,
        "pipeline_detail.html",
        {"pipeline": pipeline, "runs": runs},
    )


@router.get("/pipelines/{pipeline_id}/edit", response_class=HTMLResponse)
def pipeline_edit_form(
    request: Request,
    pipeline_id: str,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
    task_service: TaskService = Depends(get_task_service),
):
    try:
        pipeline = pipeline_service.get(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")
    steps_text = "\n".join(step.task.name for step in pipeline.steps)
    all_tasks = [{"id": t.id, "name": t.name} for t in task_service.list()]
    return templates.TemplateResponse(
        request,
        "pipeline_form.html",
        {"pipeline": pipeline, "steps_text": steps_text, "all_tasks": all_tasks},
    )


@router.post("/pipelines/{pipeline_id}", response_class=HTMLResponse)
def pipeline_update_form(
    pipeline_id: str,
    name: str = Form(...),
    description: str = Form(""),
    steps_text: str = Form(""),
    enabled: str = Form(""),
    task_service: TaskService = Depends(get_task_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    try:
        pipeline_service.update(
            pipeline_id,
            name=name,
            description=description or None,
            enabled=bool(enabled),
        )
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")
    task_ids = _resolve_task_names(steps_text, task_service)
    pipeline_service.update_steps(pipeline_id, task_ids)
    return RedirectResponse(f"/ui/pipelines/{pipeline_id}", status_code=303)


@router.get("/pipeline-runs/{run_id}", response_class=HTMLResponse)
def pipeline_run_detail(
    request: Request,
    run_id: str,
    pipeline_run_service: PipelineRunService = Depends(get_pipeline_run_service),
):
    try:
        pipeline_run = pipeline_run_service.get(run_id)
    except PipelineRunNotFoundError:
        raise HTTPException(404, "Pipeline run not found")
    step_runs = sorted(pipeline_run.step_runs, key=lambda r: r.started_at)
    return templates.TemplateResponse(
        request,
        "pipeline_run_detail.html",
        {"pipeline_run": pipeline_run, "step_runs": step_runs},
    )


def _resolve_task_names(steps_text: str, task_service: TaskService) -> list[str]:
    """Parse textarea lines into task IDs by resolving task names."""
    task_ids: list[str] = []
    for line in steps_text.strip().splitlines():
        name = line.strip()
        if not name:
            continue
        try:
            task = task_service.get_by_name(name)
        except TaskNotFoundError:
            raise HTTPException(422, f"Task not found: {name}")
        task_ids.append(task.id)
    return task_ids


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

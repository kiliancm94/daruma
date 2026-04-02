"""UI router serving Jinja2 templates with HTMX interactions."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.task import TaskResponse
from app.schemas.run import RunResponse
from app.services import TaskService, RunService, TaskNotFoundError, RunNotFoundError

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent / "templates")
)


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(session)


def get_run_service(session: Session = Depends(get_db)) -> RunService:
    return RunService(session)


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
def task_form_new(request: Request):
    return templates.TemplateResponse(request, "task_form.html", {"task": None})


@router.post("/tasks", response_class=HTMLResponse)
def task_create_form(
    name: str = Form(...),
    prompt: str = Form(...),
    cron_expression: str = Form(""),
    allowed_tools: str = Form(""),
    enabled: str = Form(""),
    task_service: TaskService = Depends(get_task_service),
):
    task_service.create(
        name=name,
        prompt=prompt,
        cron_expression=cron_expression or None,
        allowed_tools=allowed_tools or None,
        enabled=bool(enabled),
    )
    return RedirectResponse("/ui/", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(
    request: Request,
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    run_service: RunService = Depends(get_run_service),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    runs = run_service.list(task_id=task_id)
    return templates.TemplateResponse(
        request, "task_detail.html", {"task": task, "runs": runs}
    )


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def task_edit_form(
    request: Request,
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return templates.TemplateResponse(request, "task_form.html", {"task": task})


@router.post("/tasks/{task_id}", response_class=HTMLResponse)
def task_update_form(
    task_id: str,
    name: str = Form(...),
    prompt: str = Form(...),
    cron_expression: str = Form(""),
    allowed_tools: str = Form(""),
    enabled: str = Form(""),
    task_service: TaskService = Depends(get_task_service),
):
    try:
        task_service.update(
            task_id,
            name=name,
            prompt=prompt,
            cron_expression=cron_expression or None,
            allowed_tools=allowed_tools or None,
            enabled=bool(enabled),
        )
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return RedirectResponse(f"/ui/tasks/{task_id}", status_code=303)


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

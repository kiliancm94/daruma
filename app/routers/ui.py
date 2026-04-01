"""UI router serving Jinja2 templates with HTMX interactions."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.repository import TaskRepo, RunRepo
from app.routers.tasks import get_task_repo
from app.routers.runs import get_run_repo

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def tasks_list(
    request: Request,
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
):
    tasks = task_repo.list()
    for task in tasks:
        task["last_run"] = run_repo.last_run(task["id"])
    return templates.TemplateResponse(request, "tasks_list.html", {"tasks": tasks})


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
    repo: TaskRepo = Depends(get_task_repo),
):
    repo.create(
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
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
):
    task = task_repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    runs = run_repo.list(task_id=task_id)
    return templates.TemplateResponse(request, "task_detail.html", {"task": task, "runs": runs})


@router.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def task_edit_form(
    request: Request,
    task_id: str,
    repo: TaskRepo = Depends(get_task_repo),
):
    task = repo.get(task_id)
    if not task:
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
    repo: TaskRepo = Depends(get_task_repo),
):
    repo.update(
        task_id,
        name=name,
        prompt=prompt,
        cron_expression=cron_expression or None,
        allowed_tools=allowed_tools or None,
        enabled=bool(enabled),
    )
    return RedirectResponse(f"/ui/tasks/{task_id}", status_code=303)


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: str,
    repo: RunRepo = Depends(get_run_repo),
):
    run = repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse(request, "run_detail.html", {"run": run})


@router.get("/runs/{run_id}/card", response_class=HTMLResponse)
def run_card(
    request: Request,
    run_id: str,
    repo: RunRepo = Depends(get_run_repo),
):
    run = repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return templates.TemplateResponse(request, "partials/run_card.html", {"run": run})

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import RunRepo
from app.runner import run_claude
from app.services import (
    TaskService,
    RunNotFoundError,
    TaskNotFoundError,
    execute_task_bg,
    cancel_task_run,
)

router = APIRouter(tags=["triggers"])


def get_task_service() -> TaskService:
    raise RuntimeError("not configured")


def get_run_repo() -> RunRepo:
    raise RuntimeError("not configured")


def get_runner() -> Callable:
    return run_claude


@router.post("/api/tasks/{task_id}/run", response_model=RunResponse)
def manual_trigger(
    task_id: str,
    task_svc: TaskService = Depends(get_task_service),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_svc.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_bg(task, run_repo, trigger="manual", runner=runner)


@router.post("/api/trigger/{task_name}", response_model=RunResponse)
def webhook_trigger(
    task_name: str,
    task_svc: TaskService = Depends(get_task_service),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_svc.get_by_name(task_name)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_bg(task, run_repo, trigger="webhook", runner=runner)


@router.post("/api/runs/{run_id}/cancel")
def cancel_run_endpoint(
    run_id: str,
    run_repo: RunRepo = Depends(get_run_repo),
):
    try:
        cancel_task_run(run_id, run_repo)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "cancelled"}

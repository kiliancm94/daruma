from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import TaskRepo, RunRepo
from app.runner import run_claude

router = APIRouter(tags=["triggers"])


def get_task_repo() -> TaskRepo:
    raise RuntimeError("not configured")


def get_run_repo() -> RunRepo:
    raise RuntimeError("not configured")


def get_runner() -> Callable:
    return run_claude


def _execute_task(
    task: dict, trigger: str, run_repo: RunRepo, runner: Callable
) -> dict:
    run = run_repo.create(task_id=task["id"], trigger=trigger)
    result = runner(task["prompt"], allowed_tools=task.get("allowed_tools"))
    status = "success" if result["exit_code"] == 0 else "failed"
    return run_repo.complete(
        run["id"],
        status=status,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
    )


@router.post("/api/tasks/{task_id}/run", response_model=RunResponse)
def manual_trigger(
    task_id: str,
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    task = task_repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return _execute_task(task, "manual", run_repo, runner)


@router.post("/api/trigger/{task_name}", response_model=RunResponse)
def webhook_trigger(
    task_name: str,
    task_repo: TaskRepo = Depends(get_task_repo),
    run_repo: RunRepo = Depends(get_run_repo),
    runner: Callable = Depends(get_runner),
):
    task = task_repo.get_by_name(task_name)
    if not task:
        raise HTTPException(404, "Task not found")
    return _execute_task(task, "webhook", run_repo, runner)

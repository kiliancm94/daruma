import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import TaskRepo, RunRepo
from app.runner import run_claude, cancel_run

router = APIRouter(tags=["triggers"])


def get_task_repo() -> TaskRepo:
    raise RuntimeError("not configured")


def get_run_repo() -> RunRepo:
    raise RuntimeError("not configured")


def get_runner() -> Callable:
    return run_claude


def _execute_task_bg(
    task: dict, run_id: str, runner: Callable, run_repo: RunRepo
) -> None:
    """Run Claude in background thread and update the run record when done."""
    try:
        result = runner(
            task["prompt"],
            allowed_tools=task.get("allowed_tools"),
            run_id=run_id,
            on_output=lambda stdout: run_repo.update_output(run_id, stdout),
        )
        status = "success" if result["exit_code"] == 0 else "failed"
        run_repo.complete(
            run_id,
            status=status,
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
        )
    except Exception as e:
        run_repo.complete(
            run_id, status="failed", stdout="", stderr=str(e), exit_code=-1
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
    run = run_repo.create(task_id=task["id"], trigger="manual")
    threading.Thread(
        target=_execute_task_bg,
        args=(task, run["id"], runner, run_repo),
        daemon=True,
    ).start()
    return run


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
    run = run_repo.create(task_id=task["id"], trigger="webhook")
    threading.Thread(
        target=_execute_task_bg,
        args=(task, run["id"], runner, run_repo),
        daemon=True,
    ).start()
    return run


@router.post("/api/runs/{run_id}/cancel")
def cancel_run_endpoint(
    run_id: str,
    run_repo: RunRepo = Depends(get_run_repo),
):
    run = run_repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run["status"] != "running":
        raise HTTPException(400, "Run is not active")
    killed = cancel_run(run_id)
    if not killed:
        # Process already finished between check and kill
        run_repo.complete(run_id, status="failed", stdout="", stderr="Cancelled", exit_code=-1)
    return {"status": "cancelled"}

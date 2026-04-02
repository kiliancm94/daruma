from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.crud import TaskRepo, RunRepo
from app.db import get_db
from app.db import get_session_factory as _get_session_factory
from app.models.schemas import RunResponse
from app.runner import run_claude
from app.services import (
    TaskService,
    RunNotFoundError,
    TaskNotFoundError,
    execute_task_background,
    cancel_task_run,
)

router = APIRouter(tags=["triggers"])


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepo(session))


def get_run_repo(session: Session = Depends(get_db)) -> RunRepo:
    return RunRepo(session)


def get_session_factory() -> sessionmaker:
    return _get_session_factory()


def get_runner() -> Callable:
    return run_claude


@router.post("/api/tasks/{task_id}/run", response_model=RunResponse)
def manual_trigger(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    session_factory: sessionmaker = Depends(get_session_factory),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_background(
        task, session_factory, trigger="manual", runner=runner
    )


@router.post("/api/trigger/{task_name}", response_model=RunResponse)
def webhook_trigger(
    task_name: str,
    task_service: TaskService = Depends(get_task_service),
    session_factory: sessionmaker = Depends(get_session_factory),
    runner: Callable = Depends(get_runner),
):
    try:
        task = task_service.get_by_name(task_name)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return execute_task_background(
        task, session_factory, trigger="webhook", runner=runner
    )


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

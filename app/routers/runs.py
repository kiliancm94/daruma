from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.repository import RunRepo

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_repo() -> RunRepo:
    raise RuntimeError("run_repo dependency not configured")


@router.get("", response_model=list[RunResponse])
def list_runs(task_id: str | None = None, repo: RunRepo = Depends(get_run_repo)):
    return repo.list(task_id=task_id)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, repo: RunRepo = Depends(get_run_repo)):
    run = repo.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run

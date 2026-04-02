from fastapi import APIRouter, Depends, HTTPException

from app.models import RunResponse
from app.services import RunService, RunNotFoundError

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_service() -> RunService:
    raise RuntimeError("run_service dependency not configured")


@router.get("", response_model=list[RunResponse])
def list_runs(
    task_id: str | None = None, svc: RunService = Depends(get_run_service)
):
    return svc.list(task_id=task_id)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, svc: RunService = Depends(get_run_service)):
    try:
        return svc.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")

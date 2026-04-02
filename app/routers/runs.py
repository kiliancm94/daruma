from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import RunRepo
from app.db import get_db
from app.models.schemas import RunResponse
from app.services import RunService, RunNotFoundError

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_service(session: Session = Depends(get_db)) -> RunService:
    return RunService(RunRepo(session))


@router.get("", response_model=list[RunResponse])
def list_runs(
    task_id: str | None = None, run_service: RunService = Depends(get_run_service)
):
    return run_service.list(task_id=task_id)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, run_service: RunService = Depends(get_run_service)):
    try:
        return run_service.get(run_id)
    except RunNotFoundError:
        raise HTTPException(404, "Run not found")

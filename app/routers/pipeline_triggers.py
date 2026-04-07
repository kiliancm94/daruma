"""REST API endpoints for triggering pipeline runs."""

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db
from app.db import get_session_factory as _get_session_factory
from app.runner import run_claude
from app.schemas.pipeline import PipelineRunResponse, PipelineTrigger
from app.services import (
    PipelineService,
    PipelineRunService,
    PipelineNotFoundError,
    PipelineRunNotFoundError,
    execute_pipeline_background,
)

router = APIRouter(tags=["pipeline-triggers"])


def get_pipeline_service(session: Session = Depends(get_db)) -> PipelineService:
    return PipelineService(session)


def get_pipeline_run_service(
    session: Session = Depends(get_db),
) -> PipelineRunService:
    return PipelineRunService(session)


def get_session_factory() -> sessionmaker:
    return _get_session_factory()


def get_runner() -> Callable:
    return run_claude


@router.post("/api/pipelines/{pipeline_id}/run", response_model=PipelineRunResponse)
def trigger_pipeline(
    pipeline_id: str,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
    session_factory: sessionmaker = Depends(get_session_factory),
    runner: Callable = Depends(get_runner),
):
    try:
        pipeline = pipeline_service.get(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")
    return execute_pipeline_background(
        pipeline, session_factory, trigger=PipelineTrigger.manual, runner=runner
    )


@router.get("/api/pipeline-runs/{run_id}", response_model=PipelineRunResponse)
def get_pipeline_run(
    run_id: str,
    pipeline_run_service: PipelineRunService = Depends(get_pipeline_run_service),
):
    try:
        return pipeline_run_service.get(run_id)
    except PipelineRunNotFoundError:
        raise HTTPException(404, "Pipeline run not found")

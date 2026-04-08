"""REST API endpoints for pipeline management."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineResponse
from app.services import PipelineService, PipelineNotFoundError

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


def get_pipeline_service(session: Session = Depends(get_db)) -> PipelineService:
    return PipelineService(session)


@router.get("", response_model=list[PipelineResponse])
def list_pipelines(pipeline_service: PipelineService = Depends(get_pipeline_service)):
    return pipeline_service.list()


@router.post("", response_model=PipelineResponse, status_code=201)
def create_pipeline(
    body: PipelineCreate,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    try:
        return pipeline_service.create(
            name=body.name,
            description=body.description,
            task_ids=body.steps,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{pipeline_id}", response_model=PipelineResponse)
def get_pipeline(
    pipeline_id: str,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    try:
        return pipeline_service.get(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")


@router.put("/{pipeline_id}", response_model=PipelineResponse)
def update_pipeline(
    pipeline_id: str,
    body: PipelineUpdate,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    try:
        return pipeline_service.update(
            pipeline_id, **body.model_dump(exclude_unset=True)
        )
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(
    pipeline_id: str,
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    try:
        pipeline_service.delete(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(404, "Pipeline not found")
    return Response(status_code=204)

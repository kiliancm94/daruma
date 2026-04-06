"""Pydantic schemas for pipelines — API and CLI input/output."""

from pydantic import BaseModel, ConfigDict


class PipelineStepCreate(BaseModel):
    task_id: str


class PipelineCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[str]  # list of task IDs


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class PipelineStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pipeline_id: str
    task_id: str
    step_order: int


class PipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    enabled: bool
    created_at: str
    updated_at: str
    steps: list[PipelineStepResponse]


class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pipeline_id: str
    status: str
    trigger: str
    current_step: int | None
    started_at: str
    finished_at: str | None
    duration_ms: int | None

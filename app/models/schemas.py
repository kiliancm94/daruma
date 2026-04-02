"""Pydantic schemas — define input/output for API and CLI.

Base response models use from_attributes=True to auto-parse from ORM objects.
"""

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    name: str
    prompt: str
    cron_expression: str | None = None
    allowed_tools: str | None = None
    enabled: bool = True


class TaskUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    cron_expression: str | None = None
    allowed_tools: str | None = None
    enabled: bool | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt: str
    cron_expression: str | None
    allowed_tools: str | None
    enabled: bool
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    trigger: str
    status: str
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    activity: str | None = None

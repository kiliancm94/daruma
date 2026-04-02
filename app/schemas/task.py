"""Pydantic schemas for tasks — API and CLI input/output."""

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    name: str
    prompt: str
    cron_expression: str | None = None
    allowed_tools: str | None = None
    model: str = "sonnet"
    enabled: bool = True


class TaskUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    cron_expression: str | None = None
    allowed_tools: str | None = None
    model: str | None = None
    enabled: bool | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt: str
    cron_expression: str | None
    allowed_tools: str | None
    model: str
    enabled: bool
    created_at: str
    updated_at: str

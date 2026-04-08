"""Pydantic schemas for runs — API and CLI input/output."""

from pydantic import BaseModel, ConfigDict


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

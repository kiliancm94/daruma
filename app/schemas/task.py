"""Pydantic schemas for tasks — API and CLI input/output."""

import json

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class OutputFormat(StrEnum):
    text = "text"
    json = "json"
    md = "md"


class OutputDestination(StrEnum):
    pipeline = "pipeline"


class TaskCreate(BaseModel):
    name: str
    prompt: str
    cron_expression: str | None = None
    allowed_tools: str | None = None
    model: str = "sonnet"
    enabled: bool = True
    output_format: OutputFormat | None = None
    output_destination: str | None = None
    env_vars: dict[str, str] | None = None


class TaskUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    cron_expression: str | None = None
    allowed_tools: str | None = None
    model: str | None = None
    enabled: bool | None = None
    output_format: OutputFormat | None = None
    output_destination: str | None = None
    env_vars: dict[str, str] | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt: str
    cron_expression: str | None
    allowed_tools: str | None
    model: str
    enabled: bool
    output_format: OutputFormat | None
    output_destination: str | None
    env_vars: dict[str, str] | None
    created_at: str
    updated_at: str

    @field_validator("env_vars", mode="before")
    @classmethod
    def parse_env_vars(cls, v: object) -> object:
        """Deserialize JSON string from DB into a dict."""
        if isinstance(v, str):
            return json.loads(v)
        return v

"""Pydantic schemas for tasks — API and CLI input/output."""

from pydantic import BaseModel, ConfigDict, field_validator

VALID_OUTPUT_FORMATS = ("text", "json", "md")


class TaskCreate(BaseModel):
    name: str
    prompt: str
    cron_expression: str | None = None
    allowed_tools: str | None = None
    model: str = "sonnet"
    enabled: bool = True
    output_format: str | None = None
    output_destination: str | None = None

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of: {', '.join(VALID_OUTPUT_FORMATS)}"
            )
        return v


class TaskUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    cron_expression: str | None = None
    allowed_tools: str | None = None
    model: str | None = None
    enabled: bool | None = None
    output_format: str | None = None
    output_destination: str | None = None

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of: {', '.join(VALID_OUTPUT_FORMATS)}"
            )
        return v


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt: str
    cron_expression: str | None
    allowed_tools: str | None
    model: str
    enabled: bool
    output_format: str | None
    output_destination: str | None
    created_at: str
    updated_at: str

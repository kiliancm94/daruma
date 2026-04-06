"""Pydantic schemas for skills."""

from pydantic import BaseModel, ConfigDict


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    content: str


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    content: str
    source: str
    created_at: str
    updated_at: str

"""Pydantic schemas for skills."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SkillSource(StrEnum):
    local = "local"
    global_ = "global"


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    content: str
    source: SkillSource = SkillSource.local


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    name: str
    description: str
    content: str
    source: SkillSource = SkillSource.local

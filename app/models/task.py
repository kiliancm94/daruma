"""SQLAlchemy ORM model for tasks."""

import uuid

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.date_helpers import utcnow

if TYPE_CHECKING:
    from app.models.run import Run
    from app.models.skill import Skill


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String, nullable=True)
    allowed_tools: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str] = mapped_column(
        String, nullable=False, default="sonnet", server_default="sonnet"
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    output_format: Mapped[str | None] = mapped_column(String, nullable=True)
    output_destination: Mapped[str | None] = mapped_column(String, nullable=True)
    env_vars: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)

    runs: Mapped[list["Run"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill", secondary="task_skills", backref="tasks"
    )

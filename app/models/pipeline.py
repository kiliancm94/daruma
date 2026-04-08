"""SQLAlchemy ORM models for pipelines and pipeline steps."""

import uuid

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.date_helpers import utcnow

if TYPE_CHECKING:
    from app.models.pipeline_run import PipelineRun
    from app.models.task import Task


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)

    steps: Mapped[list["PipelineStep"]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="PipelineStep.step_order",
    )
    runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan"
    )


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "step_order", name="uq_pipeline_step_order"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="steps")
    task: Mapped["Task"] = relationship()

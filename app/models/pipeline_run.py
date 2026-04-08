"""SQLAlchemy ORM model for pipeline runs."""

import uuid

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.date_helpers import utcnow

if TYPE_CHECKING:
    from app.models.pipeline import Pipeline
    from app.models.run import Run


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    current_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="runs")
    step_runs: Mapped[list["Run"]] = relationship(back_populates="pipeline_run")

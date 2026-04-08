"""SQLAlchemy association table for task-skill many-to-many."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskSkill(Base):
    __tablename__ = "task_skills"

    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    skill_name: Mapped[str] = mapped_column(String, primary_key=True)

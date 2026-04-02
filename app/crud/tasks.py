"""CRUD operations for tasks."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.database import Task


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRepo:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        enabled: bool = True,
    ) -> Task:
        now = _utcnow()
        task = Task(
            name=name,
            prompt=prompt,
            cron_expression=cron_expression,
            allowed_tools=allowed_tools,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get(self, task_id: str) -> Task | None:
        return self.session.get(Task, task_id)

    def get_by_name(self, name: str) -> Task | None:
        return self.session.query(Task).filter(Task.name == name).first()

    def list(self) -> list[Task]:
        return self.session.query(Task).order_by(Task.created_at.desc()).all()

    _UPDATABLE_FIELDS = {"name", "prompt", "cron_expression", "allowed_tools", "enabled"}

    def update(self, task_id: str, **fields) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        updates = {
            k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS and v is not None
        }
        if not updates:
            return task
        for key, value in updates.items():
            setattr(task, key, value)
        task.updated_at = _utcnow()
        self.session.commit()
        self.session.refresh(task)
        return task

    def delete(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task is None:
            return False
        self.session.delete(task)
        self.session.commit()
        return True

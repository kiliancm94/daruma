"""CRUD operations for tasks."""

from sqlalchemy.orm import Session

from app.crud.exceptions import NotFoundError
from app.models.task import Task
from app.schemas.task import TaskUpdate, OutputFormat
from app.utils.date_helpers import utcnow


def create(
    session: Session,
    name: str,
    prompt: str,
    cron_expression: str | None = None,
    allowed_tools: str | None = None,
    model: str = "sonnet",
    enabled: bool = True,
    output_format: OutputFormat | None = None,
    output_destination: str | None = None,
) -> Task:
    task = Task(
        name=name,
        prompt=prompt,
        cron_expression=cron_expression,
        allowed_tools=allowed_tools,
        model=model,
        enabled=enabled,
        output_format=output_format,
        output_destination=output_destination,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get(session: Session, task_id: str) -> Task | None:
    return session.get(Task, task_id)


def get_by_name(session: Session, name: str) -> Task | None:
    return session.query(Task).filter(Task.name == name).first()


def get_all(session: Session) -> list[Task]:
    return session.query(Task).order_by(Task.created_at.desc()).all()


def update(session: Session, task_id: str, **fields) -> Task:
    """Update a task. Raises NotFoundError if the task does not exist."""
    if (task := get(session, task_id)) is None:
        raise NotFoundError(f"Task not found: {task_id}")
    validated = TaskUpdate(**fields).model_dump(exclude_unset=True)
    if not validated:
        return task
    for key, value in validated.items():
        setattr(task, key, value)
    task.updated_at = utcnow()
    session.commit()
    session.refresh(task)
    return task


def delete(session: Session, task_id: str) -> None:
    """Delete a task. Raises NotFoundError if the task does not exist."""
    if (task := get(session, task_id)) is None:
        raise NotFoundError(f"Task not found: {task_id}")
    session.delete(task)
    session.commit()

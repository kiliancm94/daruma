"""CRUD for task-skill assignments."""

from sqlalchemy.orm import Session

from app.models.task_skill import TaskSkill


def assign(session: Session, task_id: str, skill_name: str) -> None:
    if not session.get(TaskSkill, (task_id, skill_name)):
        session.add(TaskSkill(task_id=task_id, skill_name=skill_name))
        session.commit()


def unassign(session: Session, task_id: str, skill_name: str) -> None:
    link = session.get(TaskSkill, (task_id, skill_name))
    if link:
        session.delete(link)
        session.commit()


def list_for_task(session: Session, task_id: str) -> list[str]:
    """Return skill names assigned to a task."""
    rows = (
        session.query(TaskSkill.skill_name)
        .filter(TaskSkill.task_id == task_id)
        .order_by(TaskSkill.skill_name)
        .all()
    )
    return [r.skill_name for r in rows]


def replace(session: Session, task_id: str, skill_names: list[str]) -> None:
    session.query(TaskSkill).filter(TaskSkill.task_id == task_id).delete()
    for name in skill_names:
        session.add(TaskSkill(task_id=task_id, skill_name=name))
    session.commit()

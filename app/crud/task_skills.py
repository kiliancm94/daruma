"""CRUD for task-skill assignments."""

from sqlalchemy.orm import Session

from app.models.skill import Skill
from app.models.task_skill import TaskSkill


def assign(session: Session, task_id: str, skill_id: str) -> None:
    if not session.get(TaskSkill, (task_id, skill_id)):
        session.add(TaskSkill(task_id=task_id, skill_id=skill_id))
        session.commit()


def unassign(session: Session, task_id: str, skill_id: str) -> None:
    link = session.get(TaskSkill, (task_id, skill_id))
    if link:
        session.delete(link)
        session.commit()


def list_for_task(session: Session, task_id: str) -> list[Skill]:
    return (
        session.query(Skill)
        .join(TaskSkill, TaskSkill.skill_id == Skill.id)
        .filter(TaskSkill.task_id == task_id)
        .order_by(Skill.name)
        .all()
    )


def replace(session: Session, task_id: str, skill_ids: list[str]) -> None:
    session.query(TaskSkill).filter(TaskSkill.task_id == task_id).delete()
    for sid in skill_ids:
        session.add(TaskSkill(task_id=task_id, skill_id=sid))
    session.commit()

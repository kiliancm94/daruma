"""CRUD operations for skills."""

from sqlalchemy.orm import Session

from app.crud.exceptions import NotFoundError
from app.models.skill import Skill
from app.schemas.skill import SkillUpdate
from app.utils.date_helpers import utcnow


def create(
    session: Session,
    name: str,
    description: str = "",
    content: str = "",
    source: str = "local",
) -> Skill:
    skill = Skill(name=name, description=description, content=content, source=source)
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


def get(session: Session, skill_id: str) -> Skill | None:
    return session.get(Skill, skill_id)


def get_by_name(session: Session, name: str) -> Skill | None:
    return session.query(Skill).filter(Skill.name == name).first()


def get_all(session: Session) -> list[Skill]:
    return session.query(Skill).order_by(Skill.name).all()


def update(session: Session, skill_id: str, **fields) -> Skill:
    """Update a skill. Raises NotFoundError if the skill does not exist."""
    if (skill := get(session, skill_id)) is None:
        raise NotFoundError(f"Skill not found: {skill_id}")
    validated = SkillUpdate(**fields).model_dump(exclude_unset=True)
    if not validated:
        return skill
    for key, value in validated.items():
        setattr(skill, key, value)
    skill.updated_at = utcnow()
    session.commit()
    session.refresh(skill)
    return skill


def delete(session: Session, skill_id: str) -> None:
    """Delete a skill. Raises NotFoundError if the skill does not exist."""
    if (skill := get(session, skill_id)) is None:
        raise NotFoundError(f"Skill not found: {skill_id}")
    session.delete(skill)
    session.commit()

"""API router for skills management."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.crud import task_skills as task_skill_crud
from app.schemas.skill import SkillCreate, SkillUpdate, SkillResponse
from app.services import SkillService, SkillNotFoundError

router = APIRouter(prefix="/api", tags=["skills"])


def get_skill_service(session: Session = Depends(get_db)) -> SkillService:
    return SkillService(session)


@router.get("/skills", response_model=list[SkillResponse])
def list_skills(skill_service: SkillService = Depends(get_skill_service)):
    return skill_service.list_all()


@router.post("/skills", response_model=SkillResponse, status_code=201)
def create_skill(
    body: SkillCreate, skill_service: SkillService = Depends(get_skill_service)
):
    try:
        return skill_service.create(
            name=body.name,
            description=body.description,
            content=body.content,
            source=body.source,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/skills/{name}", response_model=SkillResponse)
def get_skill(name: str, skill_service: SkillService = Depends(get_skill_service)):
    try:
        return skill_service.get(name)
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")


@router.put("/skills/{name}", response_model=SkillResponse)
def update_skill(
    name: str,
    body: SkillUpdate,
    skill_service: SkillService = Depends(get_skill_service),
):
    try:
        return skill_service.update(name, **body.model_dump(exclude_unset=True))
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/skills/{name}", status_code=204)
def delete_skill(name: str, skill_service: SkillService = Depends(get_skill_service)):
    try:
        skill_service.delete(name)
    except SkillNotFoundError:
        raise HTTPException(404, "Skill not found")
    return Response(status_code=204)


# ── Task-Skill assignment ────────────────────────────


class TaskSkillsBody(BaseModel):
    skill_names: list[str]


@router.get("/tasks/{task_id}/skills", response_model=list[SkillResponse])
def list_task_skills(
    task_id: str,
    session: Session = Depends(get_db),
):
    skill_svc = SkillService(session)
    names = task_skill_crud.list_for_task(session, task_id)
    results = []
    for n in names:
        try:
            results.append(skill_svc.resolve(n))
        except SkillNotFoundError:
            pass  # skill was deleted, skip
    return results


@router.put("/tasks/{task_id}/skills")
def replace_task_skills(
    task_id: str, body: TaskSkillsBody, session: Session = Depends(get_db)
):
    task_skill_crud.replace(session, task_id, body.skill_names)
    return {"status": "ok"}

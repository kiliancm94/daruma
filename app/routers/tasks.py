from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.crud import TaskRepo
from app.db import get_db
from app.models.schemas import TaskCreate, TaskUpdate, TaskResponse
from app.services import TaskService, TaskNotFoundError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_service(session: Session = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepo(session))


@router.get("", response_model=list[TaskResponse])
def list_tasks(task_service: TaskService = Depends(get_task_service)):
    return task_service.list()


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    body: TaskCreate, task_service: TaskService = Depends(get_task_service)
):
    return task_service.create(
        name=body.name,
        prompt=body.prompt,
        cron_expression=body.cron_expression,
        allowed_tools=body.allowed_tools,
        enabled=body.enabled,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, task_service: TaskService = Depends(get_task_service)):
    try:
        return task_service.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    body: TaskUpdate,
    task_service: TaskService = Depends(get_task_service),
):
    try:
        return task_service.update(task_id, **body.model_dump(exclude_unset=True))
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, task_service: TaskService = Depends(get_task_service)):
    try:
        task_service.delete(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return Response(status_code=204)

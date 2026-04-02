from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import TaskCreate, TaskUpdate, TaskResponse
from app.services import TaskService, TaskNotFoundError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_service() -> TaskService:
    raise RuntimeError("task_service dependency not configured")


@router.get("", response_model=list[TaskResponse])
def list_tasks(svc: TaskService = Depends(get_task_service)):
    return svc.list()


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreate, svc: TaskService = Depends(get_task_service)):
    return svc.create(
        name=body.name,
        prompt=body.prompt,
        cron_expression=body.cron_expression,
        allowed_tools=body.allowed_tools,
        enabled=body.enabled,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, svc: TaskService = Depends(get_task_service)):
    try:
        return svc.get(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str, body: TaskUpdate, svc: TaskService = Depends(get_task_service)
):
    try:
        return svc.update(task_id, **body.model_dump(exclude_unset=True))
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, svc: TaskService = Depends(get_task_service)):
    try:
        svc.delete(task_id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")
    return Response(status_code=204)

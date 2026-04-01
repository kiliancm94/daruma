from fastapi import APIRouter, Depends, HTTPException, Response

from app.models import TaskCreate, TaskUpdate, TaskResponse
from app.repository import TaskRepo

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_repo() -> TaskRepo:
    raise RuntimeError("task_repo dependency not configured")


@router.get("", response_model=list[TaskResponse])
def list_tasks(repo: TaskRepo = Depends(get_task_repo)):
    return repo.list()


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreate, repo: TaskRepo = Depends(get_task_repo)):
    return repo.create(
        name=body.name,
        prompt=body.prompt,
        cron_expression=body.cron_expression,
        allowed_tools=body.allowed_tools,
        enabled=body.enabled,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, repo: TaskRepo = Depends(get_task_repo)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, body: TaskUpdate, repo: TaskRepo = Depends(get_task_repo)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return repo.update(task_id, **body.model_dump(exclude_unset=True))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, repo: TaskRepo = Depends(get_task_repo)):
    if not repo.delete(task_id):
        raise HTTPException(404, "Task not found")
    return Response(status_code=204)

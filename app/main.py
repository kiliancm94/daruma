from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import DB_PATH
from app.db import init_db
from app.repository import TaskRepo, RunRepo
from app.runner import run_claude
from app.scheduler import create_scheduler, sync_jobs
from app.services import TaskService, RunService, execute_task
from app.routers import tasks as tasks_router
from app.routers import runs as runs_router
from app.routers import triggers as triggers_router
from app.routers import ui as ui_router

_conn = None
_scheduler = None


def _execute_cron_task(task_id: str) -> None:
    task_repo = TaskRepo(_conn)
    run_repo = RunRepo(_conn)
    task = task_repo.get(task_id)
    if not task:
        return
    execute_task(task, run_repo, trigger="cron")


def _refresh_scheduler() -> None:
    if _conn and _scheduler:
        tasks = TaskRepo(_conn).list()
        sync_jobs(_scheduler, tasks, _execute_cron_task)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn, _scheduler
    _conn = init_db(DB_PATH, check_same_thread=False)
    _scheduler = create_scheduler()

    task_service = TaskService(TaskRepo(_conn))
    run_service = RunService(RunRepo(_conn))
    run_repo = RunRepo(_conn)

    # Wire up dependency overrides
    app.dependency_overrides[tasks_router.get_task_service] = lambda: task_service
    app.dependency_overrides[runs_router.get_run_service] = lambda: run_service
    app.dependency_overrides[triggers_router.get_task_service] = lambda: task_service
    app.dependency_overrides[triggers_router.get_run_repo] = lambda: run_repo
    app.dependency_overrides[triggers_router.get_runner] = lambda: run_claude
    app.dependency_overrides[ui_router.get_task_service] = lambda: task_service
    app.dependency_overrides[ui_router.get_run_service] = lambda: run_service

    _refresh_scheduler()
    _scheduler.start()
    yield
    _scheduler.shutdown()
    _conn.close()


app = FastAPI(title="Daruma — Claude Automations Runner", lifespan=lifespan)

app.include_router(tasks_router.router)
app.include_router(runs_router.router)
app.include_router(triggers_router.router)
app.include_router(ui_router.router)

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}

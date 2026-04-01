from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import DB_PATH
from app.db import init_db
from app.repository import TaskRepo, RunRepo
from app.runner import run_claude
from app.scheduler import create_scheduler, sync_jobs
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
    run = run_repo.create(task_id=task["id"], trigger="cron")
    result = run_claude(
        task["prompt"], allowed_tools=task.get("allowed_tools"), run_id=run["id"]
    )
    status = "success" if result["exit_code"] == 0 else "failed"
    run_repo.complete(
        run["id"], status=status,
        stdout=result["stdout"], stderr=result["stderr"],
        exit_code=result["exit_code"],
    )


def _refresh_scheduler() -> None:
    if _conn and _scheduler:
        tasks = TaskRepo(_conn).list()
        sync_jobs(_scheduler, tasks, _execute_cron_task)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn, _scheduler
    _conn = init_db(DB_PATH, check_same_thread=False)
    _scheduler = create_scheduler()

    # Wire up dependency overrides
    app.dependency_overrides[tasks_router.get_task_repo] = lambda: TaskRepo(_conn)
    app.dependency_overrides[runs_router.get_run_repo] = lambda: RunRepo(_conn)
    app.dependency_overrides[triggers_router.get_task_repo] = lambda: TaskRepo(_conn)
    app.dependency_overrides[triggers_router.get_run_repo] = lambda: RunRepo(_conn)
    app.dependency_overrides[triggers_router.get_runner] = lambda: run_claude

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

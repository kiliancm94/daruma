from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import DB_PATH
from app.crud import tasks as task_crud
from app.db import init_db, get_session, dispose
from app.scheduler import create_scheduler, sync_jobs
from app.services import execute_task, SkillService
from app.routers import tasks as tasks_router
from app.routers import runs as runs_router
from app.routers import skills as skills_router
from app.routers import triggers as triggers_router
from app.routers import pipelines as pipelines_router
from app.routers import pipeline_triggers as pipeline_triggers_router
from app.routers import ui as ui_router

_scheduler = None


def _execute_cron_task(task_id: str) -> None:
    session = get_session()
    try:
        task = task_crud.get(session, task_id)
        if not task:
            return
        execute_task(task, session, trigger="cron")
    finally:
        session.close()


def _refresh_scheduler() -> None:
    if _scheduler:
        session = get_session()
        try:
            tasks = task_crud.get_all(session)
            sync_jobs(_scheduler, tasks, _execute_cron_task)
        finally:
            session.close()


def _sync_global_skills() -> None:
    session = get_session()
    try:
        SkillService(session).sync_global()
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db(DB_PATH)
    _sync_global_skills()
    _scheduler = create_scheduler()
    _refresh_scheduler()
    _scheduler.start()
    yield
    _scheduler.shutdown()
    dispose()


app = FastAPI(title="Daruma — Claude Automations Runner", lifespan=lifespan)

app.include_router(tasks_router.router)
app.include_router(runs_router.router)
app.include_router(skills_router.router)
app.include_router(triggers_router.router)
app.include_router(pipelines_router.router)
app.include_router(pipeline_triggers_router.router)
app.include_router(ui_router.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")


@app.get("/health")
def health():
    return {"status": "ok"}


static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.db import get_db
from app.routers.runs import router


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def task_with_runs(db_session):
    task = task_crud.create(db_session, name="T", prompt="p")
    r1 = run_crud.create(db_session, task_id=task.id, trigger="manual")
    run_crud.complete(
        db_session, r1.id, status="success", stdout="ok", stderr="", exit_code=0
    )
    r2 = run_crud.create(db_session, task_id=task.id, trigger="cron")
    return task, r1, r2


def test_list_runs_for_task(client, task_with_runs):
    task, _, _ = task_with_runs
    resp = client.get(f"/api/runs?task_id={task.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_all_runs(client, task_with_runs):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_run(client, task_with_runs):
    _, r1, _ = task_with_runs
    resp = client.get(f"/api/runs/{r1.id}")
    assert resp.status_code == 200
    assert resp.json()["trigger"] == "manual"


def test_get_run_not_found(client):
    resp = client.get("/api/runs/nonexistent")
    assert resp.status_code == 404

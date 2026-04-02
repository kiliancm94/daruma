import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crud import TaskRepo, RunRepo
from app.db import get_db
from app.routers.runs import router


@pytest.fixture
def repos(db_session):
    return TaskRepo(db_session), RunRepo(db_session)


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
def task_with_runs(repos):
    task_repo, run_repo = repos
    task = task_repo.create(name="T", prompt="p")
    r1 = run_repo.create(task_id=task.id, trigger="manual")
    run_repo.complete(r1.id, status="success", stdout="ok", stderr="", exit_code=0)
    r2 = run_repo.create(task_id=task.id, trigger="cron")
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

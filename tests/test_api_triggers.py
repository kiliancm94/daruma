import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.repository import TaskRepo, RunRepo
from app.routers.triggers import router, get_task_repo, get_run_repo, get_runner


@pytest.fixture
def repos(db_conn):
    return TaskRepo(db_conn), RunRepo(db_conn)


@pytest.fixture
def app(repos):
    app = FastAPI()
    app.include_router(router)
    task_repo, run_repo = repos

    mock_runner = MagicMock(return_value={"exit_code": 0, "stdout": "done", "stderr": ""})

    app.dependency_overrides[get_task_repo] = lambda: task_repo
    app.dependency_overrides[get_run_repo] = lambda: run_repo
    app.dependency_overrides[get_runner] = lambda: mock_runner
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_manual_trigger(client, repos):
    task_repo, _ = repos
    task = task_repo.create(name="T", prompt="Run me")
    resp = client.post(f"/api/tasks/{task['id']}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["trigger"] == "manual"


def test_manual_trigger_not_found(client):
    resp = client.post("/api/tasks/nonexistent/run")
    assert resp.status_code == 404


def test_webhook_trigger(client, repos):
    task_repo, _ = repos
    task_repo.create(name="my-webhook", prompt="Webhook prompt")
    resp = client.post("/api/trigger/my-webhook")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trigger"] == "webhook"


def test_webhook_trigger_not_found(client):
    resp = client.post("/api/trigger/no-such-task")
    assert resp.status_code == 404

import time

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crud import tasks as task_crud
from app.crud import runs as run_crud
from app.db import get_db
from app.routers.triggers import router, get_session_factory, get_runner


@pytest.fixture
def app(db_session, session_factory):
    app = FastAPI()
    app.include_router(router)

    mock_runner = MagicMock(
        return_value={"exit_code": 0, "stdout": "done", "stderr": "", "activity": ""}
    )

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_runner] = lambda: mock_runner
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_manual_trigger(client, db_session, session_factory):
    task = task_crud.create(db_session, name="T", prompt="Run me")
    resp = client.post(f"/api/tasks/{task.id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["trigger"] == "manual"
    time.sleep(0.1)
    session = session_factory()
    run = run_crud.get(session, data["id"])
    assert run.status == "success"
    session.close()


def test_manual_trigger_not_found(client):
    resp = client.post("/api/tasks/nonexistent/run")
    assert resp.status_code == 404


def test_webhook_trigger(client, db_session, session_factory):
    task_crud.create(db_session, name="my-webhook", prompt="Webhook prompt")
    resp = client.post("/api/trigger/my-webhook")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["trigger"] == "webhook"
    time.sleep(0.1)
    session = session_factory()
    run = run_crud.get(session, data["id"])
    assert run.status == "success"
    session.close()


def test_webhook_trigger_not_found(client):
    resp = client.post("/api/trigger/no-such-task")
    assert resp.status_code == 404

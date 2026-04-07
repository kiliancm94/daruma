"""Tests for the pipelines and pipeline-triggers API routers."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.routers.pipelines import router as pipelines_router
from app.routers.pipeline_triggers import router as triggers_router


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(pipelines_router)
    app.include_router(triggers_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _create_task(db_session, name="Task A", prompt="Do something"):
    """Create a task directly via CRUD and return its ID."""
    from app.crud import tasks as task_crud

    task = task_crud.create(db_session, name=name, prompt=prompt)
    return task.id


def test_list_pipelines_empty(client):
    resp = client.get("/api/pipelines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_pipeline(client, db_session):
    task_id = _create_task(db_session, "Step 1")
    resp = client.post(
        "/api/pipelines",
        json={"name": "My Pipeline", "steps": [task_id]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Pipeline"
    assert data["id"]
    assert len(data["steps"]) == 1
    assert data["steps"][0]["task_id"] == task_id


def test_create_pipeline_invalid_task_ids(client):
    resp = client.post(
        "/api/pipelines",
        json={"name": "Bad Pipeline", "steps": ["nonexistent-id"]},
    )
    assert resp.status_code == 422


def test_list_pipelines_with_data(client, db_session):
    task_id = _create_task(db_session, "List Task")
    client.post(
        "/api/pipelines",
        json={"name": "Pipeline A", "steps": [task_id]},
    )
    client.post(
        "/api/pipelines",
        json={"name": "Pipeline B", "steps": [task_id]},
    )
    resp = client.get("/api/pipelines")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_pipeline(client, db_session):
    task_id = _create_task(db_session, "Get Task")
    create_resp = client.post(
        "/api/pipelines",
        json={"name": "Get Pipeline", "steps": [task_id]},
    )
    pipeline_id = create_resp.json()["id"]
    resp = client.get(f"/api/pipelines/{pipeline_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Pipeline"


def test_get_pipeline_not_found(client):
    resp = client.get("/api/pipelines/nonexistent")
    assert resp.status_code == 404


def test_update_pipeline(client, db_session):
    task_id = _create_task(db_session, "Update Task")
    create_resp = client.post(
        "/api/pipelines",
        json={"name": "Old Name", "steps": [task_id]},
    )
    pipeline_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/pipelines/{pipeline_id}",
        json={"name": "New Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_delete_pipeline(client, db_session):
    task_id = _create_task(db_session, "Delete Task")
    create_resp = client.post(
        "/api/pipelines",
        json={"name": "Doomed", "steps": [task_id]},
    )
    pipeline_id = create_resp.json()["id"]
    resp = client.delete(f"/api/pipelines/{pipeline_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/pipelines/{pipeline_id}").status_code == 404


def test_trigger_pipeline_run(client, db_session, session_factory):
    """Trigger a pipeline run in the background and verify the run record is returned."""
    task_id = _create_task(db_session, "Trigger Task")
    create_resp = client.post(
        "/api/pipelines",
        json={"name": "Trigger Pipeline", "steps": [task_id]},
    )
    pipeline_id = create_resp.json()["id"]

    from app.routers.pipeline_triggers import get_session_factory, get_runner

    def _mock_session_factory():
        return session_factory

    def _mock_runner():
        def fake_runner(*args, **kwargs):
            return {
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }

        return fake_runner

    client.app.dependency_overrides[get_session_factory] = _mock_session_factory
    client.app.dependency_overrides[get_runner] = _mock_runner

    resp = client.post(f"/api/pipelines/{pipeline_id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_id"] == pipeline_id
    assert data["status"] == "running"
    assert data["id"]

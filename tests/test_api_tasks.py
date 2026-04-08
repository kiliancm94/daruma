import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.routers.tasks import router


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_create_task(client):
    resp = client.post("/api/tasks", json={"name": "Test", "prompt": "Do it"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test"
    assert data["id"]
    assert data["model"] == "sonnet"


def test_create_task_with_model(client):
    resp = client.post(
        "/api/tasks", json={"name": "Opus", "prompt": "Do it", "model": "opus"}
    )
    assert resp.status_code == 201
    assert resp.json()["model"] == "opus"


def test_update_task_model(client):
    create = client.post("/api/tasks", json={"name": "M", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.put(f"/api/tasks/{task_id}", json={"model": "haiku"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "haiku"


def test_list_tasks(client):
    client.post("/api/tasks", json={"name": "A", "prompt": "p"})
    client.post("/api/tasks", json={"name": "B", "prompt": "p"})
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_task(client):
    create = client.post("/api/tasks", json={"name": "X", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "X"


def test_get_task_not_found(client):
    resp = client.get("/api/tasks/nonexistent")
    assert resp.status_code == 404


def test_update_task(client):
    create = client.post("/api/tasks", json={"name": "Old", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.put(f"/api/tasks/{task_id}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_create_task_with_env_vars(client):
    resp = client.post(
        "/api/tasks",
        json={"name": "EnvAPI", "prompt": "p", "env_vars": {"SECRET": "val"}},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["env_vars"] == {"SECRET": "val"}


def test_delete_task(client):
    create = client.post("/api/tasks", json={"name": "Gone", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404

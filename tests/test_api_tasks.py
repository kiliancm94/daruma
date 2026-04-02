import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.repository import TaskRepo
from app.services import TaskService
from app.routers.tasks import router, get_task_service


@pytest.fixture
def app(db_conn):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_task_service] = lambda: TaskService(TaskRepo(db_conn))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_create_task(client):
    resp = client.post("/api/tasks", json={
        "name": "Test", "prompt": "Do it"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test"
    assert data["id"]


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


def test_delete_task(client):
    create = client.post("/api/tasks", json={"name": "Gone", "prompt": "p"})
    task_id = create.json()["id"]
    resp = client.delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404

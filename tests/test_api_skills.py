import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.routers.skills import router


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_create_skill(client):
    resp = client.post("/api/skills", json={
        "name": "test", "description": "A test", "content": "# Test"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test"
    assert data["source"] == "local"


def test_list_skills(client):
    client.post("/api/skills", json={"name": "a", "content": "c"})
    client.post("/api/skills", json={"name": "b", "content": "c"})
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_skill(client):
    create = client.post("/api/skills", json={"name": "x", "content": "c"})
    skill_id = create.json()["id"]
    resp = client.get(f"/api/skills/{skill_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "x"


def test_get_skill_not_found(client):
    resp = client.get("/api/skills/nonexistent")
    assert resp.status_code == 404


def test_update_skill(client):
    create = client.post("/api/skills", json={"name": "y", "content": "old"})
    skill_id = create.json()["id"]
    resp = client.put(f"/api/skills/{skill_id}", json={"content": "new"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "new"


def test_delete_skill(client):
    create = client.post("/api/skills", json={"name": "z", "content": "c"})
    skill_id = create.json()["id"]
    resp = client.delete(f"/api/skills/{skill_id}")
    assert resp.status_code == 204


def test_assign_skills_to_task(client, db_session):
    from app.crud import tasks as task_crud
    task = task_crud.create(db_session, name="T", prompt="p")
    create = client.post("/api/skills", json={"name": "s", "content": "c"})
    skill_id = create.json()["id"]
    resp = client.put(f"/api/tasks/{task.id}/skills", json={"skill_ids": [skill_id]})
    assert resp.status_code == 200

    resp = client.get(f"/api/tasks/{task.id}/skills")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "s"

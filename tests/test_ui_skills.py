"""Tests for the skills UI routes — verifies global skills are clickable."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.routers import ui as ui_router
from app.crud import skills as skill_crud
from app.schemas.skill import SkillSource


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(ui_router.router)
    return app


@pytest.fixture
def client(app, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_skills_list_shows_all_skills_as_links(client, db_session):
    """Both local and global skills should be clickable in the list."""
    skill_crud.create(
        db_session, name="local-skill", content="# Local", source=SkillSource.local
    )
    global_skill = skill_crud.create(
        db_session, name="global-skill", content="# Global", source=SkillSource.global_
    )

    resp = client.get("/ui/skills/")
    assert resp.status_code == 200
    html = resp.text
    assert f"/ui/skills/{global_skill.id}" in html
    assert "local-skill" in html
    assert "global-skill" in html


def test_skill_detail_works_for_global_skill(client, db_session):
    """Global skills should be viewable via their detail page."""
    skill = skill_crud.create(
        db_session,
        name="my-global",
        content="# Content here",
        source=SkillSource.global_,
    )
    resp = client.get(f"/ui/skills/{skill.id}")
    assert resp.status_code == 200
    assert "my-global" in resp.text
    assert "# Content here" in resp.text

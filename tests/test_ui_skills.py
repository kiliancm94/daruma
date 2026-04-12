"""Tests for the skills UI routes — verifies skills are clickable by name."""

import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.routers import ui as ui_router
from app.crud import skills as skill_crud


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(ui_router.router)
    return app


@pytest.fixture
def client(app, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_skills_list_shows_all_skills_as_links(client, db_session, tmp_path):
    """Both local and global skills should be clickable in the list."""
    skill_crud.create(db_session, name="local-skill", content="# Local")

    # Create a global skill on the filesystem
    global_dir = tmp_path / "skills" / "global-skill"
    global_dir.mkdir(parents=True)
    (global_dir / "SKILL.md").write_text(
        "---\nname: global-skill\ndescription: A global\n---\n# Global"
    )
    with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
        resp = client.get("/ui/skills/")
    assert resp.status_code == 200
    html = resp.text
    assert "/ui/skills/local-skill" in html
    assert "/ui/skills/global-skill" in html
    assert "local-skill" in html
    assert "global-skill" in html


def test_skill_detail_works_for_local_skill(client, db_session):
    """Local skills should be viewable via their detail page by name."""
    skill_crud.create(db_session, name="my-local", content="# Content here")
    resp = client.get("/ui/skills/my-local")
    assert resp.status_code == 200
    assert "my-local" in resp.text
    assert "# Content here" in resp.text

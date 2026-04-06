import pytest

from app.crud import skills as skill_crud
from app.crud.exceptions import NotFoundError


class TestSkillCrud:
    def test_create_and_get(self, db_session):
        skill = skill_crud.create(
            db_session,
            name="jira",
            description="Interact with Jira",
            content="# Jira Skill\n\nUse jira CLI.",
        )
        assert skill.name == "jira"
        assert skill.source == "local"

        fetched = skill_crud.get(db_session, skill.id)
        assert fetched is not None
        assert fetched.id == skill.id

    def test_get_by_name(self, db_session):
        skill_crud.create(db_session, name="sentry", description="d", content="c")
        found = skill_crud.get_by_name(db_session, "sentry")
        assert found is not None
        assert found.name == "sentry"

    def test_list_skills(self, db_session):
        skill_crud.create(db_session, name="a", description="d", content="c")
        skill_crud.create(db_session, name="b", description="d", content="c")
        assert len(skill_crud.get_all(db_session)) == 2

    def test_update_skill(self, db_session):
        skill = skill_crud.create(db_session, name="old", description="d", content="c")
        updated = skill_crud.update(db_session, skill.id, description="new desc")
        assert updated.description == "new desc"

    def test_delete_skill(self, db_session):
        skill = skill_crud.create(db_session, name="doomed", description="d", content="c")
        skill_crud.delete(db_session, skill.id)
        assert skill_crud.get(db_session, skill.id) is None

    def test_delete_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            skill_crud.delete(db_session, "nonexistent")

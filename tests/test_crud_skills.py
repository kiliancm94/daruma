import pytest

from app.crud import skills as skill_crud
from app.crud import task_skills as task_skill_crud
from app.crud import tasks as task_crud
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
        skill = skill_crud.create(
            db_session, name="doomed", description="d", content="c"
        )
        skill_crud.delete(db_session, skill.id)
        assert skill_crud.get(db_session, skill.id) is None

    def test_delete_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            skill_crud.delete(db_session, "nonexistent")


class TestTaskSkillCrud:
    def test_assign_and_list(self, db_session):
        task = task_crud.create(db_session, name="T", prompt="p")
        task_skill_crud.assign(db_session, task.id, "my-skill")
        names = task_skill_crud.list_for_task(db_session, task.id)
        assert len(names) == 1
        assert names[0] == "my-skill"

    def test_assign_idempotent(self, db_session):
        task = task_crud.create(db_session, name="T", prompt="p")
        task_skill_crud.assign(db_session, task.id, "s")
        task_skill_crud.assign(db_session, task.id, "s")
        assert len(task_skill_crud.list_for_task(db_session, task.id)) == 1

    def test_unassign(self, db_session):
        task = task_crud.create(db_session, name="T", prompt="p")
        task_skill_crud.assign(db_session, task.id, "s")
        task_skill_crud.unassign(db_session, task.id, "s")
        assert len(task_skill_crud.list_for_task(db_session, task.id)) == 0

    def test_replace(self, db_session):
        task = task_crud.create(db_session, name="T", prompt="p")
        task_skill_crud.assign(db_session, task.id, "a")
        task_skill_crud.replace(db_session, task.id, ["b"])
        names = task_skill_crud.list_for_task(db_session, task.id)
        assert len(names) == 1
        assert names[0] == "b"

import time
from unittest.mock import MagicMock

import pytest

from app.crud import runs as run_crud
from app.services import (
    TaskService,
    RunService,
    TaskNotFoundError,
    RunNotFoundError,
    execute_task,
    execute_task_background,
)


@pytest.fixture
def task_svc(db_session):
    return TaskService(db_session)


@pytest.fixture
def run_svc(db_session):
    return RunService(db_session)


class TestTaskService:
    def test_create(self, task_svc):
        task = task_svc.create(name="Test", prompt="Do it")
        assert task.name == "Test"
        assert task.id

    def test_list(self, task_svc):
        task_svc.create(name="A", prompt="p")
        task_svc.create(name="B", prompt="p")
        assert len(task_svc.list()) == 2

    def test_get(self, task_svc):
        task = task_svc.create(name="X", prompt="p")
        assert task_svc.get(task.id).name == "X"

    def test_get_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.get("nonexistent")

    def test_get_by_name(self, task_svc):
        task_svc.create(name="Named", prompt="p")
        assert task_svc.get_by_name("Named").name == "Named"

    def test_get_by_name_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.get_by_name("nope")

    def test_update(self, task_svc):
        task = task_svc.create(name="Old", prompt="p")
        updated = task_svc.update(task.id, name="New")
        assert updated.name == "New"

    def test_update_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.update("nonexistent", name="X")

    def test_delete(self, task_svc):
        task = task_svc.create(name="Gone", prompt="p")
        task_svc.delete(task.id)
        with pytest.raises(TaskNotFoundError):
            task_svc.get(task.id)

    def test_delete_not_found(self, task_svc):
        with pytest.raises(TaskNotFoundError):
            task_svc.delete("nonexistent")


class TestRunService:
    def test_list(self, task_svc, run_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        run_crud.create(db_session, task_id=task.id, trigger="manual")
        assert len(run_svc.list()) == 1
        assert len(run_svc.list(task_id=task.id)) == 1

    def test_get(self, task_svc, run_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        run = run_crud.create(db_session, task_id=task.id, trigger="manual")
        assert run_svc.get(run.id).trigger == "manual"

    def test_get_not_found(self, run_svc):
        with pytest.raises(RunNotFoundError):
            run_svc.get("nonexistent")


class TestExecuteTask:
    def test_success(self, task_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        result = execute_task(task, db_session, runner=mock_runner)
        assert result.status == "success"
        assert result.exit_code == 0

    def test_failure(self, task_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={"exit_code": 1, "stdout": "", "stderr": "err", "activity": ""}
        )
        result = execute_task(task, db_session, runner=mock_runner)
        assert result.status == "failed"
        assert result.exit_code == 1

    def test_exception(self, task_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(side_effect=RuntimeError("boom"))
        result = execute_task(task, db_session, runner=mock_runner)
        assert result.status == "failed"
        assert result.exit_code == -1
        assert "boom" in result.stderr

    def test_on_output_callback(self, task_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        output_calls = []
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )

        def capture(stdout: str, activity: str) -> None:
            output_calls.append((stdout, activity))

        execute_task(task, db_session, runner=mock_runner, on_output=capture)
        mock_runner.assert_called_once()

    def test_skills_injected(self, task_svc, db_session):
        from app.crud import skills as skill_crud
        from app.crud import task_skills as task_skill_crud

        task = task_svc.create(name="T", prompt="p")
        skill = skill_crud.create(db_session, name="jira", description="d", content="# Jira\nUse jira CLI")
        task_skill_crud.assign(db_session, task.id, skill.id)

        mock_runner = MagicMock(
            return_value={"exit_code": 0, "stdout": "done", "stderr": "", "activity": ""}
        )
        execute_task(task, db_session, runner=mock_runner)
        call_kwargs = mock_runner.call_args
        assert "system_prompt" in call_kwargs.kwargs or (len(call_kwargs.args) > 3)
        # Check system_prompt was passed
        if call_kwargs.kwargs.get("system_prompt"):
            assert "Jira" in call_kwargs.kwargs["system_prompt"]


class TestExecuteTaskBg:
    def test_returns_running(self, task_svc, session_factory):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        run = execute_task_background(task, session_factory, runner=mock_runner)
        assert run.status == "running"
        time.sleep(0.1)
        session = session_factory()
        completed = run_crud.get(session, run.id)
        assert completed.status == "success"
        session.close()


from unittest.mock import patch
from app.services import SkillService, SkillNotFoundError


class TestSkillService:
    def test_create(self, db_session):
        svc = SkillService(db_session)
        skill = svc.create(name="test", description="d", content="c")
        assert skill.name == "test"
        assert skill.source == "local"

    def test_list_local(self, db_session):
        svc = SkillService(db_session)
        svc.create(name="a", description="d", content="c")
        assert len(svc.list_local()) == 1

    def test_get(self, db_session):
        svc = SkillService(db_session)
        skill = svc.create(name="x", description="d", content="c")
        assert svc.get(skill.id).name == "x"

    def test_get_not_found(self, db_session):
        svc = SkillService(db_session)
        with pytest.raises(SkillNotFoundError):
            svc.get("nonexistent")

    def test_update(self, db_session):
        svc = SkillService(db_session)
        skill = svc.create(name="old", description="d", content="c")
        updated = svc.update(skill.id, description="new")
        assert updated.description == "new"

    def test_delete(self, db_session):
        svc = SkillService(db_session)
        skill = svc.create(name="gone", description="d", content="c")
        svc.delete(skill.id)
        with pytest.raises(SkillNotFoundError):
            svc.get(skill.id)

    def test_list_global(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A skill\n---\n# Content"
        )
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            skills = svc.list_global()
        assert len(skills) == 1
        assert skills[0]["name"] == "my-skill"
        assert skills[0]["description"] == "A skill"
        assert skills[0]["source"] == "global"

    def test_list_global_case_insensitive(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "other"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text("---\nname: other\ndescription: d\n---\n# Body")
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            skills = svc.list_global()
        assert len(skills) == 1

    def test_list_all_merges(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "ext"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: ext\ndescription: External\n---\n# Ext")
        svc = SkillService(db_session)
        svc.create(name="local", description="d", content="c")
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            all_skills = svc.list_all()
        assert len(all_skills) == 2

    def test_list_global_no_dir(self, tmp_path, db_session):
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "nonexistent"):
            assert svc.list_global() == []

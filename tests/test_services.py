import time
from unittest.mock import MagicMock, patch

import pytest

from app.crud import runs as run_crud
from app.crud import pipeline_runs as pipeline_run_crud
from app.services import (
    TaskService,
    RunService,
    SkillService,
    SkillNotFoundError,
    TaskNotFoundError,
    RunNotFoundError,
    PipelineService,
    PipelineNotFoundError,
    PipelineRunService,
    PipelineRunNotFoundError,
    execute_task,
    execute_task_background,
    execute_pipeline,
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

    def test_delete_task_in_pipeline_raises(self, task_svc, db_session):
        from app.crud import pipelines as pipeline_crud

        task = task_svc.create(name="Guarded", prompt="p")
        pipeline_crud.create(db_session, name="My Pipeline", task_ids=[task.id])
        with pytest.raises(ValueError, match="My Pipeline"):
            task_svc.delete(task.id)


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

    def test_env_vars_passed_to_runner(self, task_svc, db_session):
        task = task_svc.create(name="T", prompt="p", env_vars={"MY_SECRET": "abc123"})
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        execute_task(task, db_session, runner=mock_runner)
        call_kwargs = mock_runner.call_args.kwargs
        assert call_kwargs["env_vars"] == {"MY_SECRET": "abc123"}

    def test_no_env_vars_passes_none(self, task_svc, db_session):
        task = task_svc.create(name="T", prompt="p")
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        execute_task(task, db_session, runner=mock_runner)
        call_kwargs = mock_runner.call_args.kwargs
        assert call_kwargs.get("env_vars") is None

    def test_skills_injected(self, task_svc, db_session):
        from app.crud import skills as skill_crud
        from app.crud import task_skills as task_skill_crud

        task = task_svc.create(name="T", prompt="p")
        # Create a local skill in DB
        skill_crud.create(
            db_session, name="jira", description="d", content="# Jira\nUse jira CLI"
        )
        # Assign by name
        task_skill_crud.assign(db_session, task.id, "jira")

        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )
        execute_task(task, db_session, runner=mock_runner)
        call_kwargs = mock_runner.call_args
        assert "system_prompt" in call_kwargs.kwargs or (len(call_kwargs.args) > 3)
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


class TestSkillService:
    def test_create_local(self, db_session):
        svc = SkillService(db_session)
        result = svc.create(name="test", description="d", content="c")
        assert result["name"] == "test"
        assert result["source"] == "local"

    def test_create_global(self, tmp_path, db_session):
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            (tmp_path / "skills").mkdir()
            result = svc.create(name="g", description="d", content="c", source="global")
        assert result["name"] == "g"
        assert result["source"] == "global"
        assert (tmp_path / "skills" / "g" / "SKILL.md").exists()

    def test_create_name_collision_global_exists(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "taken"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: taken\ndescription: d\n---\nc")
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            with pytest.raises(ValueError, match="already taken"):
                svc.create(name="taken", description="d", content="c")

    def test_create_name_collision_local_exists(self, tmp_path, db_session):
        svc = SkillService(db_session)
        svc.create(name="taken", description="d", content="c")
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            (tmp_path / "skills").mkdir()
            with pytest.raises(ValueError, match="already taken"):
                svc.create(name="taken", description="d", content="c", source="global")

    def test_resolve_global_first(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "s"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: s\ndescription: Global\n---\n# Global"
        )
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            result = svc.resolve("s")
        assert result["source"] == "global"

    def test_resolve_falls_back_to_local(self, db_session):
        svc = SkillService(db_session)
        svc.create(name="loc", description="d", content="c")
        result = svc.resolve("loc")
        assert result["source"] == "local"

    def test_resolve_not_found(self, db_session):
        svc = SkillService(db_session)
        with pytest.raises(SkillNotFoundError):
            svc.resolve("nonexistent")

    def test_list_local(self, db_session):
        svc = SkillService(db_session)
        svc.create(name="a", description="d", content="c")
        result = svc.list_local()
        assert len(result) == 1
        assert result[0]["source"] == "local"

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
        assert skills[0]["source"] == "global"

    def test_list_global_case_insensitive(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "other"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text(
            "---\nname: other\ndescription: d\n---\n# Body"
        )
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            skills = svc.list_global()
        assert len(skills) == 1

    def test_list_all_merged(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "ext"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: ext\ndescription: External\n---\n# Ext"
        )
        svc = SkillService(db_session)
        svc.create(name="local", description="d", content="c")
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            all_skills = svc.list_all()
        assert len(all_skills) == 2
        # Sorted by name
        assert all_skills[0]["name"] == "ext"
        assert all_skills[1]["name"] == "local"

    def test_update_local(self, db_session):
        svc = SkillService(db_session)
        svc.create(name="old", description="d", content="c")
        updated = svc.update("old", description="new")
        assert updated["description"] == "new"

    def test_update_global(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "g"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: g\ndescription: old\n---\n# Old"
        )
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            updated = svc.update("g", description="new")
        assert updated["description"] == "new"

    def test_delete_local(self, db_session):
        svc = SkillService(db_session)
        svc.create(name="gone", description="d", content="c")
        svc.delete("gone")
        with pytest.raises(SkillNotFoundError):
            svc.resolve("gone")

    def test_delete_global(self, tmp_path, db_session):
        skill_dir = tmp_path / "skills" / "g"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: g\ndescription: d\n---\nc")
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "skills"):
            svc.delete("g")
        assert not skill_dir.exists()

    def test_list_global_no_dir(self, tmp_path, db_session):
        svc = SkillService(db_session)
        with patch("app.services.GLOBAL_SKILLS_DIR", tmp_path / "nonexistent"):
            assert svc.list_global() == []


@pytest.fixture
def pipeline_svc(db_session):
    return PipelineService(db_session)


@pytest.fixture
def pipeline_run_svc(db_session):
    return PipelineRunService(db_session)


def _make_tasks(task_svc, count=2):
    """Helper to create N tasks and return them as a list."""
    return [
        task_svc.create(name=f"task-{i}", prompt=f"prompt-{i}") for i in range(count)
    ]


def _mock_runner(stdout="done", exit_code=0):
    """Build a MagicMock runner that returns the given stdout/exit_code."""
    return MagicMock(
        return_value={
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
            "activity": "",
        }
    )


class TestPipelineService:
    def test_create(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc)
        pipeline = pipeline_svc.create(
            name="p1", description="desc", task_ids=[t.id for t in tasks]
        )
        assert pipeline.name == "p1"
        assert pipeline.description == "desc"
        assert len(pipeline.steps) == 2

    def test_list(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=1)
        pipeline_svc.create(name="a", task_ids=[tasks[0].id])
        pipeline_svc.create(name="b", task_ids=[tasks[0].id])
        assert len(pipeline_svc.list()) == 2

    def test_get(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="g", task_ids=[tasks[0].id])
        assert pipeline_svc.get(pipeline.id).name == "g"

    def test_get_not_found(self, pipeline_svc):
        with pytest.raises(PipelineNotFoundError):
            pipeline_svc.get("nonexistent")

    def test_get_by_name(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=1)
        pipeline_svc.create(name="named", task_ids=[tasks[0].id])
        assert pipeline_svc.get_by_name("named").name == "named"

    def test_get_by_name_not_found(self, pipeline_svc):
        with pytest.raises(PipelineNotFoundError):
            pipeline_svc.get_by_name("nope")

    def test_update(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="old", task_ids=[tasks[0].id])
        updated = pipeline_svc.update(pipeline.id, name="new")
        assert updated.name == "new"

    def test_update_not_found(self, pipeline_svc):
        with pytest.raises(PipelineNotFoundError):
            pipeline_svc.update("nonexistent", name="X")

    def test_delete(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="gone", task_ids=[tasks[0].id])
        pipeline_svc.delete(pipeline.id)
        with pytest.raises(PipelineNotFoundError):
            pipeline_svc.get(pipeline.id)

    def test_delete_not_found(self, pipeline_svc):
        with pytest.raises(PipelineNotFoundError):
            pipeline_svc.delete("nonexistent")

    def test_update_steps(self, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=3)
        pipeline = pipeline_svc.create(name="s", task_ids=[tasks[0].id])
        pipeline_svc.update_steps(pipeline.id, [tasks[1].id, tasks[2].id])
        refreshed = pipeline_svc.get(pipeline.id)
        assert len(refreshed.steps) == 2
        assert refreshed.steps[0].task_id == tasks[1].id
        assert refreshed.steps[1].task_id == tasks[2].id


class TestPipelineRunService:
    def test_list(self, pipeline_run_svc, pipeline_svc, task_svc, db_session):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="p", task_ids=[tasks[0].id])
        pipeline_run_crud.create(db_session, pipeline_id=pipeline.id, trigger="manual")
        assert len(pipeline_run_svc.list()) == 1
        assert len(pipeline_run_svc.list(pipeline_id=pipeline.id)) == 1

    def test_get(self, pipeline_run_svc, pipeline_svc, task_svc, db_session):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="p", task_ids=[tasks[0].id])
        pr = pipeline_run_crud.create(
            db_session, pipeline_id=pipeline.id, trigger="manual"
        )
        assert pipeline_run_svc.get(pr.id).trigger == "manual"

    def test_get_not_found(self, pipeline_run_svc):
        with pytest.raises(PipelineRunNotFoundError):
            pipeline_run_svc.get("nonexistent")

    def test_last_run(self, pipeline_run_svc, pipeline_svc, task_svc, db_session):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="p", task_ids=[tasks[0].id])
        pipeline_run_crud.create(db_session, pipeline_id=pipeline.id, trigger="manual")
        pr2 = pipeline_run_crud.create(
            db_session, pipeline_id=pipeline.id, trigger="cron"
        )
        last = pipeline_run_svc.last_run(pipeline.id)
        assert last is not None
        assert last.id == pr2.id

    def test_last_run_none(self, pipeline_run_svc, pipeline_svc, task_svc):
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="p", task_ids=[tasks[0].id])
        assert pipeline_run_svc.last_run(pipeline.id) is None


class TestExecutePipeline:
    def test_single_step_pipeline(self, task_svc, pipeline_svc, db_session):
        """One task, mock runner, verify pipeline run succeeds."""
        tasks = _make_tasks(task_svc, count=1)
        pipeline = pipeline_svc.create(name="single", task_ids=[tasks[0].id])
        runner = _mock_runner(stdout="step0 output")

        pr = execute_pipeline(pipeline, db_session, runner=runner)

        assert pr.status == "success"
        assert pr.finished_at is not None
        runner.assert_called_once()
        # Prompt should be the original task prompt (step 0 — no prefix)
        call_args = runner.call_args
        assert call_args[0][0] == tasks[0].prompt

    def test_multi_step_output_chaining(self, task_svc, pipeline_svc, db_session):
        """Two tasks — second runner receives prepended output from first."""
        tasks = _make_tasks(task_svc, count=2)
        call_count = 0

        def chained_runner(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "exit_code": 0,
                    "stdout": "first output",
                    "stderr": "",
                    "activity": "",
                }
            return {
                "exit_code": 0,
                "stdout": "second output",
                "stderr": "",
                "activity": "",
            }

        pipeline = pipeline_svc.create(name="chain", task_ids=[t.id for t in tasks])
        pr = execute_pipeline(pipeline, db_session, runner=chained_runner)

        assert pr.status == "success"
        assert call_count == 2

    def test_multi_step_prompt_format(self, task_svc, pipeline_svc, db_session):
        """Verify the second step prompt is formatted with previous output."""
        tasks = _make_tasks(task_svc, count=2)
        prompts_seen = []

        def capturing_runner(prompt, **kwargs):
            prompts_seen.append(prompt)
            return {
                "exit_code": 0,
                "stdout": "output-from-step-0",
                "stderr": "",
                "activity": "",
            }

        pipeline = pipeline_svc.create(name="fmt", task_ids=[t.id for t in tasks])
        execute_pipeline(pipeline, db_session, runner=capturing_runner)

        # First step: original prompt
        assert prompts_seen[0] == tasks[0].prompt
        # Second step: prepended with previous output
        assert "output-from-step-0" in prompts_seen[1]
        assert tasks[1].prompt in prompts_seen[1]

    def test_pipeline_step_failure(self, task_svc, pipeline_svc, db_session):
        """First step fails — pipeline_run status=failed, second step never runs."""
        tasks = _make_tasks(task_svc, count=2)
        runner = _mock_runner(stdout="", exit_code=1)

        pipeline = pipeline_svc.create(name="fail", task_ids=[t.id for t in tasks])
        pr = execute_pipeline(pipeline, db_session, runner=runner)

        assert pr.status == "failed"
        # Runner called only once (second step skipped)
        runner.assert_called_once()

    def test_pipeline_run_records(self, task_svc, pipeline_svc, db_session):
        """Verify each step creates a Run with pipeline_run_id set."""
        tasks = _make_tasks(task_svc, count=2)
        runner = _mock_runner(stdout="ok")

        pipeline = pipeline_svc.create(name="records", task_ids=[t.id for t in tasks])
        pr = execute_pipeline(pipeline, db_session, runner=runner)

        # Should have 2 Run records linked to this pipeline run
        step_runs = (
            db_session.query(run_crud.Run)
            .filter(run_crud.Run.pipeline_run_id == pr.id)
            .all()
        )
        assert len(step_runs) == 2
        for sr in step_runs:
            assert sr.pipeline_run_id == pr.id

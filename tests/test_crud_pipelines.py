"""Tests for pipeline and pipeline run CRUD operations."""

import pytest

from app.crud import tasks as task_crud
from app.crud import pipelines as pipeline_crud
from app.crud import pipeline_runs as pipeline_run_crud
from app.crud.exceptions import NotFoundError


def _make_task(db_session, name="T", prompt="p"):
    return task_crud.create(db_session, name=name, prompt=prompt)


class TestPipelineCrud:
    def test_create_with_valid_task_ids(self, db_session):
        t1 = _make_task(db_session, name="Task1")
        t2 = _make_task(db_session, name="Task2")
        pipeline = pipeline_crud.create(
            db_session,
            name="My Pipeline",
            description="A test pipeline",
            task_ids=[t1.id, t2.id],
        )
        assert pipeline.name == "My Pipeline"
        assert pipeline.description == "A test pipeline"
        assert pipeline.enabled is True
        assert len(pipeline.steps) == 2
        assert pipeline.steps[0].task_id == t1.id
        assert pipeline.steps[0].step_order == 0
        assert pipeline.steps[1].task_id == t2.id
        assert pipeline.steps[1].step_order == 1

    def test_create_with_invalid_task_id_raises(self, db_session):
        _make_task(db_session, name="Valid")
        with pytest.raises(ValueError, match="Invalid task IDs"):
            pipeline_crud.create(
                db_session,
                name="Bad Pipeline",
                task_ids=["nonexistent-id"],
            )

    def test_create_with_empty_task_list_raises(self, db_session):
        with pytest.raises(ValueError, match="at least one"):
            pipeline_crud.create(
                db_session,
                name="Empty Pipeline",
                task_ids=[],
            )

    def test_create_disabled(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(
            db_session,
            name="Disabled",
            task_ids=[t.id],
            enabled=False,
        )
        assert pipeline.enabled is False

    def test_get(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="P", task_ids=[t.id])
        fetched = pipeline_crud.get(db_session, pipeline.id)
        assert fetched is not None
        assert fetched.id == pipeline.id

    def test_get_nonexistent_returns_none(self, db_session):
        assert pipeline_crud.get(db_session, "nonexistent") is None

    def test_get_by_name(self, db_session):
        t = _make_task(db_session)
        pipeline_crud.create(db_session, name="FindMe", task_ids=[t.id])
        found = pipeline_crud.get_by_name(db_session, "FindMe")
        assert found is not None
        assert found.name == "FindMe"

    def test_get_by_name_nonexistent_returns_none(self, db_session):
        assert pipeline_crud.get_by_name(db_session, "nope") is None

    def test_get_all(self, db_session):
        t = _make_task(db_session)
        pipeline_crud.create(db_session, name="P1", task_ids=[t.id])
        pipeline_crud.create(db_session, name="P2", task_ids=[t.id])
        pipelines = pipeline_crud.get_all(db_session)
        assert len(pipelines) == 2
        # Ordered by created_at desc — most recent first
        assert pipelines[0].name == "P2"
        assert pipelines[1].name == "P1"

    def test_update_name_and_description(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="Old", task_ids=[t.id])
        updated = pipeline_crud.update(
            db_session, pipeline.id, name="New", description="Updated desc"
        )
        assert updated.name == "New"
        assert updated.description == "Updated desc"

    def test_update_enabled(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="P", task_ids=[t.id])
        updated = pipeline_crud.update(db_session, pipeline.id, enabled=False)
        assert updated.enabled is False

    def test_update_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            pipeline_crud.update(db_session, "nonexistent", name="X")

    def test_update_no_fields_returns_unchanged(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="P", task_ids=[t.id])
        updated = pipeline_crud.update(db_session, pipeline.id)
        assert updated.name == "P"

    def test_update_steps_replaces_steps(self, db_session):
        t1 = _make_task(db_session, name="A")
        t2 = _make_task(db_session, name="B")
        t3 = _make_task(db_session, name="C")
        pipeline = pipeline_crud.create(db_session, name="P", task_ids=[t1.id, t2.id])
        assert len(pipeline.steps) == 2

        pipeline_crud.update_steps(db_session, pipeline.id, [t3.id, t1.id])
        refreshed = pipeline_crud.get(db_session, pipeline.id)
        assert len(refreshed.steps) == 2
        assert refreshed.steps[0].task_id == t3.id
        assert refreshed.steps[0].step_order == 0
        assert refreshed.steps[1].task_id == t1.id
        assert refreshed.steps[1].step_order == 1

    def test_update_steps_nonexistent_pipeline_raises(self, db_session):
        with pytest.raises(NotFoundError):
            pipeline_crud.update_steps(db_session, "nonexistent", ["some-id"])

    def test_update_steps_invalid_task_id_raises(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="P", task_ids=[t.id])
        with pytest.raises(ValueError, match="Invalid task IDs"):
            pipeline_crud.update_steps(db_session, pipeline.id, ["bad-id"])

    def test_delete(self, db_session):
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="Doomed", task_ids=[t.id])
        pipeline_id = pipeline.id
        pipeline_crud.delete(db_session, pipeline_id)
        assert pipeline_crud.get(db_session, pipeline_id) is None

    def test_delete_cascades_steps(self, db_session):
        """Deleting a pipeline also removes its steps."""
        t = _make_task(db_session)
        pipeline = pipeline_crud.create(db_session, name="P", task_ids=[t.id])
        step_id = pipeline.steps[0].id
        pipeline_crud.delete(db_session, pipeline.id)
        # Step should be gone (cascade delete-orphan)
        from app.models.pipeline import PipelineStep

        assert db_session.get(PipelineStep, step_id) is None

    def test_delete_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            pipeline_crud.delete(db_session, "nonexistent")


class TestPipelineRunCrud:
    def _make_pipeline(self, db_session):
        t = _make_task(db_session, name=f"T-{id(db_session)}")
        return pipeline_crud.create(
            db_session, name=f"P-{id(db_session)}", task_ids=[t.id]
        )

    def test_create_run(self, db_session):
        pipeline = self._make_pipeline(db_session)
        run = pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        assert run.pipeline_id == pipeline.id
        assert run.status == "running"
        assert run.trigger == "manual"
        assert run.started_at is not None

    def test_create_run_with_trigger(self, db_session):
        pipeline = self._make_pipeline(db_session)
        run = pipeline_run_crud.create(
            db_session, pipeline_id=pipeline.id, trigger="cron"
        )
        assert run.trigger == "cron"

    def test_update_step(self, db_session):
        pipeline = self._make_pipeline(db_session)
        run = pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        pipeline_run_crud.update_step(db_session, run.id, current_step=1)
        fetched = pipeline_run_crud.get(db_session, run.id)
        assert fetched.current_step == 1

    def test_update_step_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            pipeline_run_crud.update_step(db_session, "nonexistent", current_step=0)

    def test_complete_run(self, db_session):
        pipeline = self._make_pipeline(db_session)
        run = pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        completed = pipeline_run_crud.complete(db_session, run.id, status="success")
        assert completed.status == "success"
        assert completed.finished_at is not None
        assert completed.duration_ms is not None
        assert completed.duration_ms >= 0

    def test_complete_run_with_explicit_values(self, db_session):
        pipeline = self._make_pipeline(db_session)
        run = pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        completed = pipeline_run_crud.complete(
            db_session,
            run.id,
            status="failed",
            finished_at="2026-01-01T00:00:00+00:00",
            duration_ms=1234,
        )
        assert completed.status == "failed"
        assert completed.finished_at == "2026-01-01T00:00:00+00:00"
        assert completed.duration_ms == 1234

    def test_complete_nonexistent_raises(self, db_session):
        with pytest.raises(NotFoundError):
            pipeline_run_crud.complete(db_session, "nonexistent", status="success")

    def test_get(self, db_session):
        pipeline = self._make_pipeline(db_session)
        run = pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        fetched = pipeline_run_crud.get(db_session, run.id)
        assert fetched is not None
        assert fetched.id == run.id

    def test_get_nonexistent_returns_none(self, db_session):
        assert pipeline_run_crud.get(db_session, "nonexistent") is None

    def test_get_all(self, db_session):
        pipeline = self._make_pipeline(db_session)
        pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        runs = pipeline_run_crud.get_all(db_session)
        assert len(runs) >= 2

    def test_get_all_filtered_by_pipeline(self, db_session):
        t1 = _make_task(db_session, name="Ft1")
        t2 = _make_task(db_session, name="Ft2")
        p1 = pipeline_crud.create(db_session, name="Fp1", task_ids=[t1.id])
        p2 = pipeline_crud.create(db_session, name="Fp2", task_ids=[t2.id])
        pipeline_run_crud.create(db_session, pipeline_id=p1.id)
        pipeline_run_crud.create(db_session, pipeline_id=p1.id)
        pipeline_run_crud.create(db_session, pipeline_id=p2.id)
        runs_p1 = pipeline_run_crud.get_all(db_session, pipeline_id=p1.id)
        assert len(runs_p1) == 2
        runs_p2 = pipeline_run_crud.get_all(db_session, pipeline_id=p2.id)
        assert len(runs_p2) == 1

    def test_get_last(self, db_session):
        pipeline = self._make_pipeline(db_session)
        pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        run2 = pipeline_run_crud.create(db_session, pipeline_id=pipeline.id)
        last = pipeline_run_crud.get_last(db_session, pipeline.id)
        assert last is not None
        assert last.id == run2.id

    def test_get_last_no_runs_returns_none(self, db_session):
        pipeline = self._make_pipeline(db_session)
        assert pipeline_run_crud.get_last(db_session, pipeline.id) is None

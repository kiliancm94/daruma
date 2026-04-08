"""End-to-end integration tests for pipeline execution."""

from unittest.mock import MagicMock

from app.crud import tasks as task_crud
from app.crud import pipelines as pipeline_crud
from app.models.run import Run
from app.services import execute_pipeline


class TestPipelineIntegration:
    def test_pipeline_success_chains_output(self, db_session):
        """Two tasks — second receives first's stdout prepended to its prompt."""
        task_a = task_crud.create(db_session, name="task_a", prompt="Fetch data")
        task_b = task_crud.create(db_session, name="task_b", prompt="Summarize this")
        pipeline = pipeline_crud.create(
            db_session, name="chain", task_ids=[task_a.id, task_b.id]
        )

        mock_runner = MagicMock(
            side_effect=[
                {
                    "exit_code": 0,
                    "stdout": "calendar events data",
                    "stderr": "",
                    "activity": "",
                },
                {
                    "exit_code": 0,
                    "stdout": "summary",
                    "stderr": "",
                    "activity": "",
                },
            ]
        )

        pr = execute_pipeline(pipeline, db_session, runner=mock_runner)

        assert pr.status == "success"

        # Two Run records should exist with pipeline_run_id set
        step_runs = db_session.query(Run).filter(Run.pipeline_run_id == pr.id).all()
        assert len(step_runs) == 2

        # Second call's prompt should contain the first task's output
        second_call_prompt = mock_runner.call_args_list[1][0][0]
        assert "calendar events data" in second_call_prompt
        assert "Summarize this" in second_call_prompt

    def test_pipeline_failure_stops(self, db_session):
        """First task fails — pipeline stops, second task never runs."""
        task_a = task_crud.create(db_session, name="task_a", prompt="Fetch data")
        task_b = task_crud.create(db_session, name="task_b", prompt="Summarize this")
        pipeline = pipeline_crud.create(
            db_session, name="fail-early", task_ids=[task_a.id, task_b.id]
        )

        mock_runner = MagicMock(
            return_value={
                "exit_code": 1,
                "stdout": "",
                "stderr": "error",
                "activity": "",
            }
        )

        pr = execute_pipeline(pipeline, db_session, runner=mock_runner)

        assert pr.status == "failed"

        # Only one Run record should exist (second task never ran)
        step_runs = db_session.query(Run).filter(Run.pipeline_run_id == pr.id).all()
        assert len(step_runs) == 1

        # current_step should be 0 (first step)
        assert pr.current_step == 0

    def test_pipeline_three_steps_chaining(self, db_session):
        """Three tasks — each step receives only the previous step's output."""
        task_a = task_crud.create(db_session, name="task_a", prompt="step 0")
        task_b = task_crud.create(db_session, name="task_b", prompt="step 1")
        task_c = task_crud.create(db_session, name="task_c", prompt="step 2")
        pipeline = pipeline_crud.create(
            db_session,
            name="triple",
            task_ids=[task_a.id, task_b.id, task_c.id],
        )

        mock_runner = MagicMock(
            side_effect=[
                {
                    "exit_code": 0,
                    "stdout": "output-from-step-0",
                    "stderr": "",
                    "activity": "",
                },
                {
                    "exit_code": 0,
                    "stdout": "output-from-step-1",
                    "stderr": "",
                    "activity": "",
                },
                {
                    "exit_code": 0,
                    "stdout": "output-from-step-2",
                    "stderr": "",
                    "activity": "",
                },
            ]
        )

        pr = execute_pipeline(pipeline, db_session, runner=mock_runner)

        assert pr.status == "success"

        # All three runs created
        step_runs = db_session.query(Run).filter(Run.pipeline_run_id == pr.id).all()
        assert len(step_runs) == 3

        # Third task's prompt should contain second task's output, not first's
        third_call_prompt = mock_runner.call_args_list[2][0][0]
        assert "output-from-step-1" in third_call_prompt
        assert "step 2" in third_call_prompt
        # First task's output should NOT be directly in third prompt
        assert "output-from-step-0" not in third_call_prompt

    def test_pipeline_with_env_vars(self, db_session):
        """Task with env_vars — env_vars are passed through to the runner."""
        task = task_crud.create(
            db_session,
            name="env-task",
            prompt="do stuff",
            env_vars={"API_KEY": "secret123", "MODE": "prod"},
        )
        pipeline = pipeline_crud.create(
            db_session, name="env-pipeline", task_ids=[task.id]
        )

        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "done",
                "stderr": "",
                "activity": "",
            }
        )

        pr = execute_pipeline(pipeline, db_session, runner=mock_runner)

        assert pr.status == "success"
        mock_runner.assert_called_once()

        # Verify env_vars were passed to the runner
        call_kwargs = mock_runner.call_args.kwargs
        assert call_kwargs["env_vars"] == {"API_KEY": "secret123", "MODE": "prod"}

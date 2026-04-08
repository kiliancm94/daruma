"""Tests for task output formatting and file writing."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services import _format_output, _write_output


def _make_task(output_format=None, output_destination=None, name="my-task"):
    task = MagicMock()
    task.name = name
    task.output_format = output_format
    task.output_destination = output_destination
    return task


class TestFormatOutput:
    def test_text_format_returns_raw(self):
        result = _format_output("hello world", "text", "task", "run-1")
        assert result == "hello world"

    def test_md_format_includes_task_name_and_output(self):
        result = _format_output("some output", "md", "my-task", "run-abc")
        assert "# my-task" in result
        assert "some output" in result
        assert "run-abc"[:8] in result

    def test_json_format_is_valid_json(self):
        result = _format_output("output text", "json", "my-task", "run-123")
        data = json.loads(result)
        assert data["task"] == "my-task"
        assert data["run_id"] == "run-123"
        assert data["output"] == "output text"
        assert "timestamp" in data

    def test_unknown_format_returns_raw(self):
        result = _format_output("raw", "text", "t", "r")
        assert result == "raw"


class TestWriteOutput:
    def test_no_destination_does_nothing(self, tmp_path):
        task = _make_task(output_format="text", output_destination=None)
        _write_output("output", task, "run-1")  # should not raise

    def test_pipe_destination_does_nothing(self, tmp_path):
        task = _make_task(output_format="text", output_destination="pipeline")
        _write_output("output", task, "run-1")  # should not raise

    def test_writes_to_file_path(self, tmp_path):
        dest = str(tmp_path / "result.txt")
        task = _make_task(output_format="text", output_destination=dest)
        _write_output("hello", task, "run-1")
        assert Path(dest).read_text() == "hello"

    def test_writes_json_to_file(self, tmp_path):
        dest = str(tmp_path / "result.json")
        task = _make_task(output_format="json", output_destination=dest)
        _write_output("hello", task, "run-1")
        data = json.loads(Path(dest).read_text())
        assert data["output"] == "hello"
        assert data["task"] == "my-task"

    def test_writes_md_to_file(self, tmp_path):
        dest = str(tmp_path / "result.md")
        task = _make_task(output_format="md", output_destination=dest)
        _write_output("hello", task, "run-1")
        content = Path(dest).read_text()
        assert "# my-task" in content
        assert "hello" in content

    def test_directory_destination_creates_timestamped_file(self, tmp_path):
        dest = str(tmp_path) + "/"
        task = _make_task(output_format="text", output_destination=dest, name="daily")
        _write_output("output", task, "run-1")
        files = list(tmp_path.glob("daily_*.txt"))
        assert len(files) == 1
        assert files[0].read_text() == "output"

    def test_directory_without_trailing_slash(self, tmp_path):
        dest = str(tmp_path / "subdir")
        task = _make_task(output_format="md", output_destination=dest, name="report")
        _write_output("output", task, "run-1")
        files = list((tmp_path / "subdir").glob("report_*.md"))
        assert len(files) == 1

    def test_creates_parent_dirs(self, tmp_path):
        dest = str(tmp_path / "a" / "b" / "c" / "out.txt")
        task = _make_task(output_format="text", output_destination=dest)
        _write_output("content", task, "run-1")
        assert Path(dest).read_text() == "content"

    def test_overwrites_existing_file(self, tmp_path):
        dest = tmp_path / "out.txt"
        dest.write_text("old content")
        task = _make_task(output_format="text", output_destination=str(dest))
        _write_output("new content", task, "run-1")
        assert dest.read_text() == "new content"


class TestExecuteTaskWithOutput:
    def test_output_written_on_success(self, tmp_path, db_session):
        from app.crud import tasks as task_crud
        from app.services import execute_task

        dest = str(tmp_path / "out.txt")
        task = task_crud.create(
            db_session,
            name="write-test",
            prompt="p",
            output_format="text",
            output_destination=dest,
        )
        mock_runner = MagicMock(
            return_value={
                "exit_code": 0,
                "stdout": "task output",
                "stderr": "",
                "activity": "",
            }
        )
        execute_task(task, db_session, runner=mock_runner)
        assert Path(dest).read_text() == "task output"

    def test_output_not_written_on_failure(self, tmp_path, db_session):
        from app.crud import tasks as task_crud
        from app.services import execute_task

        dest = str(tmp_path / "out.txt")
        task = task_crud.create(
            db_session,
            name="fail-test",
            prompt="p",
            output_format="text",
            output_destination=dest,
        )
        mock_runner = MagicMock(
            return_value={
                "exit_code": 1,
                "stdout": "partial",
                "stderr": "err",
                "activity": "",
            }
        )
        execute_task(task, db_session, runner=mock_runner)
        assert not Path(dest).exists()


class TestOutputFormatValidation:
    def test_valid_formats_accepted(self):
        from app.schemas.task import TaskCreate

        for fmt in ("text", "json", "md"):
            t = TaskCreate(name="x", prompt="p", output_format=fmt)
            assert t.output_format == fmt

    def test_invalid_format_rejected(self):
        from app.schemas.task import TaskCreate

        with pytest.raises(Exception):
            TaskCreate(name="x", prompt="p", output_format="xml")

    def test_none_format_accepted(self):
        from app.schemas.task import TaskCreate

        t = TaskCreate(name="x", prompt="p")
        assert t.output_format is None

    def test_pipe_destination_accepted(self):
        from app.schemas.task import TaskCreate

        t = TaskCreate(name="x", prompt="p", output_destination="pipeline")
        assert t.output_destination == "pipeline"

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from app.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_db(db_path):
    """Patch DB_PATH so CLI uses the test database."""
    with patch("app.cli.DB_PATH", db_path):
        from app.db import init_db

        init_db(db_path)
        yield


class TestTaskCommands:
    def test_list_empty(self, runner, mock_db):
        result = runner.invoke(cli, ["tasks", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output

    def test_create_and_list(self, runner, mock_db):
        result = runner.invoke(
            cli, ["tasks", "create", "--name", "Test Task", "--prompt", "Do it"]
        )
        assert result.exit_code == 0
        assert "Created task: Test Task" in result.output

        result = runner.invoke(cli, ["tasks", "list"])
        assert result.exit_code == 0
        assert "Test Task" in result.output

    def test_create_with_options(self, runner, mock_db):
        result = runner.invoke(
            cli,
            [
                "tasks",
                "create",
                "--name",
                "Cron Task",
                "--prompt",
                "Run daily",
                "--cron",
                "0 8 * * 1-5",
                "--tools",
                "Bash,Read",
                "--disabled",
            ],
        )
        assert result.exit_code == 0
        assert "Created task: Cron Task" in result.output

    def test_show(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Show Me", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "show", "Show Me"])
        assert result.exit_code == 0
        assert "Name:    Show Me" in result.output
        assert "Prompt:  p" in result.output

    def test_show_json(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "JSON Task", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "show", "JSON Task", "--json"])
        assert result.exit_code == 0
        assert "JSON Task" in result.output

    def test_list_json(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "A", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "list", "--json"])
        assert result.exit_code == 0
        assert '"name"' in result.output

    def test_edit(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Old Name", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "edit", "Old Name", "--name", "New Name"])
        assert result.exit_code == 0
        assert "Updated task: New Name" in result.output

    def test_delete_with_confirm(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Doomed", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "delete", "Doomed", "-y"])
        assert result.exit_code == 0
        assert "Deleted task: Doomed" in result.output

        result = runner.invoke(cli, ["tasks", "list"])
        assert "No tasks" in result.output

    def test_show_not_found(self, runner, mock_db):
        result = runner.invoke(cli, ["tasks", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestRunCommands:
    def test_list_empty(self, runner, mock_db):
        result = runner.invoke(cli, ["runs", "list"])
        assert result.exit_code == 0
        assert "No runs" in result.output

    def test_list_with_task_filter(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Filterable", "--prompt", "p"])
        result = runner.invoke(cli, ["runs", "list", "--task", "Filterable"])
        assert result.exit_code == 0
        assert "No runs" in result.output


class TestRunExecution:
    def test_run_task(self, runner, mock_db):
        runner.invoke(
            cli, ["tasks", "create", "--name", "Runnable", "--prompt", "Hello"]
        )
        with patch("app.services.run_claude") as mock_claude:
            mock_claude.return_value = {
                "exit_code": 0,
                "stdout": "Hello from Claude",
                "stderr": "",
                "activity": "[Bash] echo hi",
            }
            result = runner.invoke(cli, ["run", "Runnable"])
            assert result.exit_code == 0
            assert "Status: success" in result.output

    def test_run_task_failure(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Failing", "--prompt", "fail"])
        with patch("app.services.run_claude") as mock_claude:
            mock_claude.return_value = {
                "exit_code": 1,
                "stdout": "",
                "stderr": "error occurred",
                "activity": "",
            }
            result = runner.invoke(cli, ["run", "Failing"])
            assert result.exit_code == 1
            assert "Status: failed" in result.output

    def test_run_task_not_found(self, runner, mock_db):
        result = runner.invoke(cli, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

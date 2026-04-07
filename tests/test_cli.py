from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from app.cli import cli, _build_plist, PLIST_LABEL


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

    def test_create_with_model(self, runner, mock_db):
        result = runner.invoke(
            cli,
            [
                "tasks",
                "create",
                "--name",
                "Opus Task",
                "--prompt",
                "p",
                "--model",
                "opus",
            ],
        )
        assert result.exit_code == 0
        assert "Created task: Opus Task" in result.output
        result = runner.invoke(cli, ["tasks", "show", "Opus Task"])
        assert "Model:   opus" in result.output

    def test_create_invalid_model(self, runner, mock_db):
        result = runner.invoke(
            cli,
            ["tasks", "create", "--name", "Bad", "--prompt", "p", "--model", "gpt-4"],
        )
        assert result.exit_code != 0

    def test_create_default_model(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Default", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "show", "Default"])
        assert "Model:   sonnet" in result.output

    def test_edit_model(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "Editable", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "edit", "Editable", "--model", "haiku"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["tasks", "show", "Editable"])
        assert "Model:   haiku" in result.output

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

    def test_create_with_env_vars(self, runner, mock_db):
        result = runner.invoke(
            cli,
            [
                "tasks",
                "create",
                "--name",
                "EnvTask",
                "--prompt",
                "p",
                "--env",
                "KEY=value1",
                "--env",
                "OTHER=val2",
            ],
        )
        assert result.exit_code == 0
        assert "Created task: EnvTask" in result.output

    def test_show_with_env_vars(self, runner, mock_db):
        runner.invoke(
            cli,
            [
                "tasks",
                "create",
                "--name",
                "EnvShow",
                "--prompt",
                "p",
                "--env",
                "SECRET=hidden",
                "--env",
                "TOKEN=abc123",
            ],
        )
        result = runner.invoke(cli, ["tasks", "show", "EnvShow"])
        assert result.exit_code == 0
        assert "SECRET=***" in result.output
        assert "TOKEN=***" in result.output
        assert "hidden" not in result.output
        assert "abc123" not in result.output

    def test_show_without_env_vars(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "NoEnv", "--prompt", "p"])
        result = runner.invoke(cli, ["tasks", "show", "NoEnv"])
        assert result.exit_code == 0
        assert "Env vars: none" in result.output

    def test_edit_add_env_vars(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "EditEnv", "--prompt", "p"])
        result = runner.invoke(
            cli,
            ["tasks", "edit", "EditEnv", "--env", "NEW_KEY=new_val"],
        )
        assert result.exit_code == 0
        assert "Updated task: EditEnv" in result.output
        result = runner.invoke(cli, ["tasks", "show", "EditEnv"])
        assert "NEW_KEY=***" in result.output

    def test_create_invalid_env_var(self, runner, mock_db):
        result = runner.invoke(
            cli,
            ["tasks", "create", "--name", "Bad", "--prompt", "p", "--env", "NOEQUALS"],
        )
        assert result.exit_code == 1
        assert "Invalid env var" in result.output

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


class TestSkillCommands:
    def test_list_empty(self, runner, mock_db):
        result = runner.invoke(cli, ["skills", "list"])
        assert result.exit_code == 0
        assert "No skills" in result.output

    def test_create_and_list(self, runner, mock_db):
        result = runner.invoke(
            cli, ["skills", "create", "--name", "test", "--content", "# Test skill"]
        )
        assert result.exit_code == 0
        assert "Created skill: test" in result.output

        result = runner.invoke(cli, ["skills", "list"])
        assert "test" in result.output

    def test_show(self, runner, mock_db):
        runner.invoke(
            cli, ["skills", "create", "--name", "s", "--content", "body text"]
        )
        result = runner.invoke(cli, ["skills", "show", "s"])
        assert result.exit_code == 0
        assert "body text" in result.output

    def test_delete(self, runner, mock_db):
        runner.invoke(cli, ["skills", "create", "--name", "d", "--content", "c"])
        result = runner.invoke(cli, ["skills", "delete", "d", "-y"])
        assert result.exit_code == 0
        assert "Deleted skill: d" in result.output

    def test_import_from_file(self, runner, mock_db, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: imported\ndescription: From file\n---\n# Imported")
        result = runner.invoke(cli, ["skills", "import", str(f)])
        assert result.exit_code == 0
        assert "Imported skill: imported" in result.output

    def test_assign_to_task(self, runner, mock_db):
        runner.invoke(cli, ["tasks", "create", "--name", "T", "--prompt", "p"])
        runner.invoke(cli, ["skills", "create", "--name", "s", "--content", "c"])
        result = runner.invoke(cli, ["tasks", "edit", "T", "--skills", "s"])
        assert result.exit_code == 0
        assert "Updated task: T" in result.output


class TestPipelineCommands:
    def _create_task(self, runner, name="Task A", prompt="Do A"):
        runner.invoke(cli, ["tasks", "create", "--name", name, "--prompt", prompt])

    def test_pipelines_list_empty(self, runner, mock_db):
        result = runner.invoke(cli, ["pipelines", "list"])
        assert result.exit_code == 0
        assert "No pipelines" in result.output

    def test_pipelines_list(self, runner, mock_db):
        self._create_task(runner, "Step1", "p1")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "My Pipe", "--steps", "Step1"],
        )
        result = runner.invoke(cli, ["pipelines", "list"])
        assert result.exit_code == 0
        assert "My Pipe" in result.output

    def test_pipelines_create(self, runner, mock_db):
        self._create_task(runner, "Alpha", "do alpha")
        self._create_task(runner, "Beta", "do beta")
        result = runner.invoke(
            cli,
            [
                "pipelines",
                "create",
                "--name",
                "Two Step",
                "--steps",
                "Alpha,Beta",
                "--description",
                "A two-step pipeline",
            ],
        )
        assert result.exit_code == 0
        assert "Created pipeline: Two Step" in result.output

    def test_pipelines_create_invalid_task(self, runner, mock_db):
        result = runner.invoke(
            cli,
            ["pipelines", "create", "--name", "Bad", "--steps", "NonExistent"],
        )
        assert result.exit_code == 1
        assert "Task not found" in result.output

    def test_pipelines_show(self, runner, mock_db):
        self._create_task(runner, "ShowTask", "p")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "ShowPipe", "--steps", "ShowTask"],
        )
        result = runner.invoke(cli, ["pipelines", "show", "ShowPipe"])
        assert result.exit_code == 0
        assert "Name:        ShowPipe" in result.output
        assert "1. ShowTask" in result.output

    def test_pipelines_show_json(self, runner, mock_db):
        self._create_task(runner, "JTask", "p")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "JPipe", "--steps", "JTask"],
        )
        result = runner.invoke(cli, ["pipelines", "show", "JPipe", "--json"])
        assert result.exit_code == 0
        assert '"name"' in result.output
        assert "JPipe" in result.output

    def test_pipelines_edit(self, runner, mock_db):
        self._create_task(runner, "EditTask", "p")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "EditPipe", "--steps", "EditTask"],
        )
        result = runner.invoke(
            cli, ["pipelines", "edit", "EditPipe", "--name", "Renamed"]
        )
        assert result.exit_code == 0
        assert "Updated pipeline: Renamed" in result.output

    def test_pipelines_edit_steps(self, runner, mock_db):
        self._create_task(runner, "X", "px")
        self._create_task(runner, "Y", "py")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "StepPipe", "--steps", "X"],
        )
        result = runner.invoke(cli, ["pipelines", "edit", "StepPipe", "--steps", "Y,X"])
        assert result.exit_code == 0
        assert "Updated pipeline: StepPipe" in result.output

    def test_pipelines_delete(self, runner, mock_db):
        self._create_task(runner, "DelTask", "p")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "DelPipe", "--steps", "DelTask"],
        )
        result = runner.invoke(cli, ["pipelines", "delete", "DelPipe", "-y"])
        assert result.exit_code == 0
        assert "Deleted pipeline: DelPipe" in result.output
        result = runner.invoke(cli, ["pipelines", "list"])
        assert "No pipelines" in result.output

    def test_pipelines_run(self, runner, mock_db):
        self._create_task(runner, "RunTask", "do run")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "RunPipe", "--steps", "RunTask"],
        )
        with patch("app.services.run_claude") as mock_claude:
            mock_claude.return_value = {
                "exit_code": 0,
                "stdout": "Step output",
                "stderr": "",
                "activity": "",
            }
            result = runner.invoke(cli, ["pipelines", "run", "RunPipe"])
            assert result.exit_code == 0
            assert "Pipeline: success" in result.output

    def test_pipelines_run_failure(self, runner, mock_db):
        self._create_task(runner, "FailTask", "fail")
        runner.invoke(
            cli,
            ["pipelines", "create", "--name", "FailPipe", "--steps", "FailTask"],
        )
        with patch("app.services.run_claude") as mock_claude:
            mock_claude.return_value = {
                "exit_code": 1,
                "stdout": "",
                "stderr": "error",
                "activity": "",
            }
            result = runner.invoke(cli, ["pipelines", "run", "FailPipe"])
            assert result.exit_code == 1
            assert "Pipeline: failed" in result.output

    def test_pipelines_not_found(self, runner, mock_db):
        result = runner.invoke(cli, ["pipelines", "show", "nope"])
        assert result.exit_code == 1
        assert "Pipeline not found" in result.output


class TestServerCommand:
    def test_server_help(self, runner):
        result = runner.invoke(cli, ["server", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output


class TestServiceCommands:
    def test_build_plist_contains_label(self):
        xml = _build_plist("127.0.0.1", 9090)
        assert PLIST_LABEL in xml
        assert "<string>server</string>" in xml
        assert "<string>127.0.0.1</string>" in xml
        assert "<string>9090</string>" in xml
        assert "<true/>" in xml  # RunAtLoad + KeepAlive

    def test_service_install(self, runner, tmp_path):
        plist_path = tmp_path / "com.daruma.server.plist"
        with (
            patch("app.cli.PLIST_PATH", plist_path),
            patch("app.cli._add_pfctl_redirect") as mock_pfctl,
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            mock_pfctl.return_value = True
            result = runner.invoke(cli, ["service", "install"])
            assert result.exit_code == 0
            assert "Service installed" in result.output
            assert "http://daruma.localhost" in result.output
            assert plist_path.exists()
            assert PLIST_LABEL in plist_path.read_text()

    def test_service_install_replaces_existing(self, runner, tmp_path):
        plist_path = tmp_path / "com.daruma.server.plist"
        plist_path.write_text("old content")
        with (
            patch("app.cli.PLIST_PATH", plist_path),
            patch("app.cli._add_pfctl_redirect") as mock_pfctl,
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            mock_pfctl.return_value = True
            result = runner.invoke(cli, ["service", "install"])
            assert result.exit_code == 0

    def test_service_uninstall(self, runner, tmp_path):
        plist_path = tmp_path / "com.daruma.server.plist"
        plist_path.write_text("some plist")
        with (
            patch("app.cli.PLIST_PATH", plist_path),
            patch("app.cli._remove_pfctl_redirect") as mock_pfctl,
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            mock_pfctl.return_value = True
            result = runner.invoke(cli, ["service", "uninstall"])
            assert result.exit_code == 0
            assert "stopped and removed" in result.output
            assert "Removed port forwarding" in result.output
            assert not plist_path.exists()

    def test_service_uninstall_not_installed(self, runner, tmp_path):
        plist_path = tmp_path / "com.daruma.server.plist"
        with patch("app.cli.PLIST_PATH", plist_path):
            result = runner.invoke(cli, ["service", "uninstall"])
            assert result.exit_code == 0
            assert "not installed" in result.output

    def test_service_status_not_running(self, runner, tmp_path):
        plist_path = tmp_path / "com.daruma.server.plist"
        with (
            patch("app.cli.PLIST_PATH", plist_path),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = runner.invoke(cli, ["service", "status"])
            assert result.exit_code == 1
            assert "not running" in result.output
            assert "Not installed" in result.output

    def test_service_status_running(self, runner, tmp_path):
        plist_path = tmp_path / "com.daruma.server.plist"
        plist_path.write_text("plist")
        with (
            patch("app.cli.PLIST_PATH", plist_path),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=f'"{PLIST_LABEL}" = {{\n\tPID = 12345;\n}};',
            )
            result = runner.invoke(cli, ["service", "status"])
            assert result.exit_code == 0
            assert "PID" in result.output

    def test_pfctl_redirect_creates_anchor(self, tmp_path):
        from app.cli import _add_pfctl_redirect

        anchor_file = tmp_path / "com.daruma"
        pf_conf = tmp_path / "pf.conf"
        pf_conf.write_text("# default pf.conf\n")
        with (
            patch("app.cli.PFCTL_ANCHOR_FILE", anchor_file),
            patch("app.cli.Path") as mock_path_cls,
            patch("subprocess.run") as mock_run,
        ):
            mock_path_cls.return_value = pf_conf
            mock_run.return_value = MagicMock(returncode=0)
            # Mock Path("/etc/pf.conf") to return our tmp pf_conf
            result = _add_pfctl_redirect(9090)
            assert result is True
            # Verify sudo tee was called with the anchor content
            first_call_args = mock_run.call_args_list[0]
            assert "tee" in first_call_args[0][0]
            assert "9090" in first_call_args[1].get("input", "")

    def test_pfctl_remove_when_no_anchor(self, tmp_path):
        from app.cli import _remove_pfctl_redirect

        anchor_file = tmp_path / "com.daruma"
        with patch("app.cli.PFCTL_ANCHOR_FILE", anchor_file):
            result = _remove_pfctl_redirect()
            assert result is False

    def test_insert_after_respects_pf_conf_order(self):
        from app.cli import _insert_after

        lines = [
            'scrub-anchor "com.apple/*"\n',
            'nat-anchor "com.apple/*"\n',
            'rdr-anchor "com.apple/*"\n',
            'dummynet-anchor "com.apple/*"\n',
            'anchor "com.apple/*"\n',
            'load anchor "com.apple" from "/etc/pf.anchors/com.apple"\n',
        ]
        # rdr-anchor should go after the last rdr-anchor (index 2)
        result = _insert_after(lines, "rdr-anchor", 'rdr-anchor "com.daruma"\n')
        assert result[3] == 'rdr-anchor "com.daruma"\n'
        # load anchor should go after the last load anchor (now index 7)
        result = _insert_after(result, "load anchor", 'load anchor "com.daruma" ...\n')
        assert result[-1] == 'load anchor "com.daruma" ...\n'

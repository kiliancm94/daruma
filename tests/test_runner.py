from unittest.mock import patch, MagicMock
from app.runner import run_claude


def _make_completed_process(returncode=0, stdout="response", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@patch("app.runner.subprocess.run")
def test_run_claude_success(mock_run):
    mock_run.return_value = _make_completed_process(
        returncode=0, stdout="Hello from Claude"
    )
    result = run_claude("Say hello", allowed_tools=None)
    assert result["exit_code"] == 0
    assert result["stdout"] == "Hello from Claude"
    assert result["stderr"] == ""
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"
    assert "-p" in cmd


@patch("app.runner.subprocess.run")
def test_run_claude_with_tools(mock_run):
    mock_run.return_value = _make_completed_process()
    run_claude("Do stuff", allowed_tools="bash,read")
    cmd = mock_run.call_args[0][0]
    assert "--allowedTools" in cmd
    tools_idx = cmd.index("--allowedTools")
    assert cmd[tools_idx + 1] == "bash,read"


@patch("app.runner.subprocess.run")
def test_run_claude_failure(mock_run):
    mock_run.return_value = _make_completed_process(
        returncode=1, stdout="", stderr="Error occurred"
    )
    result = run_claude("Fail please")
    assert result["exit_code"] == 1
    assert result["stderr"] == "Error occurred"


@patch("app.runner.subprocess.run")
def test_run_claude_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)
    result = run_claude("Slow task")
    assert result["exit_code"] == -1
    assert "timeout" in result["stderr"].lower()

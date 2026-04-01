import subprocess

import pytest
from unittest.mock import patch, MagicMock
from app.runner import run_claude, validate_tools


def _make_popen_mock(returncode=0, stdout="response", stderr=""):
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    return proc


@patch("app.runner.subprocess.Popen")
def test_run_claude_success(mock_popen):
    mock_popen.return_value = _make_popen_mock(
        returncode=0, stdout="Hello from Claude"
    )
    result = run_claude("Say hello", allowed_tools=None)
    assert result["exit_code"] == 0
    assert result["stdout"] == "Hello from Claude"
    assert result["stderr"] == ""
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "claude"
    assert "-p" in cmd


@patch("app.runner.subprocess.Popen")
def test_run_claude_with_tools(mock_popen):
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff", allowed_tools="Bash,Read")
    cmd = mock_popen.call_args[0][0]
    assert "--tools" in cmd
    tools_idx = cmd.index("--tools")
    assert cmd[tools_idx + 1] == "Bash,Read"


@patch("app.runner.subprocess.Popen")
def test_run_claude_failure(mock_popen):
    mock_popen.return_value = _make_popen_mock(
        returncode=1, stdout="", stderr="Error occurred"
    )
    result = run_claude("Fail please")
    assert result["exit_code"] == 1
    assert result["stderr"] == "Error occurred"


@patch("app.runner.subprocess.Popen")
def test_run_claude_timeout(mock_popen):
    proc = _make_popen_mock()
    proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)
    mock_popen.return_value = proc
    result = run_claude("Slow task")
    assert result["exit_code"] == -1
    assert "timeout" in result["stderr"].lower()
    proc.kill.assert_called_once()


@patch("app.runner.subprocess.Popen")
def test_run_claude_tracks_process(mock_popen):
    from app.runner import _active_processes
    mock_popen.return_value = _make_popen_mock()
    run_claude("Track me", run_id="test-run-123")
    # Process should be cleaned up after completion
    assert "test-run-123" not in _active_processes


# --- Tool validation tests ---

def test_validate_tools_accepts_valid():
    assert validate_tools("Bash,Read") == "Bash,Read"
    assert validate_tools("Write") == "Write"
    assert validate_tools("Bash, Read, Edit") == "Bash,Read,Edit"


def test_validate_tools_accepts_patterns():
    assert validate_tools("Bash(git:*)") == "Bash(git:*)"


def test_validate_tools_rejects_flags():
    with pytest.raises(ValueError, match="Invalid tool name"):
        validate_tools("--dangerously-skip-permissions")


def test_validate_tools_rejects_unknown():
    with pytest.raises(ValueError, match="Invalid tool name"):
        validate_tools("Bash,Evil")


def test_validate_tools_rejects_flag_mixed():
    with pytest.raises(ValueError, match="Invalid tool name"):
        validate_tools("Read,--dangerously-skip-permissions")

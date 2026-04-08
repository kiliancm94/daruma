import io
import json
import os

import pytest
from unittest.mock import patch, MagicMock
from app.runner import run_claude, validate_tools, _split_tool_patterns


def _make_stream_lines(text="response", is_error=False):
    """Build stream-json lines that claude CLI would emit."""
    lines = []
    # assistant event with text
    lines.append(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": text}]},
            }
        )
    )
    # result event
    lines.append(
        json.dumps(
            {
                "type": "result",
                "subtype": "error" if is_error else "success",
                "result": text,
            }
        )
    )
    return "\n".join(lines) + "\n"


def _make_stream_with_tool_use():
    """Build stream-json with a tool call and result."""
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "echo hello"},
                        },
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "content": "hello"},
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Done!"},
                    ]
                },
            }
        ),
        json.dumps({"type": "result", "result": "Done!"}),
    ]
    return "\n".join(lines) + "\n"


def _make_popen_mock(returncode=0, stdout="response", stderr=""):
    proc = MagicMock()
    stream_output = _make_stream_lines(stdout)
    proc.stdout = io.StringIO(stream_output)
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = stderr
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    return proc


@patch("app.runner.subprocess.Popen")
def test_run_claude_success(mock_popen):
    mock_popen.return_value = _make_popen_mock(returncode=0, stdout="Hello from Claude")
    result = run_claude("Say hello", allowed_tools=None)
    assert result["exit_code"] == 0
    assert result["stdout"] == "Hello from Claude"
    assert result["stderr"] == ""
    cmd = mock_popen.call_args[0][0]
    assert os.path.basename(cmd[0]) == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "sonnet"


@patch("app.runner.subprocess.Popen")
def test_run_claude_with_model(mock_popen):
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff", model="opus")
    cmd = mock_popen.call_args[0][0]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "opus"


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
    proc = MagicMock()

    # Yield lines slowly — deadline of 0 will be exceeded on first line
    def slow_iter():
        yield '{"type":"system","subtype":"init"}\n'
        yield '{"type":"system","subtype":"init"}\n'

    proc.stdout = slow_iter()
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = ""
    proc.returncode = -1
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    mock_popen.return_value = proc

    result = run_claude("Slow task", timeout=0)
    assert result["exit_code"] == -1
    assert "timeout" in result["stderr"].lower()
    proc.kill.assert_called()


@patch("app.runner.subprocess.Popen")
def test_run_claude_tracks_process(mock_popen):
    from app.runner import _active_processes

    mock_popen.return_value = _make_popen_mock()
    run_claude("Track me", run_id="test-run-123")
    assert "test-run-123" not in _active_processes


@patch("app.runner._FLUSH_INTERVAL", 0)
@patch("app.runner.subprocess.Popen")
def test_run_claude_streams_output(mock_popen):
    mock_popen.return_value = _make_popen_mock(stdout="streaming result")
    captured = []
    result = run_claude(
        "Stream me", on_output=lambda out, act: captured.append((out, act))
    )
    assert "streaming result" in result["stdout"]
    assert len(captured) > 0


@patch("app.runner._FLUSH_INTERVAL", 0)
@patch("app.runner.subprocess.Popen")
def test_run_claude_separates_output_and_activity(mock_popen):
    proc = MagicMock()
    proc.stdout = io.StringIO(_make_stream_with_tool_use())
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = ""
    proc.returncode = 0
    proc.wait = MagicMock()
    mock_popen.return_value = proc
    result = run_claude("Do stuff")
    assert "Done!" in result["stdout"]
    assert "[Bash] echo hello" in result["activity"]
    assert "hello" in result["activity"]


# --- Tool validation tests ---


def test_validate_tools_accepts_valid():
    assert validate_tools("Bash,Read") == "Bash,Read"
    assert validate_tools("Write") == "Write"
    assert validate_tools("Bash, Read, Edit") == "Bash,Read,Edit"


def test_validate_tools_normalizes_case():
    assert validate_tools("bash,read") == "Bash,Read"
    assert validate_tools("WRITE") == "Write"
    assert validate_tools("bash, read, edit") == "Bash,Read,Edit"


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


# --- Tool pattern splitting tests ---


def test_split_tool_patterns_plain():
    tools, patterns = _split_tool_patterns("Bash,Read")
    assert tools == "Bash,Read"
    assert patterns == ""


def test_split_tool_patterns_with_pattern():
    tools, patterns = _split_tool_patterns("Bash(curl:*),Read")
    assert tools == "Bash,Read"
    assert patterns == "Bash(curl:*)"


def test_split_tool_patterns_multiple_patterns():
    tools, patterns = _split_tool_patterns("Bash(curl:*),Bash(git:*),Read")
    assert tools == "Bash,Read"
    assert patterns == "Bash(curl:*),Bash(git:*)"


@patch("app.runner.subprocess.Popen")
def test_run_claude_with_system_prompt(mock_popen):
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff", system_prompt="You are a Jira expert")
    cmd = mock_popen.call_args[0][0]
    assert "--append-system-prompt" in cmd
    idx = cmd.index("--append-system-prompt")
    assert cmd[idx + 1] == "You are a Jira expert"


@patch("app.runner.subprocess.Popen")
def test_run_claude_without_system_prompt(mock_popen):
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff")
    cmd = mock_popen.call_args[0][0]
    assert "--append-system-prompt" not in cmd


# --- Env vars tests ---


@patch("app.runner.subprocess.Popen")
def test_run_claude_with_env_vars(mock_popen):
    import os

    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff", env_vars={"MY_TOKEN": "secret"})
    call_kwargs = mock_popen.call_args[1]  # keyword args
    assert "env" in call_kwargs
    assert call_kwargs["env"]["MY_TOKEN"] == "secret"
    # Parent env should be inherited too
    assert call_kwargs["env"].get("PATH") == os.environ.get("PATH")


@patch("app.runner.subprocess.Popen")
def test_run_claude_without_env_vars(mock_popen):
    mock_popen.return_value = _make_popen_mock()
    run_claude("Do stuff")
    call_kwargs = mock_popen.call_args[1]
    # No env= kwarg means inherit parent env
    assert "env" not in call_kwargs

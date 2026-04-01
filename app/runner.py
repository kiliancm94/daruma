import subprocess
import threading
import time
from typing import Callable

VALID_TOOLS = frozenset({
    "Agent", "Bash", "Edit", "Glob", "Grep", "Read", "Write",
    "NotebookEdit", "WebFetch", "WebSearch",
})

# Track running processes by run_id for cancellation
_active_processes: dict[str, subprocess.Popen] = {}
_lock = threading.Lock()

# How often to flush partial output to the callback (seconds)
_FLUSH_INTERVAL = 2


def validate_tools(tools_str: str) -> str:
    """Validate tool names against allowlist to prevent CLI flag injection."""
    tools = [t.strip() for t in tools_str.split(",") if t.strip()]
    for t in tools:
        base = t.split("(")[0]
        if base.startswith("-") or base not in VALID_TOOLS:
            raise ValueError(f"Invalid tool name: {t}")
    return ",".join(tools)


def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    timeout: int = 300,
    run_id: str | None = None,
    on_output: Callable[[str], None] | None = None,
) -> dict:
    cmd = ["claude", "-p", "--permission-mode", "auto", prompt]
    if allowed_tools:
        validated = validate_tools(allowed_tools)
        cmd.extend(["--tools", validated])

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if run_id:
            with _lock:
                _active_processes[run_id] = proc

        try:
            if on_output:
                stdout = _stream_output(proc, timeout, on_output)
            else:
                stdout, _ = proc.communicate(timeout=timeout)

            stderr = proc.stderr.read() if proc.stderr else ""
            proc.wait()
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Timeout after {timeout}s",
            }
        finally:
            if run_id:
                with _lock:
                    _active_processes.pop(run_id, None)

        return {
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except FileNotFoundError:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "claude CLI not found",
        }


def _stream_output(
    proc: subprocess.Popen,
    timeout: int,
    on_output: Callable[[str], None],
) -> str:
    """Read stdout line-by-line, flushing to callback every _FLUSH_INTERVAL seconds."""
    lines: list[str] = []
    last_flush = time.monotonic()
    deadline = time.monotonic() + timeout

    for line in proc.stdout:
        lines.append(line)
        now = time.monotonic()
        if now > deadline:
            proc.kill()
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)
        if now - last_flush >= _FLUSH_INTERVAL:
            on_output("".join(lines))
            last_flush = now

    # Final flush with complete output
    output = "".join(lines)
    on_output(output)
    return output


def cancel_run(run_id: str) -> bool:
    """Kill the process for a running run. Returns True if killed."""
    with _lock:
        proc = _active_processes.pop(run_id, None)
    if proc is None:
        return False
    proc.kill()
    proc.wait()
    return True

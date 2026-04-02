import json
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


_TOOLS_LOWER = {t.lower(): t for t in VALID_TOOLS}


def validate_tools(tools_str: str) -> str:
    """Validate and normalize tool names against allowlist."""
    tools = [t.strip() for t in tools_str.split(",") if t.strip()]
    normalized = []
    for t in tools:
        base = t.split("(")[0]
        if base.startswith("-"):
            raise ValueError(f"Invalid tool name: {t}")
        # Accept case-insensitive, normalize to canonical form
        canonical = _TOOLS_LOWER.get(base.lower())
        if canonical is None:
            raise ValueError(f"Invalid tool name: {t}")
        # Preserve pattern suffix like Bash(git:*)
        suffix = t[len(base):]
        normalized.append(canonical + suffix)
    return ",".join(normalized)


def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    timeout: int = 300,
    run_id: str | None = None,
    on_output: Callable[[str], None] | None = None,
) -> dict:
    cmd = [
        "claude", "-p",
        "--permission-mode", "auto",
        "--output-format", "stream-json",
        "--verbose",
        prompt,
    ]
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
            result = _read_stream(proc, timeout, on_output)
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

        proc.wait()
        stderr = proc.stderr.read() if proc.stderr else ""
        return {
            "exit_code": proc.returncode,
            "stdout": result,
            "stderr": stderr,
        }
    except FileNotFoundError:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "claude CLI not found",
        }


def _read_stream(
    proc: subprocess.Popen,
    timeout: int,
    on_output: Callable[[str], None] | None,
) -> str:
    """Parse stream-json output, build activity log, flush periodically."""
    activity: list[str] = []
    final_result = ""
    last_flush = time.monotonic()
    deadline = time.monotonic() + timeout

    for line in proc.stdout:
        if time.monotonic() > deadline:
            proc.kill()
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)

        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        evt_type = event.get("type")
        content = event.get("message", {}).get("content", [])

        if evt_type == "assistant":
            for block in content:
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    # Show what tool is being called
                    if name == "Bash":
                        cmd = inp.get("command", "")
                        activity.append(f"[Bash] {cmd}")
                    elif name == "Read":
                        activity.append(f"[Read] {inp.get('file_path', '')}")
                    elif name == "Write":
                        activity.append(f"[Write] {inp.get('file_path', '')}")
                    elif name == "Edit":
                        activity.append(f"[Edit] {inp.get('file_path', '')}")
                    else:
                        activity.append(f"[{name}]")
                elif btype == "text":
                    text = block.get("text", "")
                    if text.strip():
                        activity.append(text)

        elif evt_type == "user":
            for block in content:
                if block.get("type") == "tool_result":
                    result_text = block.get("content", "")
                    if isinstance(result_text, str) and result_text.strip():
                        # Truncate long tool outputs for the activity view
                        if len(result_text) > 500:
                            result_text = result_text[:500] + "…"
                        activity.append(f"  → {result_text}")

        elif evt_type == "result":
            final_result = event.get("result", "")

        # Flush partial activity periodically
        if on_output and activity:
            now = time.monotonic()
            if now - last_flush >= _FLUSH_INTERVAL:
                on_output("\n".join(activity))
                last_flush = now

    # Final flush
    output = "\n".join(activity) if activity else final_result
    if on_output:
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

import json
import os
import subprocess
import threading
import time
from typing import Callable

VALID_MODELS = ("sonnet", "opus", "haiku")
DEFAULT_MODEL = "sonnet"

VALID_TOOLS = frozenset(
    {
        "Agent",
        "Bash",
        "Edit",
        "Glob",
        "Grep",
        "Read",
        "Write",
        "NotebookEdit",
        "WebFetch",
        "WebSearch",
    }
)

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
        suffix = t[len(base) :]
        normalized.append(canonical + suffix)
    return ",".join(normalized)


def _split_tool_patterns(tools_str: str) -> tuple[str, str]:
    """Split a tools string into plain tool names and pattern-based permissions.

    Returns (tools, allowed_patterns) where:
    - tools: comma-separated base names for --tools (e.g. "Bash,Read")
    - allowed_patterns: comma-separated patterns for --allowedTools (e.g. "Bash(curl:*)")
    """
    base_names: set[str] = set()
    patterns: list[str] = []
    for t in tools_str.split(","):
        t = t.strip()
        if not t:
            continue
        base = t.split("(")[0]
        base_names.add(base)
        if "(" in t:
            patterns.append(t)
    return ",".join(sorted(base_names)), ",".join(patterns)


def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    model: str = DEFAULT_MODEL,
    system_prompt: str | None = None,
    timeout: int = 300,
    run_id: str | None = None,
    on_output: Callable[[str], None] | None = None,
    env_vars: dict[str, str] | None = None,
) -> dict:
    cmd = [
        "claude",
        "-p",
        "--permission-mode",
        "auto",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        prompt,
    ]
    if allowed_tools:
        validated = validate_tools(allowed_tools)
        tools, patterns = _split_tool_patterns(validated)
        if tools:
            cmd.extend(["--tools", tools])
        if patterns:
            cmd.extend(["--allowedTools", patterns])

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    popen_kwargs: dict = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if env_vars:
        popen_kwargs["env"] = {**os.environ, **env_vars}

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
        if run_id:
            with _lock:
                _active_processes[run_id] = proc

        try:
            output, activity = _read_stream(proc, timeout, on_output)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Timeout after {timeout}s",
                "activity": "",
            }
        finally:
            if run_id:
                with _lock:
                    _active_processes.pop(run_id, None)

        proc.wait()
        stderr = proc.stderr.read() if proc.stderr else ""
        return {
            "exit_code": proc.returncode,
            "stdout": output,
            "stderr": stderr,
            "activity": activity,
        }
    except FileNotFoundError:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "claude CLI not found",
            "activity": "",
        }


def _read_stream(
    proc: subprocess.Popen,
    timeout: int,
    on_output: Callable[[str, str], None] | None,
) -> tuple[str, str]:
    """Parse stream-json output. Returns (output_text, activity_log)."""
    activity_lines: list[str] = []
    output_lines: list[str] = []
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
                    if name == "Bash":
                        activity_lines.append(f"[Bash] {inp.get('command', '')}")
                    elif name in ("Read", "Write", "Edit"):
                        activity_lines.append(f"[{name}] {inp.get('file_path', '')}")
                    else:
                        activity_lines.append(f"[{name}]")
                elif btype == "text":
                    text = block.get("text", "")
                    if text.strip():
                        output_lines.append(text)

        elif evt_type == "user":
            for block in content:
                if block.get("type") == "tool_result":
                    result_text = block.get("content", "")
                    if isinstance(result_text, str) and result_text.strip():
                        if len(result_text) > 500:
                            result_text = result_text[:500] + "…"
                        activity_lines.append(f"  → {result_text}")

        elif evt_type == "result":
            result_text = event.get("result", "")
            if result_text and not output_lines:
                output_lines.append(result_text)

        # Flush periodically
        if on_output:
            now = time.monotonic()
            if now - last_flush >= _FLUSH_INTERVAL:
                on_output(
                    "\n".join(output_lines),
                    "\n".join(activity_lines),
                )
                last_flush = now

    output = "\n".join(output_lines)
    activity = "\n".join(activity_lines)
    if on_output:
        on_output(output, activity)

    return output, activity


def cancel_run(run_id: str) -> bool:
    """Kill the process for a running run. Returns True if killed."""
    with _lock:
        proc = _active_processes.pop(run_id, None)
    if proc is None:
        return False
    proc.kill()
    proc.wait()
    return True

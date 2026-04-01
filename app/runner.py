import subprocess

VALID_TOOLS = frozenset({
    "Agent", "Bash", "Edit", "Glob", "Grep", "Read", "Write",
    "NotebookEdit", "WebFetch", "WebSearch",
})


def validate_tools(tools_str: str) -> str:
    """Validate tool names against allowlist to prevent CLI flag injection."""
    tools = [t.strip() for t in tools_str.split(",") if t.strip()]
    for t in tools:
        base = t.split("(")[0]  # handle patterns like Bash(git:*)
        if base.startswith("-") or base not in VALID_TOOLS:
            raise ValueError(f"Invalid tool name: {t}")
    return ",".join(tools)


def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    timeout: int = 300,
) -> dict:
    cmd = ["claude", "-p", "--permission-mode", "auto", prompt]
    if allowed_tools:
        validated = validate_tools(allowed_tools)
        cmd.extend(["--tools", validated])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
        }

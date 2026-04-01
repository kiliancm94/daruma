import subprocess


def run_claude(
    prompt: str,
    allowed_tools: str | None = None,
    timeout: int = 300,
) -> dict:
    cmd = ["claude", "-p", prompt]
    if allowed_tools:
        cmd.extend(["--allowedTools", allowed_tools])

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

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
# Absolute project root so tool subprocesses work regardless of the caller's CWD.
_PROJECT_ROOT = str(Path(__file__).parent.parent.resolve())


def execute(
    cmd: list[str],
    stdin_data: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    tool_label: str = "tool",
) -> dict:
    """Run a subprocess, capture stdout/stderr, validate JSON output."""
    start = time.perf_counter()

    # When there is no stdin payload, point stdin at DEVNULL so the subprocess
    # never inherits the parent's stdin (which in stdio-MCP mode is the live
    # protocol pipe and would cause HTTP libraries like primp/ddgs to hang).
    stdin_kwargs = (
        {"input": stdin_data} if stdin_data is not None else {"stdin": subprocess.DEVNULL}
    )

    try:
        result = subprocess.run(
            cmd,
            **stdin_kwargs,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        logger.warning("%s timed out after %.1fs (limit=%ds)", tool_label, elapsed, timeout)
        return {"success": False, "error": f"{tool_label} timed out after {timeout}s"}
    except FileNotFoundError as exc:
        logger.error("%s executable not found: %s", tool_label, exc)
        return {"success": False, "error": f"{tool_label} executable not found: {exc}"}

    elapsed = time.perf_counter() - start

    if result.returncode != 0:
        error_msg = result.stderr.strip() or f"{tool_label} exited with code {result.returncode}"
        logger.error("%s failed in %.3fs (exit=%d): %s", tool_label, elapsed, result.returncode, error_msg)
        return {"success": False, "error": error_msg}

    stdout = result.stdout.strip()
    if not stdout:
        logger.error("%s produced no output in %.3fs", tool_label, elapsed)
        return {"success": False, "error": f"{tool_label} produced no output"}

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        logger.error("%s output is not valid JSON in %.3fs", tool_label, elapsed)
        return {"success": False, "error": f"{tool_label} output is not valid JSON", "raw": stdout}

    if parsed.get("success"):
        logger.info("%s completed in %.3fs", tool_label, elapsed)
    else:
        logger.warning("%s returned failure in %.3fs: %s", tool_label, elapsed, parsed.get("error", ""))

    return parsed

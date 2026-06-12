"""Activity logger — records every MCP tool call with inputs and outputs.

Writes to logs/activity.log (separate from server.log so audit and debug
concerns stay independent). Long string values are truncated at MAX_STR_LEN
characters so file content never bloats the log.
"""
import json
import logging
import logging.handlers
import time
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).parent.parent / "logs"
_ACTIVITY_LOG = _LOG_DIR / "activity.log"
_MAX_STR_LEN = 500


def _setup() -> logging.Logger:
    _LOG_DIR.mkdir(exist_ok=True)
    log = logging.getLogger("mcp.activity")
    if log.handlers:
        return log
    log.propagate = False  # keep out of server.log
    log.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        _ACTIVITY_LOG,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    return log


_log = _setup()


def _sanitize(value: Any) -> Any:
    """Recursively truncate long strings; leave other types unchanged."""
    if isinstance(value, str):
        return value if len(value) <= _MAX_STR_LEN else f"[{len(value)} chars truncated]"
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _fmt(value: Any) -> str:
    sanitized = _sanitize(value)
    if isinstance(sanitized, str):
        return f'"{sanitized}"'
    return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_call(tool_name: str, inputs: dict) -> None:
    """Log the start of a tool call with its input parameters."""
    parts = ", ".join(f"{k}={_fmt(v)}" for k, v in inputs.items() if v not in ("", [], {}, None))
    _log.info("%s [CALL] %s | %s", _ts(), tool_name, parts or "(no args)")


def log_done(tool_name: str, result: dict, elapsed_s: float) -> None:
    """Log the completion of a tool call with its output."""
    status = "OK" if result.get("success") else "FAIL"
    ms = int(elapsed_s * 1000)
    out = json.dumps(_sanitize(result), ensure_ascii=False, separators=(",", ":"))
    _log.info("%s [DONE] %s | %s | %dms | %s", _ts(), tool_name, status, ms, out)

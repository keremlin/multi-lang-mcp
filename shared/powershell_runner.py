from shared.runner import execute
from shared.security import validate_tool_path


def run_powershell(script_path: str, args: list[str] = [], timeout: int = 30) -> dict:
    validate_tool_path(script_path)
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-File", script_path, *args]
    return execute(cmd, timeout=timeout, tool_label=f"PowerShell:{script_path}")

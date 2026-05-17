from shared.runner import execute
from shared.security import validate_tool_path


def run_node(script_path: str, args: list[str] = [], timeout: int = 30) -> dict:
    validate_tool_path(script_path)
    cmd = ["node", script_path, *args]
    return execute(cmd, timeout=timeout, tool_label=f"Node:{script_path}")

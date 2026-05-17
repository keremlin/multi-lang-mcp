from shared.runner import execute
from shared.security import validate_tool_path


def run_java(
    jar_path: str,
    args: list[str] = [],
    stdin_data: str | None = None,
    timeout: int = 60,
) -> dict:
    validate_tool_path(jar_path)
    cmd = ["java", "-jar", jar_path, *args]
    return execute(cmd, stdin_data=stdin_data, timeout=timeout, tool_label=f"Java:{jar_path}")

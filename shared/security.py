import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_TOOLS_CONFIG_PATH = _PROJECT_ROOT / "config" / "tools.json"


def _load_allowed_paths() -> frozenset[str]:
    if not _TOOLS_CONFIG_PATH.exists():
        return frozenset()
    with open(_TOOLS_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    paths: set[str] = set()
    for tool in config.get("tools", []):
        for key in ("script", "jar"):
            if key in tool:
                paths.add(Path(tool[key]).as_posix())
    return frozenset(paths)


# Loaded once at import time; restart server after editing tools.json.
_ALLOWED_PATHS: frozenset[str] = _load_allowed_paths()


def validate_tool_path(path: str) -> None:
    """Raise ValueError if path is not in the registered allowlist or contains traversal.

    This prevents any ad-hoc or arbitrary execution pattern from sneaking in.
    Only paths declared in config/tools.json are permitted.
    """
    normalized = Path(path).as_posix()

    if ".." in normalized:
        raise ValueError(f"Directory traversal detected in tool path: {path!r}")

    try:
        (_PROJECT_ROOT / path).resolve().relative_to(_PROJECT_ROOT)
    except ValueError:
        raise ValueError(f"Tool path escapes project root: {path!r}")

    if normalized not in _ALLOWED_PATHS:
        raise ValueError(
            f"Tool path {path!r} is not registered in config/tools.json. "
            "Register the tool before executing it."
        )

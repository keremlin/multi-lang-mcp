"""Tests for config/tools.json — registry integrity checks."""
import json
from pathlib import Path

import pytest

TOOLS_CONFIG = Path(__file__).parent.parent / "config" / "tools.json"
REQUIRED_FIELDS = {"name", "runtime", "description", "timeout"}


def load_tools() -> list[dict]:
    with open(TOOLS_CONFIG, encoding="utf-8") as f:
        return json.load(f)["tools"]


def test_tools_json_is_valid():
    assert TOOLS_CONFIG.exists(), "config/tools.json is missing"
    load_tools()  # raises json.JSONDecodeError if invalid


def test_all_tools_have_required_fields():
    for tool in load_tools():
        missing = REQUIRED_FIELDS - tool.keys()
        assert not missing, f"Tool {tool.get('name', '?')} missing fields: {missing}"


def test_all_tools_have_script_or_jar():
    for tool in load_tools():
        has_path = "script" in tool or "jar" in tool
        assert has_path, f"Tool {tool['name']} has no 'script' or 'jar' field"


def test_python_and_non_java_scripts_exist():
    root = Path(__file__).parent.parent
    for tool in load_tools():
        if tool["runtime"] == "java":
            # jar requires mvn build; skip existence check
            continue
        script = tool.get("script", "")
        if script:
            assert (root / script).exists(), (
                f"Tool '{tool['name']}' script not found: {script}"
            )


def test_no_duplicate_tool_names():
    names = [t["name"] for t in load_tools()]
    assert len(names) == len(set(names)), "Duplicate tool names found in tools.json"


def test_all_timeouts_are_positive():
    for tool in load_tools():
        assert tool["timeout"] > 0, f"Tool {tool['name']} has non-positive timeout"

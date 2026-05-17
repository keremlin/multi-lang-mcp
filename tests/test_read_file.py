"""Integration tests for tools/python/read_file.py."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "read_file.py")


def run_script(*args) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def test_reads_existing_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        tmp_path = f.name

    result = run_script(tmp_path)
    assert result["success"] is True
    assert result["data"]["content"] == "hello world"
    assert result["data"]["path"] == tmp_path


def test_missing_file_returns_error():
    result = run_script("this_file_does_not_exist_xyz.txt")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_no_args_returns_error():
    raw = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = json.loads(raw.stdout)
    assert result["success"] is False
    assert "No file path" in result["error"]


def test_output_is_always_valid_json():
    result = run_script("/nonexistent/path/file.txt")
    assert isinstance(result, dict)
    assert "success" in result

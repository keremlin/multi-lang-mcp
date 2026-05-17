"""Tests for shared/runner.py — the core subprocess executor."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from shared.runner import execute


def _make_result(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    r = MagicMock()
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


@patch("shared.runner.subprocess.run")
def test_successful_json_output(mock_run):
    mock_run.return_value = _make_result('{"success": true, "data": {"x": 1}}')
    result = execute(["echo", "ignored"])
    assert result == {"success": True, "data": {"x": 1}}


@patch("shared.runner.subprocess.run")
def test_nonzero_exit_returns_error(mock_run):
    mock_run.return_value = _make_result(returncode=1, stderr="something broke")
    result = execute(["false"], tool_label="mytool")
    assert result["success"] is False
    assert "something broke" in result["error"]


@patch("shared.runner.subprocess.run")
def test_empty_output_returns_error(mock_run):
    mock_run.return_value = _make_result(stdout="")
    result = execute(["cmd"])
    assert result["success"] is False
    assert "no output" in result["error"]


@patch("shared.runner.subprocess.run")
def test_invalid_json_returns_error_with_raw(mock_run):
    mock_run.return_value = _make_result(stdout="not json at all")
    result = execute(["cmd"], tool_label="mytool")
    assert result["success"] is False
    assert "not valid JSON" in result["error"]
    assert result["raw"] == "not json at all"


@patch("shared.runner.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=5))
def test_timeout_returns_error(mock_run):
    result = execute(["slow-cmd"], timeout=5, tool_label="slowtool")
    assert result["success"] is False
    assert "timed out" in result["error"]


@patch("shared.runner.subprocess.run", side_effect=FileNotFoundError("no such file"))
def test_missing_executable_returns_error(mock_run):
    result = execute(["nonexistent-binary"], tool_label="ghost")
    assert result["success"] is False
    assert "not found" in result["error"]


@patch("shared.runner.subprocess.run")
def test_stdin_data_passed_through(mock_run):
    mock_run.return_value = _make_result('{"success": true}')
    execute(["cmd"], stdin_data='{"key": "val"}')
    _, kwargs = mock_run.call_args
    assert kwargs["input"] == '{"key": "val"}'

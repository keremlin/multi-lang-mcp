"""Tests for shared/python_runner.py — path allowlist enforcement."""
from unittest.mock import MagicMock, patch

import pytest

from shared.python_runner import run_python


def test_unregistered_path_raises():
    with pytest.raises(ValueError, match="not registered"):
        run_python("tools/python/does_not_exist.py", [])


def test_traversal_path_raises():
    with pytest.raises(ValueError, match="traversal"):
        run_python("tools/python/../../server.py", [])


def test_path_outside_project_raises():
    with pytest.raises(ValueError):
        run_python("C:/Windows/System32/cmd.exe", [])


@patch("shared.python_runner.execute")
def test_registered_path_calls_execute(mock_execute):
    mock_execute.return_value = {"success": True, "data": {}}
    result = run_python("tools/python/read_file.py", ["somefile.txt"])
    assert mock_execute.called
    cmd_used = mock_execute.call_args[0][0]
    assert "tools/python/read_file.py" in cmd_used
    assert "somefile.txt" in cmd_used

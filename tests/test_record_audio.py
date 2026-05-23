"""Integration tests for tools/python/record_audio.py."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "record_audio.py")


def run_script(*args) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(result.stdout)


def test_no_args_returns_error():
    proc = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, timeout=15)
    result = json.loads(proc.stdout)
    assert result["success"] is False
    assert "Usage" in result["error"]


def test_invalid_max_seconds_returns_error(tmp_path):
    result = run_script(str(tmp_path / "out.wav"), "abc")
    assert result["success"] is False
    assert "number" in result["error"].lower()


def test_max_seconds_out_of_range_returns_error(tmp_path):
    result = run_script(str(tmp_path / "out.wav"), "200")
    assert result["success"] is False
    assert "between" in result["error"].lower()


def test_invalid_silence_duration_returns_error(tmp_path):
    result = run_script(str(tmp_path / "out.wav"), "10", "notanumber")
    assert result["success"] is False
    assert "number" in result["error"].lower()


def test_output_always_valid_json(tmp_path):
    result = run_script(str(tmp_path / "out.wav"), "200")
    assert isinstance(result, dict)
    assert "success" in result

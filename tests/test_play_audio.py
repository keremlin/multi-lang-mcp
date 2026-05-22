"""Integration tests for tools/python/play_audio.py."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "play_audio.py")


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


def test_missing_file_returns_error():
    result = run_script("nonexistent_audio.mp3")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_unsupported_format_returns_error(tmp_path):
    bad = tmp_path / "audio.xyz"
    bad.write_bytes(b"data")
    result = run_script(str(bad))
    assert result["success"] is False
    assert "Unsupported" in result["error"]


def test_output_always_valid_json():
    result = run_script("nonexistent.mp3")
    assert isinstance(result, dict)
    assert "success" in result

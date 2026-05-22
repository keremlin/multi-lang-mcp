"""Integration tests for tools/python/groq_stt.py."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "groq_stt.py")
NO_CREDS_ENV = {
    **{k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"},
    "GROQ_API_KEY": "",
}


def run_stt(*args, env=None) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=15,
        env=env or NO_CREDS_ENV,
    )
    return json.loads(result.stdout)


def test_no_args_returns_error():
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        timeout=15,
        env=NO_CREDS_ENV,
    )
    result = json.loads(proc.stdout)
    assert result["success"] is False
    assert "Usage" in result["error"]


def test_missing_audio_file_returns_error():
    result = run_stt("nonexistent_audio.mp3")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_unsupported_format_returns_error(tmp_path):
    bad_file = tmp_path / "audio.xyz"
    bad_file.write_bytes(b"data")
    result = run_stt(str(bad_file))
    assert result["success"] is False
    assert "Unsupported" in result["error"]


def test_missing_api_key_returns_error(tmp_path):
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"\xff\xfb" + b"\x00" * 100)  # stub MP3 header
    result = run_stt(str(audio))
    assert result["success"] is False
    assert "GROQ_API_KEY" in result["error"]


def test_output_always_valid_json():
    result = run_stt("nonexistent.wav")
    assert isinstance(result, dict)
    assert "success" in result

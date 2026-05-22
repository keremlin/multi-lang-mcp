"""Integration tests for tools/python/google_tts.py."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "google_tts.py")
NO_CREDS_ENV = {
    **{k: v for k, v in os.environ.items() if k not in {"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GOOGLE_ACCESS_TOKEN"}},
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "GOOGLE_REFRESH_TOKEN": "",
}


def run_tts(params: dict, env=None) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(params),
        capture_output=True,
        text=True,
        timeout=15,
        env=env or NO_CREDS_ENV,
    )
    return json.loads(result.stdout)


def test_missing_credentials_returns_error():
    result = run_tts({"text": "hello", "output_path": "out.mp3"})
    assert result["success"] is False
    assert "GOOGLE" in result["error"]


def test_empty_text_returns_error():
    result = run_tts({"text": "", "output_path": "out.mp3"})
    assert result["success"] is False
    assert "text" in result["error"].lower()


def test_missing_text_key_returns_error():
    result = run_tts({"output_path": "out.mp3"})
    assert result["success"] is False
    assert "text" in result["error"].lower()


def test_missing_output_path_returns_error():
    result = run_tts({"text": "hello"})
    assert result["success"] is False
    assert "output_path" in result["error"].lower()


def test_invalid_audio_encoding_returns_error():
    result = run_tts({"text": "hello", "output_path": "out.mp3", "audio_encoding": "WAV"})
    assert result["success"] is False
    assert "WAV" in result["error"] or "encoding" in result["error"].lower()


def test_invalid_json_input_returns_error():
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input="not json",
        capture_output=True,
        text=True,
        timeout=15,
        env=NO_CREDS_ENV,
    )
    result = json.loads(proc.stdout)
    assert result["success"] is False
    assert "JSON" in result["error"]


def test_output_always_valid_json():
    result = run_tts({"text": "test", "output_path": "out.mp3"})
    assert isinstance(result, dict)
    assert "success" in result

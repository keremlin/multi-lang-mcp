"""Integration tests for tools/python/youtube_download.py."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "youtube_download.py")
FAKE_YDL = str(Path(__file__).parent / "fixtures" / "fake_yt_dlp")

SAMPLE_URL = "https://www.youtube.com/watch?v=MEHJY2FWwYg"


def run_script(*args, extra_env=None, timeout=30) -> tuple[dict, int]:
    env = {**os.environ}
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return json.loads(result.stdout), result.returncode


def fake_env() -> dict:
    """Prepend the fake yt_dlp stub to PYTHONPATH so it shadows the real one."""
    existing = os.environ.get("PYTHONPATH", "")
    return {"PYTHONPATH": FAKE_YDL + os.pathsep + existing if existing else FAKE_YDL}


# ---------------------------------------------------------------------------
# Argument validation (no network, no yt_dlp)
# ---------------------------------------------------------------------------

def test_no_args_returns_error():
    raw = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = json.loads(raw.stdout)
    assert result["success"] is False
    assert "Usage" in result["error"]


def test_invalid_retries_arg_returns_error():
    result, _ = run_script(SAMPLE_URL, "not-a-number")
    assert result["success"] is False
    assert "Invalid argument" in result["error"]


def test_invalid_timeout_arg_returns_error():
    result, _ = run_script(SAMPLE_URL, "3", "bad-timeout")
    assert result["success"] is False
    assert "Invalid argument" in result["error"]


def test_output_is_always_valid_json():
    raw = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = json.loads(raw.stdout)
    assert isinstance(result, dict)
    assert "success" in result


# ---------------------------------------------------------------------------
# Happy path (fake yt_dlp stub — no network)
# ---------------------------------------------------------------------------

def test_downloads_video_successfully(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_DOWNLOADS_DIR", str(tmp_path))
    result, code = run_script(SAMPLE_URL, extra_env={**fake_env(), "FAKE_DOWNLOADS_DIR": str(tmp_path)})
    # The stub saves to the real Downloads dir; just check the contract
    assert result["success"] is True
    data = result["data"]
    assert data["title"] == "Fake Test Video"
    assert data["url"] == SAMPLE_URL
    assert data["status"] == "completed"
    assert data["file_size_bytes"] > 0
    assert data["file_size_mb"] > 0
    assert data["duration_seconds"] == 120
    assert data["uploader"] == "Fake Channel"
    assert Path(data["saved_to"]).exists()
    assert code == 0


def test_saved_to_is_absolute_path():
    result, _ = run_script(SAMPLE_URL, extra_env=fake_env())
    assert result["success"] is True
    assert Path(result["data"]["saved_to"]).is_absolute()


def test_default_format_is_best():
    result, _ = run_script(SAMPLE_URL, extra_env=fake_env())
    assert result["success"] is True


def test_custom_retries_and_timeout_accepted():
    result, _ = run_script(SAMPLE_URL, "5", "60", extra_env=fake_env())
    assert result["success"] is True


def test_custom_format_accepted():
    result, _ = run_script(SAMPLE_URL, "3", "30", "best[ext=mp4]", extra_env=fake_env())
    assert result["success"] is True


# ---------------------------------------------------------------------------
# Error path (fake yt_dlp raises DownloadError)
# ---------------------------------------------------------------------------

def test_download_error_returns_failure(tmp_path):
    """Inject a fake yt_dlp that always raises DownloadError."""
    error_stub = tmp_path / "yt_dlp" / "__init__.py"
    error_stub.parent.mkdir(parents=True)
    error_stub.write_text(
        "class YoutubeDL:\n"
        "    def __init__(self, o): pass\n"
        "    def __enter__(self): return self\n"
        "    def __exit__(self, *a): pass\n"
        "    def extract_info(self, url, download=True): raise utils.DownloadError('simulated error')\n"
        "    def prepare_filename(self, i): return ''\n"
        "class utils:\n"
        "    class DownloadError(Exception): pass\n"
    )
    existing = os.environ.get("PYTHONPATH", "")
    env = {"PYTHONPATH": str(tmp_path) + os.pathsep + existing if existing else str(tmp_path)}
    result, code = run_script(SAMPLE_URL, extra_env=env)
    assert result["success"] is False
    assert "simulated error" in result["error"]
    assert code != 0

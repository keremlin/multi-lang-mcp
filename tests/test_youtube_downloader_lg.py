import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).parent.parent / "tools" / "python" / "youtube_downloader_lg.py"


def _run(stdin_data: str, timeout: int = 15) -> tuple[dict, int]:
    result = subprocess.run(
        [sys.executable, str(TOOL)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        return json.loads(result.stdout), result.returncode
    except json.JSONDecodeError:
        return {"raw_stdout": result.stdout, "stderr": result.stderr}, result.returncode


def test_no_input():
    out, code = _run("")
    assert code != 0
    assert out["success"] is False
    assert "No input" in out["error"]


def test_invalid_json():
    out, code = _run("not valid json")
    assert code != 0
    assert out["success"] is False
    assert "JSON" in out["error"]


def test_missing_url():
    out, code = _run(json.dumps({}))
    assert code != 0
    assert out["success"] is False
    assert "url" in out["error"]


def test_invalid_crf():
    out, code = _run(json.dumps({"url": "https://youtu.be/x", "crf": 99}))
    assert code != 0
    assert out["success"] is False
    assert "crf" in out["error"].lower()


def test_invalid_preset():
    out, code = _run(json.dumps({"url": "https://youtu.be/x", "preset": "godspeed"}))
    assert code != 0
    assert out["success"] is False
    assert "preset" in out["error"].lower()

"""Integration tests for tools/python/download_file.py."""
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "tools" / "python" / "download_file.py")


def run_script(*args, timeout=30) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return json.loads(result.stdout)


class _StaticHandler(http.server.BaseHTTPRequestHandler):
    """Serves self.server.file_content at any GET path."""

    def do_GET(self):
        content = self.server.file_content
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


class _NotFoundHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def _start_server(handler_class, file_content=b""):
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_class)
    server.file_content = file_content
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, port


@pytest.fixture
def file_server():
    # Large enough to hit multiple 25% milestones
    content = b"x" * (256 * 1024)  # 256 KB
    server, port = _start_server(_StaticHandler, content)
    yield f"http://127.0.0.1:{port}/file.bin", content
    server.shutdown()


@pytest.fixture
def not_found_server():
    server, port = _start_server(_NotFoundHandler)
    yield f"http://127.0.0.1:{port}/missing.bin"
    server.shutdown()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_downloads_file_successfully(file_server, tmp_path):
    url, expected = file_server
    save_path = str(tmp_path / "out.bin")

    result = run_script(url, save_path)

    assert result["success"] is True
    data = result["data"]
    assert data["url"] == url
    assert Path(save_path).read_bytes() == expected
    assert data["bytes_downloaded"] == len(expected)
    assert data["progress_percent"] == 100.0
    assert 100 in data["progress_milestones"]


def test_creates_parent_directories(file_server, tmp_path):
    url, _ = file_server
    save_path = str(tmp_path / "a" / "b" / "c" / "nested.bin")

    result = run_script(url, save_path)

    assert result["success"] is True
    assert Path(save_path).exists()


def test_progress_milestones_present(file_server, tmp_path):
    url, _ = file_server
    result = run_script(url, str(tmp_path / "out.bin"))

    assert result["success"] is True
    milestones = result["data"]["progress_milestones"]
    assert isinstance(milestones, list)
    assert 100 in milestones


def test_saved_to_is_absolute_path(file_server, tmp_path):
    url, _ = file_server
    result = run_script(url, str(tmp_path / "out.bin"))

    assert result["success"] is True
    assert Path(result["data"]["saved_to"]).is_absolute()


# ---------------------------------------------------------------------------
# Error cases
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


def test_only_one_arg_returns_error():
    raw = subprocess.run(
        [sys.executable, SCRIPT, "http://example.com/file"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = json.loads(raw.stdout)
    assert result["success"] is False


def test_invalid_url_scheme_returns_error(tmp_path):
    result = run_script("ftp://example.com/file.txt", str(tmp_path / "out.txt"))
    assert result["success"] is False
    assert "http" in result["error"].lower()


def test_http_404_returns_error(not_found_server, tmp_path):
    result = run_script(not_found_server, str(tmp_path / "out.bin"))
    assert result["success"] is False
    assert "404" in result["error"]


def test_connection_refused_returns_error(tmp_path):
    # Port 1 is almost universally closed/refused
    result = run_script("http://127.0.0.1:1/file.txt", str(tmp_path / "out.txt"), timeout=15)
    assert result["success"] is False
    assert result["error"]


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

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

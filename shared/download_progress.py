"""
IPC bridge between download tools and the Download Manager UI.

Tools call: new_download() → update() → complete() / fail()
UI polls:   data/downloads_progress.json every 500 ms
"""
import json
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_PROGRESS_FILE = _ROOT / "data" / "downloads_progress.json"
_UI_SCRIPT = _ROOT / "ui" / "download_manager_ui.py"
_UI_PORT = 37842
_MAX_AGE_H = 24


def _ensure_data_dir():
    _PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    try:
        if _PROGRESS_FILE.exists():
            return json.loads(_PROGRESS_FILE.read_text("utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict):
    _ensure_data_dir()
    _PROGRESS_FILE.write_text(json.dumps(data, indent=2), "utf-8")


def _purge_old(data: dict) -> dict:
    cutoff = time.time() - _MAX_AGE_H * 3600
    return {k: v for k, v in data.items() if v.get("updated_at", 0) > cutoff}


def new_download(tool: str, name: str = "") -> str:
    """Register a new download, launch the UI, and return a download_id."""
    dl_id = str(uuid.uuid4())
    data = _purge_old(_load())
    data[dl_id] = {
        "tool": tool,
        "name": name,
        "status": "starting",
        "pct": 0,
        "started_at": time.time(),
        "updated_at": time.time(),
    }
    _save(data)
    _launch_ui()
    return dl_id


def update(dl_id: str, **kwargs):
    """Write any progress fields for a download."""
    data = _load()
    if dl_id not in data:
        data[dl_id] = {}
    data[dl_id].update(kwargs)
    data[dl_id]["updated_at"] = time.time()
    _save(data)


def complete(dl_id: str, **kwargs):
    update(dl_id, status="completed", pct=100, **kwargs)


def fail(dl_id: str, error: str):
    update(dl_id, status="error", error=error)


# ── UI launcher ───────────────────────────────────────────────────────────────

def _is_ui_running() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", _UI_PORT))
        s.close()
        return True
    except OSError:
        return False


def _launch_ui():
    try:
        if _is_ui_running():
            return
        _ensure_data_dir()
        flags = 0
        python = sys.executable
        if sys.platform == "win32":
            flags = (
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )
            # pythonw.exe suppresses the console at the process level too
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            if pythonw.exists():
                python = str(pythonw)
        subprocess.Popen(
            [python, str(_UI_SCRIPT)],
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # UI launch is best-effort; never block the download

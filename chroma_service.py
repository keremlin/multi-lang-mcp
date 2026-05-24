"""Windows Service wrapper for the ChromaDB standalone vector database.

Usage (run as Administrator):
    python chroma_service.py install    # register service
    python chroma_service.py start      # start it
    python chroma_service.py stop       # stop it
    python chroma_service.py remove     # unregister
    python chroma_service.py restart    # restart

Or use install_service.ps1 / uninstall_service.ps1 which manage both
ChromaDB and the MCP server together.
"""
import os
import subprocess
import sys
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager

PROJECT_ROOT = Path(__file__).parent.resolve()
CHROMA = str(PROJECT_ROOT / ".venv" / "Scripts" / "chroma.exe")
DATA_PATH = str(PROJECT_ROOT / "data" / "chromadb")

# Read from .env if present; fall back to defaults
try:
    from dotenv import dotenv_values
    _env = dotenv_values(PROJECT_ROOT / ".env")
except Exception:
    _env = {}

HOST = _env.get("CHROMA_HOST") or os.environ.get("CHROMA_HOST", "127.0.0.1")
PORT = _env.get("CHROMA_PORT") or os.environ.get("CHROMA_PORT", "8001")


class ChromaDBService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ChromaDB"
    _svc_display_name_ = "ChromaDB Vector Database"
    _svc_description_ = "ChromaDB standalone vector database — HTTP on port 8001"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._process:
            self._process.terminate()
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        os.makedirs(DATA_PATH, exist_ok=True)
        self._process = subprocess.Popen(
            [CHROMA, "run", "--host", HOST, "--port", PORT, "--path", DATA_PATH],
            cwd=str(PROJECT_ROOT),
        )
        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ChromaDBService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(ChromaDBService)

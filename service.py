"""Windows Service wrapper for the Multi-Language MCP Server.

Usage (run as Administrator):
    python service.py install    # register service
    python service.py start      # start it
    python service.py stop       # stop it
    python service.py remove     # unregister
    python service.py restart    # restart
    python service.py status     # check status

Or use install_service.ps1 / uninstall_service.ps1 which also update
Claude Code MCP registration automatically.
"""
import subprocess
import sys
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager

PROJECT_ROOT = Path(__file__).parent.resolve()
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
SERVER = str(PROJECT_ROOT / "server.py")
HOST = "127.0.0.1"
PORT = 8080


class MCPServerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "MultiLangMCP"
    _svc_display_name_ = "Multi-Language MCP Server"
    _svc_description_ = "FastMCP multi-language AI tool server — SSE on port 8080"

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
        self._process = subprocess.Popen(
            [PYTHON, SERVER, "--transport", "sse", "--host", HOST, "--port", str(PORT)],
            cwd=str(PROJECT_ROOT),
        )
        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(MCPServerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(MCPServerService)

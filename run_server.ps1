<#
.SYNOPSIS
    Start the Multi-Language MCP server in SSE mode (development / foreground).
.PARAMETER Port
    Port to listen on (default: 8080).
.PARAMETER Host
    Host to bind to (default: 127.0.0.1).
.EXAMPLE
    .\run_server.ps1
    .\run_server.ps1 -Port 9000
#>
param(
    [int]$Port    = 8080,
    [string]$Host = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host ""
Write-Host "Multi-Language MCP Server" -ForegroundColor Cyan
Write-Host "  Transport : SSE"
Write-Host "  Endpoint  : http://${Host}:${Port}/sse"
Write-Host "  Logs      : $root\logs\server.log"
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

& $python "$root\server.py" --transport sse --host $Host --port $Port

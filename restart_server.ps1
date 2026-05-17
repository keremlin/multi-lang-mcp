<#
.SYNOPSIS
    Stop the running MCP server and start it again in SSE mode.
    Use this after code changes during development.
.PARAMETER Port
    Port to listen on (default: 8080).
.PARAMETER Host
    Host to bind to (default: 127.0.0.1).
.EXAMPLE
    .\restart_server.ps1
    .\restart_server.ps1 -Port 9000
#>
param(
    [int]$Port      = 8080,
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Multi-Language MCP Server - Restart" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# -- 1. Stop ------------------------------------------------------------------

Write-Host ""
Write-Host "[Stopping]" -ForegroundColor Yellow
$stopped = $false

$svc = Get-Service -Name "MultiLangMCP" -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "  Stopping MultiLangMCP Windows service..." -ForegroundColor Yellow
    Stop-Service -Name "MultiLangMCP" -Force -ErrorAction Stop
    Write-Host "  Service stopped." -ForegroundColor Green
    $stopped = $true
}

$procs = Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*server.py*" }

if ($procs) {
    foreach ($p in $procs) {
        Write-Host "  Stopping standalone server (PID $($p.ProcessId))..." -ForegroundColor Yellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  Standalone process stopped." -ForegroundColor Green
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "  No running server found - starting fresh." -ForegroundColor Gray
}

# -- 2. Wait for port to free -------------------------------------------------

Write-Host ""
Write-Host "[Waiting for port $Port to free]" -ForegroundColor Yellow

$maxWait = 10
$waited  = 0
while ($waited -lt $maxWait) {
    $inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $inUse) { break }
    Start-Sleep -Seconds 1
    $waited++
}

if ($waited -ge $maxWait) {
    Write-Warning "Port $Port still in use after ${maxWait}s - starting anyway."
} else {
    Write-Host "  Port $Port is free." -ForegroundColor Green
}

# -- 3. Start -----------------------------------------------------------------

Write-Host ""
Write-Host "[Starting]" -ForegroundColor Green
Write-Host "  Transport : SSE"
Write-Host "  Endpoint  : http://${BindHost}:${Port}/sse"
Write-Host "  Logs      : $root\logs\server.log"
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

& $python "$root\server.py" --transport sse --host $BindHost --port $Port

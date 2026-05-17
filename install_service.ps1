<#
.SYNOPSIS
    Install Multi-Language MCP Server as a Windows service.
.DESCRIPTION
    Must be run as Administrator.
    - Registers the service via pywin32 (service.py)
    - Starts the service
    - Updates Claude Code MCP registration to SSE transport
    - Runs server_status.ps1 to confirm
#>

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# Stop existing service if already installed
$existing = Get-Service -Name "MultiLangMCP" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing MultiLangMCP service..." -ForegroundColor Yellow
    if ($existing.Status -eq "Running") { Stop-Service "MultiLangMCP" -Force }
    & $python "$root\service.py" remove
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "Installing MultiLangMCP Windows service..." -ForegroundColor Cyan
& $python "$root\service.py" install
Start-Sleep -Seconds 1

Write-Host "Starting service..." -ForegroundColor Cyan
Start-Service -Name "MultiLangMCP"
Start-Sleep -Seconds 4

$svc = Get-Service -Name "MultiLangMCP"
if ($svc.Status -ne "Running") {
    Write-Error "Service failed to start. Open Windows Event Viewer → Windows Logs → Application for details."
    exit 1
}
Write-Host "Service is running." -ForegroundColor Green

Write-Host ""
Write-Host "Updating Claude Code MCP registration → SSE transport..." -ForegroundColor Cyan
claude mcp remove multi-lang-mcp -s user 2>$null
claude mcp add -s user --transport sse multi-lang-mcp http://127.0.0.1:8080/sse

Write-Host ""
& "$root\server_status.ps1"

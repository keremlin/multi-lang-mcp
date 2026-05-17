<#
.SYNOPSIS
    Stop the MCP server — handles both Windows service mode and standalone mode.
#>

$root = $PSScriptRoot
$stopped = $false

# 1. Try Windows service
$svc = Get-Service -Name "MultiLangMCP" -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "Stopping MultiLangMCP Windows service..." -ForegroundColor Yellow
    Stop-Service -Name "MultiLangMCP" -Force -ErrorAction Stop
    Write-Host "Service stopped." -ForegroundColor Green
    $stopped = $true
}

# 2. Fall back: kill standalone python process running server.py
$procs = Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*server.py*" }

if ($procs) {
    foreach ($p in $procs) {
        Write-Host "Stopping standalone server (PID $($p.ProcessId))..." -ForegroundColor Yellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Standalone process stopped." -ForegroundColor Green
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "No running MCP server found." -ForegroundColor Gray
}

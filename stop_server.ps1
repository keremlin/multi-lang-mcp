<#
.SYNOPSIS
    Stop the MCP server — handles both Windows service mode and standalone mode.
#>

$root = $PSScriptRoot
$stopped = $false

# 1. Stop MultiLangMCP Windows service
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

# 3. Stop ChromaDB Windows service
$chromaSvc = Get-Service -Name "ChromaDB" -ErrorAction SilentlyContinue
if ($chromaSvc -and $chromaSvc.Status -eq "Running") {
    Write-Host "Stopping ChromaDB Windows service..." -ForegroundColor Yellow
    Stop-Service -Name "ChromaDB" -Force -ErrorAction SilentlyContinue
    Write-Host "ChromaDB stopped." -ForegroundColor Green
    $stopped = $true
}

# 4. Fall back: kill standalone chroma.exe process
$chromaProcs = Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "chroma.exe" }

if ($chromaProcs) {
    foreach ($p in $chromaProcs) {
        Write-Host "Stopping standalone ChromaDB (PID $($p.ProcessId))..." -ForegroundColor Yellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Standalone ChromaDB stopped." -ForegroundColor Green
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "No running MCP server or ChromaDB found." -ForegroundColor Gray
}

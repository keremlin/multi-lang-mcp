<#
.SYNOPSIS
    Show the current state of the MCP server and list all registered tools.
#>

$root = $PSScriptRoot
$port = 8080

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Multi-Language MCP Server - Status"    -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Windows Services
Write-Host ""
Write-Host "[Windows Service - ChromaDB]" -ForegroundColor White
$chromaSvc = Get-Service -Name "ChromaDB" -ErrorAction SilentlyContinue
if ($chromaSvc) {
    $color = if ($chromaSvc.Status -eq "Running") { "Green" } else { "Red" }
    Write-Host ("  Status    : {0}" -f $chromaSvc.Status) -ForegroundColor $color
    Write-Host "  StartType : $($chromaSvc.StartType)"
    Write-Host "  Display   : $($chromaSvc.DisplayName)"
} else {
    Write-Host "  Not installed" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[Windows Service - MultiLangMCP]" -ForegroundColor White
$svc = Get-Service -Name "MultiLangMCP" -ErrorAction SilentlyContinue
if ($svc) {
    $color = "Red"
    if ($svc.Status -eq "Running") { $color = "Green" }
    Write-Host ("  Status    : {0}" -f $svc.Status) -ForegroundColor $color
    Write-Host "  StartType : $($svc.StartType)"
    Write-Host "  Display   : $($svc.DisplayName)"
} else {
    Write-Host "  Not installed" -ForegroundColor Gray
}

# 2. Standalone Process
Write-Host ""
Write-Host "[Standalone Process]" -ForegroundColor White
$procs = Get-WmiObject Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*server.py*" }
if ($procs) {
    foreach ($p in $procs) {
        Write-Host "  Running - PID $($p.ProcessId)" -ForegroundColor Green
        Write-Host "  Cmd: $($p.CommandLine)"
    }
} else {
    Write-Host "  Not running" -ForegroundColor Gray
}

# 3. SSE Endpoint Health
Write-Host ""
Write-Host "[SSE Endpoint  http://127.0.0.1:$port]" -ForegroundColor White
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -TimeoutSec 2 -ErrorAction Stop -UseBasicParsing
    Write-Host "  Reachable  HTTP $($resp.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  Not reachable (server may be in stdio mode or not started)" -ForegroundColor Red
}

# 4. Claude Code Registration
Write-Host ""
Write-Host "[Claude Code MCP Registration]" -ForegroundColor White
$mcpInfo = claude mcp get multi-lang-mcp 2>&1
foreach ($line in $mcpInfo) {
    Write-Host "  $line"
}

# 5. Registered Tools
Write-Host ""
Write-Host "[Registered Tools  (config/tools.json)]" -ForegroundColor White
$configPath = Join-Path $root "config\tools.json"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    foreach ($tool in $config.tools) {
        $schemaPath = Join-Path $root "schemas\$($tool.name).input.json"
        $schemaTag = "no schema"
        if (Test-Path $schemaPath) { $schemaTag = "schema OK" }
        Write-Host ("  {0,-22} [{1,-10}]  {2}  ({3})" -f $tool.name, $tool.runtime, $tool.description, $schemaTag)
    }
} else {
    Write-Host "  config/tools.json not found" -ForegroundColor Red
}

# 6. Last 10 log lines
Write-Host ""
Write-Host "[Last 10 log lines  (logs/server.log)]" -ForegroundColor White
$logPath = Join-Path $root "logs\server.log"
if (Test-Path $logPath) {
    Get-Content $logPath -Tail 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
} else {
    Write-Host "  Log file not yet created (server has not run)" -ForegroundColor Gray
}

Write-Host ""

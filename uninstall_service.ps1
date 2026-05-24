<#
.SYNOPSIS
    Stop and remove the MultiLangMCP Windows service.
.DESCRIPTION
    Must be run as Administrator.
    Stops the service, unregisters it, and reverts Claude Code MCP back to
    stdio transport (how it was before install_service.ps1 was run).
#>

#Requires -RunAsAdministrator

$ErrorActionPreference = "SilentlyContinue"
$root   = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Stopping MultiLangMCP service..." -ForegroundColor Yellow
Stop-Service -Name "MultiLangMCP" -Force 2>$null
Start-Sleep -Seconds 2

Write-Host "Removing MultiLangMCP service registration..." -ForegroundColor Yellow
& $python "$root\service.py" remove 2>$null
Start-Sleep -Seconds 1

Write-Host "Stopping ChromaDB service..." -ForegroundColor Yellow
Stop-Service -Name "ChromaDB" -Force 2>$null
Start-Sleep -Seconds 2

Write-Host "Removing ChromaDB service registration..." -ForegroundColor Yellow
& $python "$root\chroma_service.py" remove 2>$null
Start-Sleep -Seconds 1

Write-Host "Reverting Claude Code MCP to stdio transport..." -ForegroundColor Cyan
claude mcp remove multi-lang-mcp -s user 2>$null
claude mcp add -s user multi-lang-mcp -- "$python" "$root\server.py"

Write-Host ""
Write-Host "Done. Both services removed; MCP reverted to stdio mode." -ForegroundColor Green
Write-Host ""
claude mcp get multi-lang-mcp 2>&1

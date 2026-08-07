# LinguaFusion Automated Free Cloudflare Tunnel Launcher
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $ProjectRoot "tools"
$CloudflaredExe = Join-Path $ToolsDir "cloudflared.exe"

if (-not (Test-Path $ToolsDir)) {
    New-Item -ItemType Directory -Path $ToolsDir | Out-Null
}

if (-not (Test-Path $CloudflaredExe)) {
    Write-Host "Downloading free Cloudflare Tunnel executable (one-time setup)..." -ForegroundColor Cyan
    $Url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $Url -OutFile $CloudflaredExe
    Write-Host "Cloudflare executable downloaded successfully." -ForegroundColor Green
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  LinguaFusion HTTPS Cloudflare Tunnel Launcher" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "IMPORTANT: Keep this window OPEN while friends are connected!" -ForegroundColor Yellow
Write-Host "Closing this window will turn off HTTPS remote access." -ForegroundColor Red
Write-Host ""

& $CloudflaredExe tunnel --url http://localhost:8000

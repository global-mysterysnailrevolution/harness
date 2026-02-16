# Run Instagram login locally (where you have a display), then upload session to VPS.
# Usage: .\scripts\vps\igfetch_login_local.ps1 -VpsHost root@100.124.123.68

param([string]$VpsHost = "root@100.124.123.68")

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HarnessRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$WorkDir = Join-Path $env:TEMP "igfetch-login"
$ReelsDir = Join-Path $WorkDir "reels"
$StateDir = Join-Path $WorkDir "state"

Write-Host "=== igfetch local login ===" -ForegroundColor Cyan
Write-Host ""

# 1. Create work dir and fetch reels from VPS (always refresh)
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
Write-Host "Fetching reels scripts from VPS..." -ForegroundColor Yellow
scp -r "${VpsHost}:/opt/harness/igfetch/app/scripts/reels" $WorkDir

# 2. npm install
Push-Location $ReelsDir
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Running npm install..." -ForegroundColor Yellow
        npm install
    }

    # 3. Run login (browser will open)
    $env:IGFETCH_BASE = $WorkDir
    Write-Host ""
    Write-Host "Starting login script - browser will open. Log in to Instagram, then press ENTER in this window." -ForegroundColor Green
    Write-Host ""
    node igfetch_login.js

    # 4. Upload storageState to VPS
    $StateFile = Join-Path $StateDir "storageState.json"
    if (Test-Path $StateFile) {
        Write-Host ""
        Write-Host "Uploading session to VPS..." -ForegroundColor Yellow
        ssh $VpsHost "mkdir -p /opt/harness/igfetch/state"
        scp $StateFile "${VpsHost}:/opt/harness/igfetch/state/storageState.json"
        ssh $VpsHost "chown igfetch:igfetch /opt/harness/igfetch/state/storageState.json"
        Write-Host "Done. Session saved on VPS." -ForegroundColor Green
    } else {
        Write-Host "ERROR: storageState.json not created" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

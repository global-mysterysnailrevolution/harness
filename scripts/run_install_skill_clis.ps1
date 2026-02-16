# Install OpenClaw skill CLIs (gh, gemini, codex) inside the container.
# Run from harness root. Works locally (docker exec) or via SSH to VPS.
#
# Usage:
#   .\scripts\run_install_skill_clis.ps1                    # Local (Docker on Windows)
#   .\scripts\run_install_skill_clis.ps1 -VpsHost root@100.124.123.68
#   .\scripts\run_install_skill_clis.ps1 -VpsHost user@vps -Container openclaw-kx9d-openclaw-1

param(
    [string]$VpsHost = "",
    [string]$Container = "openclaw-kx9d-openclaw-1"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HarnessRoot = Split-Path -Parent $ScriptDir
$InstallScript = Join-Path $HarnessRoot "scripts\vps\install_openclaw_skill_clis.sh"

if (-not (Test-Path $InstallScript)) {
    Write-Host "Install script not found: $InstallScript" -ForegroundColor Red
    exit 1
}

$scriptContent = (Get-Content $InstallScript -Raw) -replace "`r`n", "`n"
if ($VpsHost) {
    Write-Host "Piping install script to $VpsHost via SSH..." -ForegroundColor Cyan
    $scriptContent | ssh $VpsHost "docker exec -i $Container bash -s"
} else {
    Write-Host "Running install inside local container: $Container" -ForegroundColor Cyan
    $scriptContent | docker exec -i $Container bash -s
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nRestart container to pick up PATH: docker restart $Container" -ForegroundColor Yellow
}

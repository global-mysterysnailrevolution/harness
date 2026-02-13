# OpenClaw setup step - called from bootstrap.ps1
# Usage: .\bootstrap_openclaw.ps1 -TargetDir C:\path -OpenClawToken "sk-xxx"
param(
    [Parameter(Mandatory=$true)]
    [string]$TargetDir,
    [string]$OpenClawToken = ""
)

$ErrorActionPreference = "Stop"
$openclawSetupDone = $false

$doOpenClaw = $false
if ($OpenClawToken) {
    $doOpenClaw = $true
} else {
    $response = Read-Host "Set up OpenClaw? (y/N)"
    $doOpenClaw = ($response -eq "y" -or $response -eq "Y")
    if ($doOpenClaw) {
        $OpenClawToken = Read-Host "OpenClaw token (API key or pairing code - leave blank to configure later)"
    }
}

if (-not $doOpenClaw) { return $false }

# Write token to .env if provided
$envPath = Join-Path $TargetDir ".env"
if ($OpenClawToken) {
    $envContent = @()
    if (Test-Path $envPath) {
        $envContent = Get-Content $envPath -ErrorAction SilentlyContinue
        $envContent = $envContent | Where-Object { $_ -notmatch "^ANTHROPIC_API_KEY=" -and $_ -notmatch "^OPENAI_API_KEY=" -and $_ -notmatch "^OPENCLAW_TOKEN=" }
    }
    if ($OpenClawToken -match "^sk-ant-|^sk-proj-") {
        $envContent += "ANTHROPIC_API_KEY=$OpenClawToken"
    } elseif ($OpenClawToken -match "^sk-") {
        $envContent += "OPENAI_API_KEY=$OpenClawToken"
    } else {
        $envContent += "OPENCLAW_TOKEN=$OpenClawToken"
    }
    $envContent | Out-File -FilePath $envPath -Encoding UTF8
    Write-Host "  [OK] Token saved to .env" -ForegroundColor Gray
}

# Ensure OpenClaw config exists
$openclawDir = Join-Path $env:USERPROFILE ".openclaw"
$openclawConfig = Join-Path $openclawDir "openclaw.json"
$openclawWorkspace = Join-Path $openclawDir "workspace"
if (-not (Test-Path $openclawDir)) {
    New-Item -ItemType Directory -Path $openclawDir -Force | Out-Null
}
if (-not (Test-Path $openclawWorkspace)) {
    New-Item -ItemType Directory -Path $openclawWorkspace -Force | Out-Null
}
if (-not (Test-Path $openclawConfig)) {
    $minimalConfig = @{
        agents = @{
            defaults = @{
                workspace = $openclawWorkspace
            }
        }
    } | ConvertTo-Json -Depth 5
    $minimalConfig | Out-File -FilePath $openclawConfig -Encoding UTF8
    Write-Host "  [OK] Created minimal openclaw.json" -ForegroundColor Gray
}

# Run OpenClaw hardening
$setupScript = Join-Path $TargetDir "scripts\openclaw_setup\apply_openclaw_hardening.py"
if (Test-Path $setupScript) {
    try {
        & python $setupScript --config-path $openclawConfig --workspace-path $openclawWorkspace
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] OpenClaw hardening applied" -ForegroundColor Gray
            return $true
        }
    } catch {
        Write-Host "  [WARN] OpenClaw setup skipped (python or script not found)" -ForegroundColor Yellow
    }
}
return $false

# Run OpenClaw setup/hardening. Agent-runnable.
# Usage:
#   .\scripts\run_openclaw_setup.ps1                    # Local
#   .\scripts\run_openclaw_setup.ps1 -WithQmd            # Include QMD MCP
#   .\scripts\run_openclaw_setup.ps1 -VpsHost user@vps   # Remote via SSH

param(
    [string]$VpsHost = "",
    [string]$ConfigPath = "",
    [string]$WorkspacePath = "",
    [switch]$SkipAgentsMd,
    [switch]$WithQmd,
    [string]$QmdMcpUrl = "http://127.0.0.1:8181"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HarnessRoot = Split-Path -Parent $ScriptDir
$SetupScript = Join-Path $HarnessRoot "scripts\openclaw_setup\apply_openclaw_hardening.py"

if (-not (Test-Path $SetupScript)) {
    Write-Host "Setup script not found: $SetupScript" -ForegroundColor Red
    exit 1
}

$args = @()
if ($ConfigPath) { $args += "--config-path", $ConfigPath }
if ($WorkspacePath) { $args += "--workspace-path", $WorkspacePath }
if ($SkipAgentsMd) { $args += "--skip-agents-md" }
if ($WithQmd) { $args += "--with-qmd"; $args += "--qmd-mcp-url", $QmdMcpUrl }

if ($VpsHost) {
    # Remote: copy and run via SSH
    $remotePath = "/opt/harness/apply_openclaw_hardening.py"
    Write-Host "Copying setup script to $VpsHost..." -ForegroundColor Cyan
    scp $SetupScript "${VpsHost}:$remotePath"
    $cmd = "python3 $remotePath"
    if ($ConfigPath) { $cmd += " --config-path $ConfigPath" }
    if ($WorkspacePath) { $cmd += " --workspace-path $WorkspacePath" }
    if ($SkipAgentsMd) { $cmd += " --skip-agents-md" }
    if ($WithQmd) { $cmd += " --with-qmd --qmd-mcp-url $QmdMcpUrl" }
    Write-Host "Running on remote..." -ForegroundColor Cyan
    ssh $VpsHost $cmd
} else {
    # Local
    python $SetupScript @args
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nRestart OpenClaw to apply changes." -ForegroundColor Yellow
}

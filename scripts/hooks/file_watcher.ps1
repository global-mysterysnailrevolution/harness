# File Watcher Hook
# Triggered by Cursor on file changes

param(
    [string]$FilePath = "",
    [string]$EventType = "modified"
)

$ErrorActionPreference = "Continue"
$RepoPath = Get-Location

Write-Host "[File Watcher] Detected: $EventType - $FilePath" -ForegroundColor Cyan

# Check if this is a feature file (not test, not docs)
$isFeatureFile = $true
if ($FilePath -match "(test|spec|__tests__|\.md|\.txt)") {
    $isFeatureFile = $false
}

# If significant feature file change, trigger context priming
if ($isFeatureFile -and $EventType -eq "modified") {
    Write-Host "[File Watcher] Feature file changed - triggering context update" -ForegroundColor Yellow
    
    # Spawn context priming (non-blocking)
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-File",
        "$RepoPath\scripts\workers\context_priming.ps1"
    ) -WindowStyle Hidden
}

# Post-Edit Hook
# Updates context artifacts after significant edits

param(
    [string]$FilePath = ""
)

$ErrorActionPreference = "Continue"
$RepoPath = Get-Location

Write-Host "[Post-Edit] Updating context artifacts..." -ForegroundColor Cyan

# Update context pack if significant change
if ($FilePath -and $FilePath -notmatch "(test|spec|\.md)") {
    Write-Host "[Post-Edit] Significant edit detected - updating context pack" -ForegroundColor Yellow
    
    # Update context pack (non-blocking)
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-Command",
        "& '$RepoPath\scripts\compilers\build_context_pack.py' --repo '$RepoPath'"
    ) -WindowStyle Hidden
}

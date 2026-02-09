# Pre-Commit Hook
# Runs safety checks and memory checkpoint before commit

param()

$ErrorActionPreference = "Continue"
$RepoPath = Get-Location

Write-Host "[Pre-Commit] Running safety checks..." -ForegroundColor Cyan

# Check for secrets
$secretsPattern = @("*.env*", "*secret*", "*token*", "*key*", "*.pem")
$stagedFiles = git diff --cached --name-only 2>&1

if ($LASTEXITCODE -eq 0) {
    foreach ($file in $stagedFiles) {
        foreach ($pattern in $secretsPattern) {
            if ($file -like $pattern) {
                Write-Host "[Pre-Commit] ⚠️  WARNING: Potential secret file: $file" -ForegroundColor Yellow
                Write-Host "[Pre-Commit] Review before committing!" -ForegroundColor Yellow
            }
        }
    }
}

# Create memory checkpoint
Write-Host "[Pre-Commit] Creating memory checkpoint..." -ForegroundColor Yellow
& "$RepoPath\scripts\workers\memory_extraction.ps1" -ContextRemaining 5000 -ContextTotal 10000 2>&1 | Out-Null

Write-Host "[Pre-Commit] ✓ Checks complete" -ForegroundColor Green

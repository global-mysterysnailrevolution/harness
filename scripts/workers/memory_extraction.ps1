# Memory Extraction Worker
# Triggered automatically when context approaches limit (15% remaining)

param(
    [string]$RepoPath = ".",
    [int]$ContextRemaining = 0,
    [int]$ContextTotal = 0
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

$threshold = 0.15 # 15%
$contextPercent = if ($ContextTotal -gt 0) { $ContextRemaining / $ContextTotal } else { 0 }

Write-Host "[Memory Extraction] Context: $ContextRemaining/$ContextTotal ($([math]::Round($contextPercent * 100, 1))%)" -ForegroundColor Cyan

if ($contextPercent -gt $threshold -and $contextPercent -lt 0.5) {
    Write-Host "[Memory Extraction] Threshold not reached yet" -ForegroundColor Yellow
    exit 0
}

# Lock file
$lockFile = "$RepoPath\ai\_locks\memory_extraction.lock"
$cooldownFile = "$RepoPath\ai\_locks\memory_cooldown.txt"

# Check cooldown (prevent multiple triggers)
if (Test-Path $cooldownFile) {
    $cooldownTime = Get-Content $cooldownFile
    $cooldownDate = [DateTime]::Parse($cooldownTime)
    if ((Get-Date) -lt $cooldownDate.AddMinutes(5)) {
        Write-Host "[Memory Extraction] In cooldown period" -ForegroundColor Yellow
        exit 0
    }
}

function Acquire-Lock {
    $attempts = 0
    while (Test-Path $lockFile -and $attempts -lt 60) {
        Start-Sleep -Seconds 1
        $attempts++
    }
    if (Test-Path $lockFile) {
        return $false
    }
    "$$" | Out-File -FilePath $lockFile -Encoding UTF8
    return $true
}

function Release-Lock {
    if (Test-Path $lockFile) {
        Remove-Item $lockFile -Force
    }
}

if (-not (Acquire-Lock)) {
    Write-Host "[Memory Extraction] Another extraction in progress" -ForegroundColor Yellow
    exit 1
}

try {
    Write-Host "[Memory Scribe] Creating memory checkpoint..." -ForegroundColor Yellow

    # Append to raw memory log (append-only for safety)
    $memoryLog = "$RepoPath\ai\memory\raw_memory.log"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    "`n=== Memory Checkpoint: $timestamp ===" | Out-File -FilePath $memoryLog -Append -Encoding UTF8
    "Context: $ContextRemaining/$ContextTotal ($([math]::Round($contextPercent * 100, 1))%)" | Out-File -FilePath $memoryLog -Append -Encoding UTF8
    "" | Out-File -FilePath $memoryLog -Append -Encoding UTF8
    
    # Compile memory log into WORKING_MEMORY.md
    & "$RepoPath\scripts\compilers\memory_checkpoint.py" --input $memoryLog --output "$RepoPath\ai\memory\WORKING_MEMORY.md" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        node "$RepoPath\scripts\compilers\memory_checkpoint.js" --input $memoryLog --output "$RepoPath\ai\memory\WORKING_MEMORY.md" 2>&1 | Out-Null
    }

    # Extract decisions to DECISIONS.md
    & "$RepoPath\scripts\compilers\memory_checkpoint.py" --decisions --input $memoryLog --output "$RepoPath\ai\memory\DECISIONS.md" 2>&1 | Out-Null

    # Set cooldown
    (Get-Date).ToString() | Out-File -FilePath $cooldownFile -Encoding UTF8

    Write-Host "[Memory Extraction] Complete!" -ForegroundColor Green
    Write-Host "  ✓ WORKING_MEMORY.md" -ForegroundColor Gray
    Write-Host "  ✓ DECISIONS.md" -ForegroundColor Gray
    Write-Host "  ✓ Cooldown active (5 minutes)" -ForegroundColor Gray

} finally {
    Release-Lock
}

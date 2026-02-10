# Context Priming Worker
# Runs in parallel to map repo, research, and create implementation plan

param(
    [string]$FeatureName = "",
    [string]$RepoPath = "."
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "[Context Priming] Starting parallel workers..." -ForegroundColor Cyan

# Lock file for coordination
$lockFile = "$RepoPath\ai\_locks\context_priming.lock"
$lockTimeout = 300 # 5 minutes

function Acquire-Lock {
    $attempts = 0
    while (Test-Path $lockFile -and $attempts -lt $lockTimeout) {
        Start-Sleep -Seconds 1
        $attempts++
    }
    if (Test-Path $lockFile) {
        Write-Host "[Context Priming] Lock timeout - another worker may be running" -ForegroundColor Yellow
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
    exit 1
}

try {
    # 1. Repo Scout - Map structure and insertion points
    Write-Host "[Repo Scout] Mapping repository structure..." -ForegroundColor Yellow
    & "$RepoPath\scripts\compilers\build_repo_map.py" --output "$RepoPath\ai\context\REPO_MAP.md" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # Fallback to Node.js
        node "$RepoPath\scripts\compilers\build_repo_map.js" --output "$RepoPath\ai\context\REPO_MAP.md" 2>&1 | Out-Null
    }

    # 2. Web Researcher - Find docs and implementations (if feature specified)
    if ($FeatureName) {
        Write-Host "[Web Researcher] Searching for feature: $FeatureName..." -ForegroundColor Yellow
        $researchFile = "$RepoPath\ai\context\FEATURE_RESEARCH.md"
        $researchLog = "$RepoPath\ai\research\raw_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
        
        # Append research findings to raw log
        "## Feature Research: $FeatureName`n" | Out-File -FilePath $researchLog -Append -Encoding UTF8
        "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n" | Out-File -FilePath $researchLog -Append -Encoding UTF8
        "`n[Research findings will be appended here]`n" | Out-File -FilePath $researchLog -Append -Encoding UTF8
        
        # Compile research log into feature research
        & "$RepoPath\scripts\compilers\build_context_pack.py" --input $researchLog --output $researchFile 2>&1 | Out-Null
    }

    # 3. Implementation Bridger - Create concrete plan
    Write-Host "[Implementation Bridger] Creating implementation plan..." -ForegroundColor Yellow
    $contextPack = "$RepoPath\ai\context\CONTEXT_PACK.md"
    & "$RepoPath\scripts\compilers\build_context_pack.py" --output $contextPack 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        node "$RepoPath\scripts\compilers\build_context_pack.js" --output $contextPack 2>&1 | Out-Null
    }
    
    # 4. Note: Specialized context building happens on-demand via context_builder.ps1
    # This is called by supervisor before spawning sub-agents

    Write-Host "[Context Priming] Complete!" -ForegroundColor Green
    Write-Host "  ✓ REPO_MAP.md" -ForegroundColor Gray
    if ($FeatureName) {
        Write-Host "  ✓ FEATURE_RESEARCH.md" -ForegroundColor Gray
    }
    Write-Host "  ✓ CONTEXT_PACK.md" -ForegroundColor Gray

} finally {
    Release-Lock
}

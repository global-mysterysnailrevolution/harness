# Context Builder Worker
# Builds specialized context for sub-agents on-demand

param(
    [string]$AgentId = "",
    [string]$TaskDescription = "",
    [string]$AgentRole = "",
    [string]$RepoPath = "."
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "[Context Builder] Building specialized context for agent: $AgentId" -ForegroundColor Cyan

if (-not $AgentId -or -not $TaskDescription -or -not $AgentRole) {
    Write-Host "[Context Builder] Error: AgentId, TaskDescription, and AgentRole required" -ForegroundColor Red
    exit 1
}

# Lock file
$lockFile = "$RepoPath\ai\_locks\context_builder_$AgentId.lock"

function Acquire-Lock {
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
    Write-Host "[Context Builder] Another context builder running for this agent" -ForegroundColor Yellow
    exit 1
}

try {
    # Check if context already exists and is fresh
    $existingContext = "$RepoPath\ai\context\specialized\${AgentId}_CONTEXT.md"
    if (Test-Path $existingContext) {
        $fileAge = (Get-Item $existingContext).LastWriteTime
        $ageHours = ((Get-Date) - $fileAge).TotalHours
        
        if ($ageHours -lt 1) {
            Write-Host "[Context Builder] Fresh context exists (age: $([math]::Round($ageHours, 1)) hours)" -ForegroundColor Green
            Release-Lock
            exit 0
        }
    }
    
    # Load existing context files
    $repoMap = "$RepoPath\ai\context\REPO_MAP.md"
    $contextPack = "$RepoPath\ai\context\CONTEXT_PACK.md"
    
    $repoMapArg = if (Test-Path $repoMap) { "--repo-map $repoMap" } else { "" }
    $contextPackArg = if (Test-Path $contextPack) { "--context-pack $contextPack" } else { "" }
    
    # Build specialized context
    Write-Host "[Context Builder] Analyzing requirements..." -ForegroundColor Yellow
    Write-Host "[Context Builder] Fetching documentation..." -ForegroundColor Yellow
    Write-Host "[Context Builder] Cloning reference repos if needed..." -ForegroundColor Yellow
    
    python "$RepoPath\scripts\compilers\build_specialized_context.py" `
        --agent-id $AgentId `
        --task "$TaskDescription" `
        --role $AgentRole `
        --repo $RepoPath `
        $repoMapArg `
        $contextPackArg 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Context Builder] Error building context" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[Context Builder] Complete!" -ForegroundColor Green
    Write-Host "  ✓ Specialized context: $existingContext" -ForegroundColor Gray

} finally {
    Release-Lock
}

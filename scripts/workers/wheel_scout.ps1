# Wheel-Scout Worker
# Performs landscape research to find existing solutions before building

param(
    [string]$ProblemStatement = "",
    [string]$RepoPath = ".",
    [string]$ConstraintsJson = "{}"
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "[Wheel-Scout] Starting landscape research..." -ForegroundColor Cyan

if (-not $ProblemStatement) {
    Write-Host "[Wheel-Scout] Error: Problem statement required" -ForegroundColor Red
    exit 1
}

# Parse constraints
$constraints = @{}
try {
    $constraints = $ConstraintsJson | ConvertFrom-Json | ConvertTo-Hashtable
} catch {
    Write-Host "[Wheel-Scout] Warning: Invalid constraints JSON, using empty" -ForegroundColor Yellow
}

# Lock file
$lockFile = "$RepoPath\ai\_locks\wheel_scout.lock"

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
    Write-Host "[Wheel-Scout] Another Wheel-Scout in progress" -ForegroundColor Yellow
    exit 1
}

try {
    # Check cache first
    Write-Host "[Wheel-Scout] Checking cache..." -ForegroundColor Yellow
    $cacheResult = python "$RepoPath\scripts\broker\reality_cache.py" --check --problem "$ProblemStatement" --constraints $ConstraintsJson 2>&1
    
    if ($LASTEXITCODE -eq 0 -and $cacheResult -match "Using cached") {
        Write-Host "[Wheel-Scout] Using cached report" -ForegroundColor Green
        Release-Lock
        exit 0
    }
    
    # Perform research
    Write-Host "[Wheel-Scout] Researching existing solutions..." -ForegroundColor Yellow
    
    # Use tool broker to search for tools that can help with research
    $researchTools = python "$RepoPath\scripts\broker\tool_broker.py" search --query "web search github search" --max-results 5 2>&1
    
    # Research steps (would use actual tools in production):
    # 1. Web search for existing solutions
    # 2. GitHub repo search
    # 3. Documentation research
    # 4. SOTA paper search
    
    # For now, create a template report structure
    $reportData = @{
        problem_statement = $ProblemStatement
        must_have_capabilities = @()
        constraints = $constraints
        closest_existing_solutions = @()
        state_of_the_art = @()
        recommended_path = "extend"
        reuse_plan = @{
            base = ""
            extensions = @()
            integration_steps = @()
        }
        risks = @()
        stop_conditions = @()
    }
    
    # Save raw research data
    $researchLog = "$RepoPath\ai\research\raw_wheel_scout_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    $reportData | ConvertTo-Json -Depth 10 | Out-File -FilePath $researchLog -Encoding UTF8
    
    # Compile landscape report
    Write-Host "[Wheel-Scout] Compiling landscape report..." -ForegroundColor Yellow
    python "$RepoPath\scripts\compilers\landscape_report.py" --input $researchLog --output "$RepoPath\ai\research\landscape_reports\landscape_report.json" --repo $RepoPath 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Wheel-Scout] Error compiling report" -ForegroundColor Red
        exit 1
    }
    
    # Cache the report
    python "$RepoPath\scripts\broker\reality_cache.py" --cache --problem "$ProblemStatement" --constraints $ConstraintsJson --report "$RepoPath\ai\research\landscape_reports\landscape_report.json" 2>&1 | Out-Null
    
    Write-Host "[Wheel-Scout] Complete!" -ForegroundColor Green
    Write-Host "  ✓ Landscape report generated" -ForegroundColor Gray
    Write-Host "  ✓ Report cached for future use" -ForegroundColor Gray

} finally {
    Release-Lock
}

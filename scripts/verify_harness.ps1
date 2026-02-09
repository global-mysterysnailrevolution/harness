# Harness Verification Script
# Golden scenario that demonstrates harness functionality

param(
    [string]$RepoPath = "."
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "`n=== Harness Verification (Golden Scenario) ===" -ForegroundColor Cyan
Write-Host ""

$testsPassed = 0
$testsFailed = 0

function Test-Step {
    param([string]$Name, [scriptblock]$Test)
    
    Write-Host "[TEST] $Name..." -ForegroundColor Yellow -NoNewline
    
    try {
        & $Test
        Write-Host " PASSED" -ForegroundColor Green
        $script:testsPassed++
        return $true
    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "  Error: $_" -ForegroundColor Red
        $script:testsFailed++
        return $false
    }
}

# Test 1: Directory structure exists
Test-Step "Directory structure" {
    $requiredDirs = @(
        "ai\context",
        "ai\memory",
        "ai\tests",
        "ai\research",
        "ai\_locks",
        "scripts\workers",
        "scripts\compilers"
    )
    
    foreach ($dir in $requiredDirs) {
        $fullPath = Join-Path $RepoPath $dir
        if (-not (Test-Path $fullPath)) {
            throw "Directory missing: $dir"
        }
    }
}

# Test 2: Core files exist
Test-Step "Core harness files" {
    $requiredFiles = @(
        "HARNESS_README.md",
        "scripts\workers\context_priming.ps1",
        "scripts\workers\memory_extraction.ps1",
        "scripts\workers\log_monitor.ps1",
        "scripts\workers\test_writer.ps1"
    )
    
    foreach ($file in $requiredFiles) {
        $fullPath = Join-Path $RepoPath $file
        if (-not (Test-Path $fullPath)) {
            throw "File missing: $file"
        }
    }
}

# Test 3: Compilers exist
Test-Step "Deterministic compilers" {
    $compilers = @(
        "scripts\compilers\build_repo_map.py",
        "scripts\compilers\build_context_pack.py",
        "scripts\compilers\memory_checkpoint.py"
    )
    
    foreach ($compiler in $compilers) {
        $fullPath = Join-Path $RepoPath $compiler
        if (-not (Test-Path $fullPath)) {
            throw "Compiler missing: $compiler"
        }
    }
}

# Test 4: Simulate context priming
Test-Step "Context priming (simulated)" {
    $repoMap = Join-Path $RepoPath "ai\context\REPO_MAP.md"
    
    # Run repo map compiler
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python "$RepoPath\scripts\compilers\build_repo_map.py" --repo $RepoPath --output "ai\context\REPO_MAP.md" 2>&1 | Out-Null
    } elseif (Get-Command node -ErrorAction SilentlyContinue) {
        node "$RepoPath\scripts\compilers\build_repo_map.js" --repo $RepoPath --output "ai\context\REPO_MAP.md" 2>&1 | Out-Null
    } else {
        throw "Python or Node.js required for compilers"
    }
    
    if (-not (Test-Path $repoMap)) {
        throw "REPO_MAP.md not generated"
    }
}

# Test 5: Simulate memory checkpoint
Test-Step "Memory checkpoint (simulated)" {
    $memoryLog = Join-Path $RepoPath "ai\memory\raw_memory.log"
    
    # Create sample memory log
    @"
=== Memory Checkpoint: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===
Context: 1500/10000 (15.0%)

Test checkpoint entry.
Decision: Use Python for compilers.
TODO: Add Node.js fallback.
"@ | Out-File -FilePath $memoryLog -Encoding UTF8
    
    # Run memory checkpoint compiler
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python "$RepoPath\scripts\compilers\memory_checkpoint.py" --input $memoryLog --output "ai\memory\WORKING_MEMORY.md" --repo $RepoPath 2>&1 | Out-Null
        python "$RepoPath\scripts\compilers\memory_checkpoint.py" --input $memoryLog --output "ai\memory\DECISIONS.md" --decisions --repo $RepoPath 2>&1 | Out-Null
    } else {
        throw "Python required for memory checkpoint"
    }
    
    $workingMemory = Join-Path $RepoPath "ai\memory\WORKING_MEMORY.md"
    if (-not (Test-Path $workingMemory)) {
        throw "WORKING_MEMORY.md not generated"
    }
}

# Test 6: Simulate log monitoring (dummy mode)
Test-Step "Log monitoring (dummy mode)" {
    $dummyLog = Join-Path $RepoPath "ai\_locks\dummy_server.log"
    
    # Create dummy log
    @"
Server started at $(Get-Date)
Listening on port 3000
[INFO] Application ready
[ERROR] Test error for verification
"@ | Out-File -FilePath $dummyLog -Encoding UTF8
    
    # Run log sentinel
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python "$RepoPath\scripts\compilers\log_sentinel.py" --input $dummyLog --output "ai\context\LOG_FINDINGS.md" --repo $RepoPath 2>&1 | Out-Null
    } else {
        throw "Python required for log sentinel"
    }
    
    $findings = Join-Path $RepoPath "ai\context\LOG_FINDINGS.md"
    if (-not (Test-Path $findings)) {
        throw "LOG_FINDINGS.md not generated"
    }
}

# Test 7: Platform integration files
Test-Step "Platform integration files" {
    $platformFiles = @(
        ".cursor\hooks.json",
        ".claude\settings.json",
        "CODEX_WORKFLOW.md"
    )
    
    foreach ($file in $platformFiles) {
        $fullPath = Join-Path $RepoPath $file
        if (-not (Test-Path $fullPath)) {
            throw "Platform file missing: $file"
        }
    }
}

# Summary
Write-Host "`n=== Verification Summary ===" -ForegroundColor Cyan
Write-Host "Tests passed: $testsPassed" -ForegroundColor Green
Write-Host "Tests failed: $testsFailed" -ForegroundColor $(if ($testsFailed -eq 0) { "Green" } else { "Red" })

if ($testsFailed -eq 0) {
    Write-Host "`n✅ All tests passed! Harness is working correctly." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n❌ Some tests failed. Review errors above." -ForegroundColor Red
    exit 1
}

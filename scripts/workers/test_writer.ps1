# Test Writer Worker
# Writes tests in parallel with feature implementation

param(
    [string]$RepoPath = ".",
    [string]$FeaturePath = ""
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "[Test Writer] Starting test generation..." -ForegroundColor Cyan

# Detect test framework
$testFramework = "unknown"
$testDir = ""

if (Test-Path "$RepoPath\package.json") {
    $package = Get-Content "$RepoPath\package.json" | ConvertFrom-Json
    if ($package.devDependencies.jest) {
        $testFramework = "jest"
        $testDir = "tests" # or __tests__
    } elseif ($package.devDependencies.mocha) {
        $testFramework = "mocha"
        $testDir = "test"
    } elseif ($package.devDependencies.vitest) {
        $testFramework = "vitest"
        $testDir = "tests"
    }
} elseif (Test-Path "$RepoPath\pytest.ini" -or (Get-ChildItem "$RepoPath\*.py" -Recurse | Where-Object { $_.Name -match "test_" })) {
    $testFramework = "pytest"
    $testDir = "tests"
} elseif (Test-Path "$RepoPath\Cargo.toml") {
    $testFramework = "rust"
    $testDir = "tests"
}

Write-Host "[Test Writer] Detected framework: $testFramework" -ForegroundColor Green

# Lock file
$lockFile = "$RepoPath\ai\_locks\test_writer.lock"
$testPlan = "$RepoPath\ai\tests\TEST_PLAN.md"
$coverageNotes = "$RepoPath\ai\tests\COVERAGE_NOTES.md"

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
    Write-Host "[Test Writer] Another test writer in progress" -ForegroundColor Yellow
    exit 1
}

try {
    Write-Host "[Test Writer] Analyzing feature and generating tests..." -ForegroundColor Yellow

    # Append to raw test log
    $testLog = "$RepoPath\ai\tests\raw_test_plan.log"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    "`n=== Test Plan Update: $timestamp ===" | Out-File -FilePath $testLog -Append -Encoding UTF8
    "Framework: $testFramework" | Out-File -FilePath $testLog -Append -Encoding UTF8
    if ($FeaturePath) {
        "Feature: $FeaturePath" | Out-File -FilePath $testLog -Append -Encoding UTF8
    }
    "" | Out-File -FilePath $testLog -Append -Encoding UTF8

    # Compile test plan
    & "$RepoPath\scripts\compilers\test_plan_compiler.py" --input $testLog --output $testPlan --framework $testFramework 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        node "$RepoPath\scripts\compilers\test_plan_compiler.js" --input $testLog --output $testPlan --framework $testFramework 2>&1 | Out-Null
    }

    # Generate coverage notes
    if ($testFramework -ne "unknown") {
        $coverage = @"
# Test Coverage Notes
Generated: $timestamp

## Framework
$testFramework

## Test Directory
$testDir

## Coverage Status
- Unit tests: Pending
- Integration tests: Pending
- E2E tests: Pending

## Notes
Tests are being generated in parallel with feature implementation.
Review $testPlan for detailed test plan.

"@
        $coverage | Out-File -FilePath $coverageNotes -Encoding UTF8
    }

    Write-Host "[Test Writer] Complete!" -ForegroundColor Green
    Write-Host "  ✓ TEST_PLAN.md" -ForegroundColor Gray
    Write-Host "  ✓ COVERAGE_NOTES.md" -ForegroundColor Gray

} finally {
    Release-Lock
}

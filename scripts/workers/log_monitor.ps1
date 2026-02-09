# Log Monitor Worker
# Monitors dev server logs in background, detects anomalies

param(
    [string]$RepoPath = ".",
    [string]$LogPath = "",
    [string]$ServerCommand = ""
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "[Log Monitor] Starting log monitoring..." -ForegroundColor Cyan

# Detect dev server if not specified
if (-not $ServerCommand) {
    # Check common patterns
    if (Test-Path "$RepoPath\package.json") {
        $package = Get-Content "$RepoPath\package.json" | ConvertFrom-Json
        if ($package.scripts.start) {
            $ServerCommand = "npm start"
        } elseif ($package.scripts.dev) {
            $ServerCommand = "npm run dev"
        }
    } elseif (Test-Path "$RepoPath\requirements.txt") {
        $ServerCommand = "python app.py" # Common default
    } elseif (Test-Path "$RepoPath\Cargo.toml") {
        $ServerCommand = "cargo run"
    }
}

if (-not $ServerCommand) {
    Write-Host "[Log Monitor] No dev server detected - running in dummy mode" -ForegroundColor Yellow
    # Create dummy log for testing
    $dummyLog = "$RepoPath\ai\_locks\dummy_server.log"
    "Server started at $(Get-Date)" | Out-File -FilePath $dummyLog -Encoding UTF8
    "Listening on port 3000" | Out-File -FilePath $dummyLog -Append -Encoding UTF8
    $LogPath = $dummyLog
} else {
    Write-Host "[Log Monitor] Detected server: $ServerCommand" -ForegroundColor Green
}

# Determine log path
if (-not $LogPath) {
    # Common log locations
    $possibleLogs = @(
        "$RepoPath\logs\app.log",
        "$RepoPath\*.log",
        "$env:TEMP\server.log"
    )
    foreach ($log in $possibleLogs) {
        if (Test-Path $log) {
            $LogPath = $log
            break
        }
    }
}

if (-not $LogPath) {
    Write-Host "[Log Monitor] No log file found - will tail stdout/stderr" -ForegroundColor Yellow
}

# Lock file
$lockFile = "$RepoPath\ai\_locks\log_monitor.lock"
$findingsFile = "$RepoPath\ai\context\LOG_FINDINGS.md"
$rawLog = "$RepoPath\ai\context\raw_server.log"

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
    Write-Host "[Log Monitor] Already monitoring" -ForegroundColor Yellow
    exit 1
}

try {
    Write-Host "[Log Monitor] Monitoring logs..." -ForegroundColor Yellow
    Write-Host "[Log Monitor] Findings will be written to: $findingsFile" -ForegroundColor Gray

    # Start monitoring (simplified - in production would use proper tailing)
    $anomalyPatterns = @(
        "error", "Error", "ERROR",
        "exception", "Exception", "EXCEPTION",
        "fatal", "Fatal", "FATAL",
        "stack trace", "Stack Trace",
        "warning", "Warning", "WARNING"
    )

    $lineCount = 0
    $anomalyCount = 0
    $anomalies = @()

    if ($LogPath -and (Test-Path $LogPath)) {
        # Monitor existing log file
        Get-Content $LogPath -Tail 100 -Wait | ForEach-Object {
            $line = $_
            $lineCount++
            
            # Append to raw log
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $line" | Out-File -FilePath $rawLog -Append -Encoding UTF8
            
            # Check for anomalies
            foreach ($pattern in $anomalyPatterns) {
                if ($line -match $pattern) {
                    $anomalyCount++
                    $anomalies += @{
                        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                        line = $line
                        pattern = $pattern
                    }
                    break
                }
            }
            
            # Compile findings every 10 anomalies or every 100 lines
            if ($anomalyCount -gt 0 -and ($anomalyCount % 10 -eq 0 -or $lineCount % 100 -eq 0)) {
                & "$RepoPath\scripts\compilers\log_sentinel.py" --input $rawLog --output $findingsFile 2>&1 | Out-Null
            }
        }
    } else {
        # Dummy mode - simulate monitoring
        Write-Host "[Log Monitor] Running in dummy mode - no actual server" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        
        # Create sample findings
        $sampleFindings = @"
# Log Findings
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

## Summary
- Total lines monitored: 0 (dummy mode)
- Anomalies detected: 0
- Server status: Not running (dummy mode)

## Anomalies
None detected (dummy mode).

## Recommendations
1. Start your dev server to enable real log monitoring
2. Configure log path in harness settings if using custom location
3. Review ai/context/raw_server.log for detailed logs

"@
        $sampleFindings | Out-File -FilePath $findingsFile -Encoding UTF8
    }

    Write-Host "[Log Monitor] Monitoring complete" -ForegroundColor Green

} finally {
    Release-Lock
}

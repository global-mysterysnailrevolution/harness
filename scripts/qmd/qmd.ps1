# QMD wrapper for Windows (Bun's qmd uses bash; this runs it via bun)
# Usage: .\qmd.ps1 status | search "query" | embed | mcp ...
$ErrorActionPreference = "Stop"
$env:XDG_CACHE_HOME = if ($env:XDG_CACHE_HOME) { $env:XDG_CACHE_HOME } else { "$env:USERPROFILE\.cache" }
$qmdPath = "$env:USERPROFILE\.bun\install\global\node_modules\qmd\src\qmd.ts"
if (-not (Test-Path $qmdPath)) {
    $qmdPath = "$env:USERPROFILE\.bun\bin\..\install\global\node_modules\qmd\src\qmd.ts"
}
if (-not (Test-Path $qmdPath)) {
    Write-Error "QMD not found. Install with: bun install -g github:tobi/qmd"
    exit 1
}
& "$env:USERPROFILE\.bun\bin\bun.exe" $qmdPath @args

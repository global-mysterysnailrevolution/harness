# Start QMD MCP HTTP server for OpenClaw
# QMD exposes: qmd_search, qmd_vector_search, qmd_deep_search, qmd_get, qmd_multi_get, qmd_status
# Default port: 8181. OpenClaw connects to http://127.0.0.1:8181/mcp
$ErrorActionPreference = "Stop"
$env:XDG_CACHE_HOME = if ($env:XDG_CACHE_HOME) { $env:XDG_CACHE_HOME } else { "$env:USERPROFILE\.cache" }
$qmdPath = "$env:USERPROFILE\.bun\install\global\node_modules\qmd\src\qmd.ts"
if (-not (Test-Path $qmdPath)) {
    Write-Error "QMD not found. Install with: bun install -g github:tobi/qmd"
    exit 1
}
$bun = "$env:USERPROFILE\.bun\bin\bun.exe"
Write-Host "Starting QMD MCP server at http://127.0.0.1:8181/mcp"
Write-Host "Press Ctrl+C to stop."
& $bun $qmdPath mcp --http

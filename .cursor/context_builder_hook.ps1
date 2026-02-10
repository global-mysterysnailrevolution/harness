# Cursor Context Builder Hook
# Builds specialized context before agent spawn

param(
    [string]$AgentId = "",
    [string]$AgentRole = "",
    [string]$TaskDescription = "",
    [string]$RepoPath = "."
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

Write-Host "[Cursor Context Builder] Building context for $AgentId..." -ForegroundColor Cyan

if (-not $AgentId -or -not $AgentRole -or -not $TaskDescription) {
    Write-Host "[Cursor Context Builder] Error: All parameters required" -ForegroundColor Red
    exit 1
}

# Build context using context builder worker
& "$RepoPath\scripts\workers\context_builder.ps1" `
    -AgentId $AgentId `
    -TaskDescription $TaskDescription `
    -AgentRole $AgentRole `
    -RepoPath $RepoPath

if ($LASTEXITCODE -eq 0) {
    $contextFile = "$RepoPath\ai\context\specialized\${AgentId}_CONTEXT.md"
    Write-Host "[Cursor Context Builder] Context ready: $contextFile" -ForegroundColor Green
    Write-Output $contextFile
} else {
    Write-Host "[Cursor Context Builder] Error building context" -ForegroundColor Red
    exit 1
}

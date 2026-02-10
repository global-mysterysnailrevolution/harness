# Pre-Spawn Context Hook
# Builds specialized context before agent spawn (used by Cursor/Claude)

param(
    [string]$AgentId = "",
    [string]$AgentRole = "",
    [string]$TaskDescription = "",
    [string]$RepoPath = "."
)

$ErrorActionPreference = "Continue"
$RepoPath = Resolve-Path $RepoPath

if (-not $AgentId -or -not $AgentRole -or -not $TaskDescription) {
    Write-Host "[Pre-Spawn Context] Error: AgentId, AgentRole, and TaskDescription required" -ForegroundColor Red
    exit 1
}

# Call context builder
& "$RepoPath\scripts\workers\context_builder.ps1" `
    -AgentId $AgentId `
    -TaskDescription $TaskDescription `
    -AgentRole $AgentRole `
    -RepoPath $RepoPath

if ($LASTEXITCODE -eq 0) {
    $contextFile = "$RepoPath\ai\context\specialized\${AgentId}_CONTEXT.md"
    Write-Output $contextFile
} else {
    exit 1
}

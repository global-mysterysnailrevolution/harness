# Run MCP stdio-to-HTTP bridges for OpenClaw
# Starts one bridge per MCP server on ports 8101-8104
# Run on VPS: pwsh -File scripts/run_mcp_servers.ps1

$baseDir = $PSScriptRoot
$harnessDir = Split-Path $baseDir
$allowedFsPath = $harnessDir  # Restrict filesystem to harness dir

$servers = @(
    @{
        Name = "filesystem"
        Port = 8101
        Cmd = "npx"
        Args = @("-y", "@modelcontextprotocol/server-filesystem", $allowedFsPath)
    },
    @{
        Name = "fetch"
        Port = 8102
        Cmd = "npx"
        Args = @("-y", "@modelcontextprotocol/server-fetch")
    },
    @{
        Name = "time"
        Port = 8104
        Cmd = "npx"
        Args = @("-y", "@modelcontextprotocol/server-time")
    }
)

# GitHub requires token - add if set
if ($env:GITHUB_PERSONAL_ACCESS_TOKEN) {
    $servers += @{
        Name = "github"
        Port = 8103
        Cmd = "npx"
        Args = @("-y", "@modelcontextprotocol/server-github")
        Env = @{ GITHUB_PERSONAL_ACCESS_TOKEN = $env:GITHUB_PERSONAL_ACCESS_TOKEN }
    }
}

Write-Host "Starting MCP bridges..."
foreach ($s in $servers) {
    $env:MCP_PORT = $s.Port
    $proc = Start-Process -FilePath "node" -ArgumentList @(
        "$baseDir\mcp_stdio_to_http_bridge.js"
    ) -PassThru -NoNewWindow
    Start-Sleep -Seconds 1
    # Actually we need to pass the cmd - the bridge reads from argv
    # Let me fix - we need to spawn with the right args
}

# Simpler: run each bridge in background
$jobs = @()
foreach ($s in $servers) {
    $argList = @("$baseDir\mcp_stdio_to_http_bridge.js", "--port", $s.Port, "--", $s.Cmd) + $s.Args
    $env:MCP_PORT = $s.Port
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "node"
    $psi.Arguments = ($argList -join " ")
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    Write-Host "Started $($s.Name) on port $($s.Port) (PID $($p.Id))"
}

Write-Host "MCP bridges running. Press Ctrl+C to stop."
Wait-Process -Id $p.Id -ErrorAction SilentlyContinue

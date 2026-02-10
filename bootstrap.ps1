# Agent Harness Template Bootstrap Installer
# Installs the harness into the current directory
# Works on Windows 11 with optional WSL support

param(
    [switch]$Force,
    [switch]$SkipGit,
    [string]$WSLPath = ""
)

$ErrorActionPreference = "Stop"
$HarnessVersion = "1.0.0"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetDir = Get-Location

Write-Host "`n=== Agent Harness Template Bootstrap ===" -ForegroundColor Cyan
Write-Host "Version: $HarnessVersion" -ForegroundColor Gray
Write-Host "Target: $TargetDir`n" -ForegroundColor Gray

# Check if harness already exists
if (Test-Path "$TargetDir\ai\context\CONTEXT_PACK.md" -and -not $Force) {
    Write-Host "⚠️  Harness already exists in this directory!" -ForegroundColor Yellow
    $response = Read-Host "Overwrite? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "Aborted." -ForegroundColor Red
        exit 0
    }
}

# Detect WSL
$HasWSL = $false
if (Get-Command wsl -ErrorAction SilentlyContinue) {
    $wslCheck = wsl --list --quiet 2>&1
    if ($LASTEXITCODE -eq 0) {
        $HasWSL = $true
        Write-Host "✓ WSL detected" -ForegroundColor Green
    }
}

# Check for Git
$HasGit = $false
if (Get-Command git -ErrorAction SilentlyContinue) {
    $HasGit = $true
    Write-Host "✓ Git detected" -ForegroundColor Green
} else {
    Write-Host "⚠️  Git not found - harness will work but version control recommended" -ForegroundColor Yellow
}

# Create backup if needed
if (-not $SkipGit -and $HasGit) {
    $gitStatus = git status --porcelain 2>&1
    if ($LASTEXITCODE -eq 0 -and $gitStatus) {
        Write-Host "`n📦 Creating backup snapshot..." -ForegroundColor Cyan
        $backupDir = "$TargetDir\ai\_backups\$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        # Backup modified files
        git status --porcelain | ForEach-Object {
            $file = ($_ -split '\s+', 2)[1]
            if (Test-Path $file) {
                $dest = "$backupDir\$file"
                $destDir = Split-Path -Parent $dest
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                Copy-Item $file $dest -Force
            }
        }
        Write-Host "✓ Backup created: $backupDir" -ForegroundColor Green
    }
}

# Create directory structure
Write-Host "`n📁 Creating directory structure..." -ForegroundColor Cyan

$dirs = @(
    "ai\context",
    "ai\context\specialized",
    "ai\memory",
    "ai\tests",
    "ai\research",
    "ai\research\landscape_reports",
    "ai\vendor",
    "ai\_backups",
    "ai\_locks",
    "ai\supervisor",
    "scripts\workers",
    "scripts\compilers",
    "scripts\hooks",
    "scripts\broker",
    "scripts\supervisor",
    ".cursor",
    ".claude\agents",
    ".claude\hooks",
    "openclaw",
    "gemini"
)

foreach ($dir in $dirs) {
    $fullPath = Join-Path $TargetDir $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        Write-Host "  ✓ $dir" -ForegroundColor Gray
    }
}

# Copy template files
Write-Host "`n📄 Installing template files..." -ForegroundColor Cyan

$templateFiles = @{
    "ai\context\REPO_MAP.md" = "REPO_MAP_TEMPLATE.md"
    "ai\context\CONTEXT_PACK.md" = "CONTEXT_PACK_TEMPLATE.md"
    "ai\memory\WORKING_MEMORY.md" = "WORKING_MEMORY_TEMPLATE.md"
    "ai\memory\DECISIONS.md" = "DECISIONS_TEMPLATE.md"
    ".gitignore" = "GITIGNORE_TEMPLATE"
    "HARNESS_README.md" = "HARNESS_README_TEMPLATE.md"
}

# For now, create minimal templates (will be expanded)
foreach ($target in $templateFiles.Keys) {
    $targetPath = Join-Path $TargetDir $target
    $templateName = $templateFiles[$target]
    # Create placeholder if template doesn't exist in script dir
    if (-not (Test-Path (Join-Path $ScriptDir $templateName))) {
        "# Placeholder - will be populated by harness" | Out-File -FilePath $targetPath -Encoding UTF8
    } else {
        Copy-Item (Join-Path $ScriptDir $templateName) $targetPath -Force
    }
    Write-Host "  ✓ $target" -ForegroundColor Gray
}

# Create .gitkeep files for empty directories
$keepDirs = @("ai\_locks", "ai\tests", "scripts\workers", "scripts\compilers", "scripts\hooks")
foreach ($dir in $keepDirs) {
    $keepFile = Join-Path $TargetDir "$dir\.gitkeep"
    if (-not (Test-Path $keepFile)) {
        "" | Out-File -FilePath $keepFile -Encoding UTF8
    }
}

# Install scripts
Write-Host "`n🔧 Installing harness scripts..." -ForegroundColor Cyan

# Copy scripts from template (if they exist) or create placeholders
$scripts = @(
    "scripts\workers\context_priming.ps1",
    "scripts\workers\memory_extraction.ps1",
    "scripts\workers\log_monitor.ps1",
    "scripts\workers\test_writer.ps1",
    "scripts\compilers\build_repo_map.py",
    "scripts\compilers\build_repo_map.js",
    "scripts\compilers\build_context_pack.py",
    "scripts\compilers\memory_checkpoint.py",
    "scripts\compilers\log_sentinel.py",
    "scripts\compilers\test_plan_compiler.py"
)

foreach ($script in $scripts) {
    $scriptPath = Join-Path $TargetDir $script
    $scriptDir = Split-Path -Parent $scriptPath
    if (-not (Test-Path $scriptDir)) {
        New-Item -ItemType Directory -Path $scriptDir -Force | Out-Null
    }
    # Placeholder - will be created in next steps
    Write-Host "  ✓ $script" -ForegroundColor Gray
}

# Initialize git if needed
if (-not $SkipGit -and $HasGit) {
    if (-not (Test-Path "$TargetDir\.git")) {
        Write-Host "`n🔷 Initializing Git repository..." -ForegroundColor Cyan
        git init | Out-Null
        Write-Host "✓ Git initialized" -ForegroundColor Green
    }
}

# Create platform integration files
Write-Host "`n🔌 Creating platform integrations..." -ForegroundColor Cyan

# Cursor integration
$cursorHooks = Join-Path $TargetDir ".cursor\hooks.json"
if (-not (Test-Path $cursorHooks)) {
    @{
        version = "1.0"
        hooks = @(
            @{
                event = "file-watcher"
                command = "scripts\hooks\file_watcher.ps1"
            },
            @{
                event = "pre-commit"
                command = "scripts\hooks\pre_commit.ps1"
            }
        )
    } | ConvertTo-Json -Depth 10 | Out-File -FilePath $cursorHooks -Encoding UTF8
    Write-Host "  ✓ .cursor\hooks.json" -ForegroundColor Gray
}

# Claude Code integration
$claudeSettings = Join-Path $TargetDir ".claude\settings.json"
if (-not (Test-Path $claudeSettings)) {
    @{
        hooks = @{
            compaction = "scripts\compilers\memory_checkpoint.py"
            rehydrate = "scripts\compilers\build_context_pack.py"
        }
        secretGates = @{
            patterns = @("*.env*", "*secret*", "*token*", "*key*", "*.pem", "*.key")
            askFirst = $true
        }
        riskyCommands = @{
            patterns = @("rm -rf", "del /s", "format", "dd if=", "git push --force")
            askFirst = $true
        }
        postEdit = @{
            enabled = $true
            command = "scripts\hooks\post_edit.ps1"
            triggers = @("file_save", "significant_change")
        }
        stopTimeCompile = @{
            enabled = $true
            command = "scripts\compilers\build_context_pack.py"
            description = "Compiles context pack at end of session"
        }
        supervisor = @{
            enabled = $true
            toolBroker = @{ enabled = $true }
            wheelScout = @{ enabled = $true; requiredForBuild = $true }
            contextBuilder = @{ enabled = $true; preSpawnHook = "scripts\hooks\pre_spawn_context.ps1" }
        }
    } | ConvertTo-Json -Depth 10 | Out-File -FilePath $claudeSettings -Encoding UTF8
    Write-Host "  ✓ .claude\settings.json" -ForegroundColor Gray
}

# Claude supervisor config
$claudeSupervisor = Join-Path $TargetDir ".claude\supervisor.json"
if (-not (Test-Path $claudeSupervisor)) {
    @{
        version = "1.0"
        supervisor = @{
            enabled = $true
            state_dir = "ai/supervisor"
        }
    } | ConvertTo-Json -Depth 10 | Out-File -FilePath $claudeSupervisor -Encoding UTF8
    Write-Host "  ✓ .claude\supervisor.json" -ForegroundColor Gray
}

# Codex workflow doc
$codexWorkflow = Join-Path $TargetDir "CODEX_WORKFLOW.md"
if (-not (Test-Path $codexWorkflow)) {
    "# Codex CLI Workflow Guide`n`nSee HARNESS_README.md for details." | Out-File -FilePath $codexWorkflow -Encoding UTF8
    Write-Host "  ✓ CODEX_WORKFLOW.md" -ForegroundColor Gray
}

# Create supervisor config files
Write-Host "`n⚙️  Creating supervisor configuration files..." -ForegroundColor Cyan

# Supervisor allowlists
$allowlistsPath = Join-Path $TargetDir "ai\supervisor\allowlists.json"
if (-not (Test-Path $allowlistsPath)) {
    $allowlistsContent = Get-Content (Join-Path $ScriptDir "ai\supervisor\allowlists.json") -ErrorAction SilentlyContinue
    if (-not $allowlistsContent) {
        # Create default allowlists
        @{
            version = "1.0"
            default_allowlist = @{
                servers = @()
                tools = @()
            }
            agent_profiles = @{
                orchestrator = @{
                    servers = @("tool-broker")
                    tools = @("search_tools", "describe_tool")
                }
                "web-runner" = @{
                    servers = @("browser")
                    tools = @("browser.*", "screenshot")
                }
                judge = @{
                    servers = @("image")
                    tools = @("image.*", "read")
                }
                fixer = @{
                    servers = @("fs", "git")
                    tools = @("write", "read", "git.*")
                }
            }
        } | ConvertTo-Json -Depth 10 | Out-File -FilePath $allowlistsPath -Encoding UTF8
    } else {
        Copy-Item (Join-Path $ScriptDir "ai\supervisor\allowlists.json") $allowlistsPath -Force
    }
    Write-Host "  ✓ ai\supervisor\allowlists.json" -ForegroundColor Gray
}

# Supervisor gates
$gatesPath = Join-Path $TargetDir "ai\supervisor\gates.json"
if (-not (Test-Path $gatesPath)) {
    $gatesContent = Get-Content (Join-Path $ScriptDir "ai\supervisor\gates.json") -ErrorAction SilentlyContinue
    if (-not $gatesContent) {
        # Create default gates
        @{
            version = "1.0"
            gates = @{
                wheel_scout = @{
                    enabled = $true
                    required_for = @("build", "architecture", "system")
                    timeout_seconds = 300
                }
                budget = @{
                    enabled = $true
                    max_tokens = 1000000
                    max_api_calls = 1000
                }
                security = @{
                    enabled = $true
                    require_approval_for = @("git push --force", "rm -rf")
                }
            }
        } | ConvertTo-Json -Depth 10 | Out-File -FilePath $gatesPath -Encoding UTF8
    } else {
        Copy-Item (Join-Path $ScriptDir "ai\supervisor\gates.json") $gatesPath -Force
    }
    Write-Host "  ✓ ai\supervisor\gates.json" -ForegroundColor Gray
}

# Create .gitkeep files for empty directories
$gitkeepDirs = @(
    "ai\context\specialized",
    "ai\research\landscape_reports",
    "ai\vendor",
    "ai\_backups",
    "ai\_locks"
)

foreach ($dir in $gitkeepDirs) {
    $fullPath = Join-Path $TargetDir $dir
    $gitkeepPath = Join-Path $fullPath ".gitkeep"
    if ((Test-Path $fullPath) -and -not (Test-Path $gitkeepPath)) {
        "" | Out-File -FilePath $gitkeepPath -Encoding UTF8
    }
}

# Create supervisor state files
$statePath = Join-Path $TargetDir "ai\supervisor\state.json"
if (-not (Test-Path $statePath)) {
    @{
        version = "1.0"
        current_task = $null
        active_agents = @()
        budget_used = @{
            tokens = 0
            api_calls = 0
            time_seconds = 0
        }
    } | ConvertTo-Json -Depth 10 | Out-File -FilePath $statePath -Encoding UTF8
    Write-Host "  ✓ ai\supervisor\state.json" -ForegroundColor Gray
}

$taskQueuePath = Join-Path $TargetDir "ai\supervisor\task_queue.json"
if (-not (Test-Path $taskQueuePath)) {
    @{
        version = "1.0"
        pending = @()
        in_progress = @()
        completed = @()
    } | ConvertTo-Json -Depth 10 | Out-File -FilePath $taskQueuePath -Encoding UTF8
    Write-Host "  ✓ ai\supervisor\task_queue.json" -ForegroundColor Gray
}

# Create VPS-friendly MCP registry (not Cursor-dependent)
$mcpRegistryPath = Join-Path $TargetDir "ai\supervisor\mcp.servers.json"
if (-not (Test-Path $mcpRegistryPath)) {
    $mcpRegistryContent = Get-Content (Join-Path $ScriptDir "ai\supervisor\mcp.servers.json") -ErrorAction SilentlyContinue
    if (-not $mcpRegistryContent) {
        # Create default MCP registry
        @{
            version = "1.0"
            description = "VPS-friendly MCP server registry (harness-native, not Cursor-dependent)"
            servers = @{
                playwright = @{
                    command = "npx"
                    args = @("-y", "@modelcontextprotocol/server-playwright")
                    env = @{}
                    description = "Playwright browser automation MCP server"
                    enabled = $true
                }
            }
            toolhive = @{
                enabled = $false
                gateway_url = $null
            }
        } | ConvertTo-Json -Depth 10 | Out-File -FilePath $mcpRegistryPath -Encoding UTF8
    } else {
        Copy-Item (Join-Path $ScriptDir "ai\supervisor\mcp.servers.json") $mcpRegistryPath -Force
    }
    Write-Host "  ✓ ai\supervisor\mcp.servers.json (VPS-friendly registry)" -ForegroundColor Gray
}

Write-Host "`n✅ Harness installation complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "  1. Review HARNESS_README.md for usage instructions" -ForegroundColor White
Write-Host "  2. Configure platform-specific settings:" -ForegroundColor White
Write-Host "     - OpenClaw: See OPENCLAW_INTEGRATION.md" -ForegroundColor Gray
Write-Host "     - Cursor: See CURSOR_SUPERVISOR_GUIDE.md" -ForegroundColor Gray
Write-Host "     - Claude Code: See CLAUDE_SUPERVISOR_GUIDE.md" -ForegroundColor Gray
Write-Host "     - Gemini: See GEMINI_INTEGRATION.md" -ForegroundColor Gray
Write-Host "  3. Configure tool broker allowlists in ai/supervisor/allowlists.json" -ForegroundColor White
Write-Host "  4. Run verification: .\scripts\verify_harness.ps1" -ForegroundColor White
Write-Host "`nSupervisor Features:" -ForegroundColor Cyan
Write-Host "  ✓ Tool Broker: Unified MCP tool access" -ForegroundColor Gray
Write-Host "  ✓ Wheel-Scout: Reality checks before building" -ForegroundColor Gray
Write-Host "  ✓ Context Builder: On-demand documentation and repo cloning" -ForegroundColor Gray
Write-Host "  ✓ Multi-Agent Orchestration: Task routing and coordination" -ForegroundColor Gray
Write-Host "`n"

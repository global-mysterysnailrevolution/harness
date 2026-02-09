# Agent Harness Template

A universal, platform-agnostic harness system for orchestrating parallel AI agent behaviors across Codex CLI, Cursor, Claude Code, and OpenClaw.

## Quick Start

### Installation

Run the bootstrap installer in your repository root:

```powershell
# From the harness template directory
.\bootstrap.ps1

# Or from any directory (if harness is cloned)
cd C:\path\to\your\repo
C:\path\to\harness-template\bootstrap.ps1
```

The installer will:
- Create the harness directory structure
- Install platform integration files
- Set up safety guardrails
- Initialize Git if needed (with backup)

### Verification

```powershell
.\scripts\verify_harness.ps1
```

## Architecture

### The Four Parallel Behaviors

1. **Context Priming** (ALWAYS runs in parallel)
   - Repo-scout: Maps insertion points and architecture
   - Web/GitHub research: Finds existing docs and implementations
   - Implementation-bridger: Creates concrete plan for this repo
   - Outputs: `ai/context/REPO_MAP.md`, `ai/context/FEATURE_RESEARCH.md`, `ai/context/CONTEXT_PACK.md`

2. **Memory Extraction** (Automatic trigger at 15% context remaining)
   - Summarizes session into `ai/memory/WORKING_MEMORY.md`
   - Records decisions into `ai/memory/DECISIONS.md`
   - Performs compaction/rehydration for continuation
   - Trigger: Codex CLI `/status` or token-counting approximation

3. **Log Monitoring** (Runs when testing local server)
   - Starts dev server as background task
   - Tails/streams logs continuously
   - Detects anomalies and summarizes into `ai/context/LOG_FINDINGS.md`
   - Provides actionable fix suggestions

4. **Background Test Writing** (Runs alongside feature implementation)
   - Identifies test framework and conventions
   - Writes/updates unit and integration tests
   - Maintains `ai/tests/TEST_PLAN.md` and `ai/tests/COVERAGE_NOTES.md`
   - Runs fast test subsets when possible

## Directory Structure

```
your-repo/
├── ai/
│   ├── context/          # Context artifacts (REPO_MAP, CONTEXT_PACK, etc.)
│   ├── memory/           # Session memory (WORKING_MEMORY, DECISIONS)
│   ├── tests/            # Test plans and coverage notes
│   ├── research/         # Archived web research with citations
│   ├── vendor/           # Cloned reference implementations (gitignored)
│   ├── _backups/         # Timestamped backups before risky operations
│   └── _locks/           # File locks for concurrent operation safety
├── scripts/
│   ├── workers/          # Background worker scripts
│   ├── compilers/        # Deterministic artifact compilers
│   └── hooks/           # Git hooks and event handlers
├── .cursor/              # Cursor IDE integration
│   └── hooks.json       # Cursor event hooks
├── .claude/             # Claude Code integration
│   ├── agents/          # Claude subagent definitions
│   └── settings.json    # Claude hooks and settings
└── CODEX_WORKFLOW.md    # Codex CLI workflow guide
```

## Platform Integration

### Codex CLI

The harness uses Codex CLI's background terminals (`/ps`) and context status (`/status`):

- **Background Workers**: Spawn via `codex /ps <command>`
- **Context Monitoring**: Check with `codex /status` to detect 15% threshold
- **MCP Server**: Codex runs as MCP server for integration

See `CODEX_WORKFLOW.md` for detailed commands and runbook.

### Cursor IDE

Integration via `.cursor/hooks.json`:

```json
{
  "version": "1.0",
  "hooks": [
    {
      "event": "file-watcher",
      "command": "scripts/hooks/file_watcher.ps1"
    },
    {
      "event": "pre-commit",
      "command": "scripts/hooks/pre_commit.ps1"
    }
  ]
}
```

**Worktrees**: Use worktrees for parallel feature branches. See `.cursor/WORKTREES_GUIDE.md`.

### Claude Code

Integration via `.claude/` directory:

- **Subagents**: Defined in `.claude/agents/*.md`
- **Hooks**: Configured in `.claude/settings.json`
- **Skills**: Documented in `.claude/SKILLS.md`

Claude agents automatically use harness artifacts for context priming and memory checkpointing.

### OpenClaw

OpenClaw compatibility is achieved through:

- Platform-agnostic artifact formats (Markdown, JSON)
- Standard file-based communication
- No platform-specific dependencies in core harness

The harness works identically in OpenClaw as in other platforms.

## Safety & Guardrails

### Secret Protection

The harness automatically asks before reading files matching:
- `*.env*`
- `*secret*`, `*token*`, `*key*`
- `*.pem`, `*.key`
- SSH keys, cloud credentials

### Risky Command Gating

Asks before executing:
- Destructive file operations (delete, move without backup)
- System-level changes
- Network operations that could cost money
- Git operations that rewrite history

### Versioning Before Destruction

- **Git repos**: Creates commit before destructive operations
- **Non-git repos**: Creates timestamped backup in `ai/_backups/`
- Always warns before proceeding

### File Locking

Prevents concurrent workers from corrupting artifacts:
- Lock files in `ai/_locks/` for exclusive access
- Append-only raw logs with deterministic compile step
- Prevents clobbering of `WORKING_MEMORY.md` and `CONTEXT_PACK.md`

## Deterministic Compilers

All artifacts are generated deterministically from raw logs:

- `scripts/compilers/build_repo_map.py/js` - Generates REPO_MAP.md
- `scripts/compilers/build_context_pack.py/js` - Generates CONTEXT_PACK.md
- `scripts/compilers/memory_checkpoint.py/js` - Creates memory checkpoints
- `scripts/compilers/log_sentinel.py/js` - Processes log findings
- `scripts/compilers/test_plan_compiler.py/js` - Generates test plans

**Why deterministic?** Ensures parallel workers can safely append to raw logs, then compile final artifacts without conflicts.

## Usage Patterns

### Starting a New Feature

```powershell
# Context priming runs automatically
# Workers spawn in parallel:
# - Repo-scout maps structure
# - Web researcher finds docs
# - Implementation-bridger creates plan

# Check results:
cat ai/context/REPO_MAP.md
cat ai/context/CONTEXT_PACK.md
```

### Memory Checkpoint (Automatic)

When context approaches limit (15% remaining):
- Memory-scribe worker spawns automatically
- Summarizes session to `ai/memory/WORKING_MEMORY.md`
- Records decisions to `ai/memory/DECISIONS.md`
- Main agent continues with compacted context + memory pointers

### Testing with Log Monitoring

```powershell
# Start dev server (harness detects and monitors)
npm start  # or python app.py, etc.

# Log monitor runs in background
# Anomalies logged to ai/context/LOG_FINDINGS.md
```

### Writing Tests in Parallel

When implementing a feature:
- Test-writer worker spawns automatically
- Identifies test framework from repo
- Writes tests alongside implementation
- Updates `ai/tests/TEST_PLAN.md`

## Research Archiving

For every external implementation found:

1. **Save to `ai/research/`**:
   - Link + summary
   - Citation
   - "Why it matters" note

2. **Optional Clone to `ai/vendor/`**:
   - Ask first if repo is large/unknown
   - Gitignored by default
   - Used for reference implementations

## Golden Scenario / Verification

Run the verification script to test the harness:

```powershell
.\scripts\verify_harness.ps1
```

This demonstrates:
- ✅ Artifact creation
- ✅ Simulated feature implementation triggers
- ✅ Memory checkpoint simulation
- ✅ Log monitoring (dummy mode)
- ✅ Test writing outputs

Works even in repos with no dev server.

## Platform Detection

The harness automatically detects:

- **Stack**: From `package.json`, `requirements.txt`, `Cargo.toml`, etc.
- **Dev Server**: From scripts, config files, common patterns
- **Test Framework**: From test directories, config files
- **Language**: From file extensions and project structure

Works in code repos AND docs-only repos.

## Troubleshooting

### Workers Not Spawning

- Check platform integration files exist
- Verify scripts are executable
- Check `ai/_locks/` for stuck locks

### Memory Checkpoint Not Triggering

- Verify Codex CLI `/status` works
- Check token-counting approximation
- Review `ai/memory/` for existing checkpoints

### Log Monitor Not Starting

- Verify dev server detection
- Check background process spawning
- Review platform-specific requirements

## Contributing

This is a template - customize for your needs:

1. Modify worker scripts in `scripts/workers/`
2. Adjust compilers in `scripts/compilers/`
3. Update platform integrations as needed
4. Extend safety guardrails for your use case

## License

[Your License Here]

## Support

- Issues: [GitHub Issues]
- Documentation: See platform-specific guides in `.cursor/`, `.claude/`, and `CODEX_WORKFLOW.md`

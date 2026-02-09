# Agent Harness Template

A universal, platform-agnostic harness system for orchestrating parallel AI agent behaviors across **Codex CLI**, **Cursor**, **Claude Code**, and **OpenClaw**.

## Quick Start

### Installation

Run the bootstrap installer in your repository root:

```powershell
.\bootstrap.ps1
```

### Full Documentation

See **[HARNESS_README.md](HARNESS_README.md)** for complete documentation.

## What This Harness Does

The harness orchestrates **four parallel behaviors**:

1. **Context Priming** (Always parallel) - Maps repo, researches, creates implementation plan
2. **Memory Extraction** (Auto-triggered at 15% context) - Checkpoints session for continuation
3. **Log Monitoring** (When testing) - Monitors dev server logs, detects anomalies
4. **Background Test Writing** (Parallel with features) - Writes tests alongside implementation

## Platform Support

- ✅ **Codex CLI** - Native support via `/ps` and `/status` commands
- ✅ **Cursor IDE** - Integration via hooks.json and worktrees
- ✅ **Claude Code** - Subagents, hooks, and skills integration
- ✅ **OpenClaw** - Platform-agnostic file-based communication

## Key Features

- **Parallel Workers**: Always-run background processes
- **Deterministic Compilers**: Safe concurrent artifact generation
- **Safety Guardrails**: Secret protection, risky command gating
- **Memory Checkpointing**: Automatic session state persistence
- **Platform Agnostic**: Works in code repos AND docs-only repos

## Structure

```
your-repo/
├── ai/
│   ├── context/          # REPO_MAP, CONTEXT_PACK, FEATURE_RESEARCH
│   ├── memory/           # WORKING_MEMORY, DECISIONS
│   ├── tests/            # TEST_PLAN, COVERAGE_NOTES
│   ├── research/         # Archived web research
│   ├── vendor/           # Cloned implementations (gitignored)
│   ├── _backups/         # Timestamped backups
│   └── _locks/           # File locks for concurrency
├── scripts/
│   ├── workers/          # Background worker scripts
│   ├── compilers/        # Deterministic artifact compilers
│   └── hooks/            # Git hooks and event handlers
├── .cursor/              # Cursor IDE integration
├── .claude/              # Claude Code integration
└── CODEX_WORKFLOW.md     # Codex CLI guide
```

## Verification

Test the harness installation:

```powershell
.\scripts\verify_harness.ps1
```

## Documentation

- **[HARNESS_README.md](HARNESS_README.md)** - Complete harness documentation
- **[CODEX_WORKFLOW.md](CODEX_WORKFLOW.md)** - Codex CLI workflow guide
- **[.cursor/WORKTREES_GUIDE.md](.cursor/WORKTREES_GUIDE.md)** - Cursor worktrees guide

## License

[Add your license here]

## Contributing

This is a template - customize for your needs. See HARNESS_README.md for detailed customization instructions.

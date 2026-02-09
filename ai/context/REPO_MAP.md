# Repository Map
Generated: 02/07/2026

## Stack
- Type: PowerShell-based template system
- Architecture: Template/Configuration repository
- Purpose: Agent Harness Template for AI-assisted development workflows

## Repository Structure

```
agent-harness-template/
├── ai/
│   ├── context/          # Context artifacts for AI agents
│   │   ├── REPO_MAP.md   # This file - repository structure mapping
│   │   └── CONTEXT_PACK.md # Context pack for agent priming
│   ├── memory/            # Session memory and checkpoints
│   │   └── WORKING_MEMORY.md # Working memory checkpoint
│   ├── tests/             # Test artifacts and validation
│   └── _locks/            # Lock files for concurrent operations
├── scripts/
│   ├── workers/           # Background worker scripts
│   ├── compilers/         # Deterministic artifact compilers
│   └── hooks/             # Git hooks and automation
└── .cursor/               # Cursor IDE configuration (if exists)
    └── skills/            # Cursor Agent Skills
└── .claude/               # Claude Code agents (if exists)
    └── agents/            # Claude agent configurations
```

## Insertion Points

### Background Workers
- Location: `scripts/workers/`
- Purpose: Long-running background processes
- Examples: File watchers, data processors, sync workers

### Artifact Compilers
- Location: `scripts/compilers/`
- Purpose: Generate deterministic artifacts from templates
- Examples: Code generators, documentation builders

### Cursor Skills
- Location: `.cursor/skills/`
- Purpose: Cursor Agent Skills for automation
- Examples: Custom commands, workflows

### Claude Agents
- Location: `.claude/agents/`
- Purpose: Claude Code agent configurations
- Examples: Specialized agent definitions

## Workflow Integration

### Context Priming
1. Consult `ai/context/REPO_MAP.md` for structure
2. Review `ai/context/CONTEXT_PACK.md` for context
3. Checkpoint memory in `ai/memory/WORKING_MEMORY.md`

### Safety Gates
- File operations: Check locks in `ai/_locks/`
- Concurrent access: Use lock files before modifications
- Validation: Run tests in `ai/tests/` before committing

## Status
- ✅ Repository structure mapped
- ✅ Insertion points identified
- ✅ Workflow defined

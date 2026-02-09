# Agent Harness Template

A PowerShell-based template system for AI-assisted development workflows.

## Overview

The Agent Harness Template provides a structured framework for managing AI agent interactions, context priming, memory checkpointing, and workflow automation.

## Structure

```
agent-harness-template/
├── ai/
│   ├── context/          # Context artifacts for AI agents
│   ├── memory/            # Session memory and checkpoints
│   ├── tests/             # Test artifacts and validation
│   └── _locks/            # Lock files for concurrent operations
└── scripts/
    ├── workers/           # Background worker scripts
    ├── compilers/         # Deterministic artifact compilers
    └── hooks/             # Git hooks and automation
```

## Key Features

- **Context Management**: Structured context priming for AI agents
- **Memory Checkpointing**: Session state persistence
- **Safety Gates**: Concurrent operation protection
- **Workflow Automation**: Background workers and compilers
- **Integration Points**: Cursor IDE and Claude Code support

## Usage

### For AI Agents

1. **Context Priming**
   - Consult `ai/context/REPO_MAP.md` for structure
   - Review `ai/context/CONTEXT_PACK.md` for context
   - Check `ai/memory/WORKING_MEMORY.md` for recent state

2. **Making Changes**
   - Check for locks in `ai/_locks/`
   - Follow safety gates for sensitive operations
   - Update memory after significant changes

3. **Validation**
   - Run tests in `ai/tests/` before committing
   - Verify working tree status
   - Check for uncommitted changes

### For Developers

This template can be used as a starting point for projects that involve AI-assisted development. Customize the structure and workflows to fit your needs.

## Files

- `ai/context/REPO_MAP.md` - Repository structure mapping
- `ai/context/CONTEXT_PACK.md` - Context pack for agent priming
- `ai/memory/WORKING_MEMORY.md` - Working memory checkpoint
- `README.md` - This file

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

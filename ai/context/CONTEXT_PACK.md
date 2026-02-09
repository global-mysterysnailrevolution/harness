# Context Pack
Generated: 02/07/2026

## Purpose
This context pack provides essential information for AI agents working with the Agent Harness Template system.

## Repository Overview

**Name:** Agent Harness Template  
**Type:** Template/Configuration Repository  
**Stack:** PowerShell-based automation system  
**Architecture:** Modular harness for AI-assisted development

## Key Concepts

### Harness System
The harness provides a structured framework for:
- Context management and priming
- Memory checkpointing
- Workflow automation
- Safety gates and validation

### Workflow Pattern
1. **Context Priming**: Load repository structure and context
2. **Memory Checkpoint**: Save session state
3. **Operation Execution**: Perform tasks with safety gates
4. **Validation**: Run tests and checks
5. **Commitment**: Save changes with proper tracking

## Directory Conventions

### `ai/context/`
- **REPO_MAP.md**: Repository structure and insertion points
- **CONTEXT_PACK.md**: This file - agent context information

### `ai/memory/`
- **WORKING_MEMORY.md**: Session memory and state checkpoints
- Used for maintaining context across agent interactions

### `ai/tests/`
- Test artifacts and validation scripts
- Run before committing changes

### `ai/_locks/`
- Lock files for concurrent operation safety
- Prevents race conditions in multi-agent scenarios

### `scripts/workers/`
- Background worker scripts
- Long-running processes and automation

### `scripts/compilers/`
- Deterministic artifact compilers
- Generate code, docs, or other artifacts from templates

## Agent Guidelines

### Before Making Changes
1. ✅ Consult `ai/context/REPO_MAP.md` for structure
2. ✅ Review `ai/context/CONTEXT_PACK.md` for context
3. ✅ Check `ai/memory/WORKING_MEMORY.md` for recent state
4. ✅ Verify no locks in `ai/_locks/` for target files

### During Operations
- Use parallel workers when appropriate
- Follow safety gates for sensitive operations
- Checkpoint memory after significant changes

### After Operations
- Update `ai/memory/WORKING_MEMORY.md` with new state
- Run validation tests if applicable
- Document changes in appropriate context files

## Safety Gates

### File Operations
- Check for lock files before modifying
- Create locks for concurrent access protection
- Remove locks after operations complete

### Git Operations
- Verify working tree status
- Check for uncommitted changes
- Validate before pushing

### External Dependencies
- Verify API availability
- Check authentication status
- Validate configuration

## Integration Points

### Cursor IDE
- Skills in `.cursor/skills/`
- Configuration in `.cursor/` directory

### Claude Code
- Agents in `.claude/agents/`
- Configurations in `.claude/` directory

## Status
- ✅ Context pack ready
- ✅ Guidelines defined
- ✅ Safety gates documented

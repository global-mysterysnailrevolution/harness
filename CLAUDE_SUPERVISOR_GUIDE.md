# Claude Code Supervisor Guide

## Overview

Claude Code integration uses subagents, hooks, and skills. The supervisor acts as the top-level Claude agent that coordinates subagents.

## Architecture

```
Claude Agent (Supervisor)
  ├── Wheel-Scout Subagent
  ├── Context Builder Subagent
  ├── Implementer Subagent
  ├── Test Runner Subagent
  └── Fixer Subagent
```

## Configuration

### Supervisor Agent

Defined in `.claude/agents/supervisor.md`. This is the main orchestrator.

### Subagent Definitions

Subagents defined in `.claude/agents/*.md`:
- `wheel-scout.md` - Reality check agent
- `context-builder.md` - Context hydration agent
- `tool-broker.md` - Tool management agent
- Plus existing agents (repo-scout, web-researcher, etc.)

### Hooks

Configured in `.claude/hooks/context_builder.json`:
- `pre-subagent-spawn`: Builds context before spawn
- `post-wheel-scout`: Clears gate after report

### Settings

Edit `.claude/settings.json` to add supervisor hooks:

```json
{
  "hooks": {
    "pre-subagent-spawn": {
      "command": "python",
      "args": ["scripts/broker/context_hydrator.py", "--build"]
    }
  }
}
```

## Usage

### Supervisor Workflow

1. User gives task to Claude (supervisor agent)
2. Supervisor classifies intent
3. If build → spawns Wheel-Scout subagent
4. Wheel-Scout generates landscape report
5. Supervisor validates report, clears gate
6. Supervisor spawns context builder subagent
7. Context builder fetches docs, clones repos
8. Supervisor spawns implementer subagent with context
9. Implementer references landscape report in work

### Subagent Spawning

Supervisor spawns subagents via Claude's subagent system:

```markdown
# In supervisor agent prompt
Spawn subagent: implementer
Context: [specialized context injected here]
Task: [task description]
Landscape Report: [report reference]
```

### Tool Broker Integration

Subagents access tools through tool broker:

- Supervisor queries broker for available tools
- Filters by subagent allowlist
- Injects tool access into subagent context

## Wheel-Scout Gate

Hard gate enforced by supervisor:

1. Supervisor detects build intent
2. Checks for landscape report
3. If missing → spawns Wheel-Scout subagent
4. Waits for report generation
5. Validates report
6. Clears gate
7. Only then spawns implementer

## Context Building

Automatic context building via hook:

1. Supervisor identifies subagent needed
2. Pre-spawn hook triggers
3. Context builder analyzes requirements
4. Fetches documentation
5. Clones reference repos
6. Compiles specialized context
7. Injects into subagent spawn

## Best Practices

1. **Reference Landscape Reports**: Implementers must cite existing solutions
2. **Use Specialized Context**: Each subagent gets tailored context
3. **Respect Tool Allowlists**: Subagents only see allowed tools
4. **Monitor Budgets**: Track token usage per task

## Troubleshooting

### Subagents Not Spawning

- Check supervisor agent is active
- Verify subagent definitions in `.claude/agents/`
- Review hook configuration

### Context Not Building

- Check pre-spawn hook is enabled
- Verify context builder has tool access
- Review `ai/context/specialized/` for outputs

### Wheel-Scout Blocking

- Check `ai/research/landscape_reports/` for reports
- Verify report validation
- Review gate state

# Multi-Agent Supervisor System

## Overview

The supervisor system orchestrates multiple agents with tool broker integration, Wheel-Scout reality checks, and dynamic context building. It works across OpenClaw, Cursor, Claude Code, and Gemini.

## Key Components

### 1. Tool Broker

Unified MCP tool access that reduces token usage by 80%+:

- **Meta-tools only**: Agents see `search_tools()`, `call_tool()`, etc., not 50+ tool schemas
- **Per-agent allowlists**: Security and token reduction
- **On-demand hydration**: Load full tool schemas only when needed
- **Proxy calling**: Execute tools without schema injection

See [TOOL_BROKER_GUIDE.md](TOOL_BROKER_GUIDE.md) for details.

### 2. Wheel-Scout Agent

Reality check agent that prevents reinventing wheels:

- **Hard gate**: Blocks implementers until landscape report approved
- **Research**: Finds existing OSS, products, papers
- **Recommendation**: adopt/extend/build with justification
- **Caching**: Avoids re-researching similar problems

See `.claude/agents/wheel-scout.md` for details.

### 3. Dynamic Context Builder

On-demand context building for sub-agents:

- **Documentation fetching**: Language docs, framework docs, GitHub READMEs
- **Repo cloning**: Clones reference repos dynamically
- **Code extraction**: Extracts relevant examples
- **Specialization**: Each agent gets context tailored to their role

See `.claude/agents/context-builder.md` for details.

### 4. Supervisor Core

Main orchestration logic:

- **Task routing**: Classifies intent, routes to appropriate agent
- **Gate enforcement**: Enforces Wheel-Scout and budget gates
- **Budget tracking**: Monitors token usage, API calls, time
- **Agent coordination**: Manages agent lifecycle

## Workflow

```
User Task
    ↓
Supervisor (classifies intent)
    ↓
[If build] → Wheel-Scout Gate Check
    ↓ (if not cleared)
Wheel-Scout (research existing solutions)
    ↓
Landscape Report Generated
    ↓
Gate Cleared
    ↓
Context Builder (fetches docs, clones repos)
    ↓
Specialized Context Built
    ↓
Sub-Agent Spawned (with context + landscape report)
    ↓
Sub-Agent Works (references report, uses specialized context)
```

## Platform Integration

### OpenClaw

- Uses `sessions_spawn` with pre-hydrated context
- Leverages `tools.allow/deny` for tool scoping
- Browser tool for web testing scenarios

See [OPENCLAW_INTEGRATION.md](OPENCLAW_INTEGRATION.md)

### Cursor

- MCP server integration for tool broker
- Hooks for context building
- Worktrees for parallel development

See [CURSOR_SUPERVISOR_GUIDE.md](CURSOR_SUPERVISOR_GUIDE.md)

### Claude Code

- Supervisor as top-level agent
- Subagents for specialized tasks
- Hooks for context building

See [CLAUDE_SUPERVISOR_GUIDE.md](CLAUDE_SUPERVISOR_GUIDE.md)

### Gemini

- Gemini API multi-agent orchestration
- Function calling for context injection
- Tool broker via Gemini's tool system

See [GEMINI_INTEGRATION.md](GEMINI_INTEGRATION.md)

## Quick Start

### 1. Install Harness

```powershell
.\bootstrap.ps1
```

### 2. Configure Tool Broker

Edit `ai/supervisor/allowlists.json`:

```json
{
  "web-runner": {
    "allow": ["browser:*", "web:*"],
    "servers": ["browser", "web"]
  }
}
```

### 3. Use Supervisor

```python
from scripts.supervisor.supervisor import Supervisor
from pathlib import Path

supervisor = Supervisor(Path("."))

# Submit task
task_id = supervisor.submit_task("Build React authentication component")

# Process (handles gates, context, spawning)
supervisor.process_task(task_id)
```

## Agent Profiles

Common agent profiles:

- **orchestrator**: Minimal tools, spawns others
- **web-runner**: Browser automation, screenshots
- **judge**: Test evaluation, visual diffs
- **fixer**: Code editing, test running
- **wheel-scout**: Research only (read-only tools)
- **context-builder**: Documentation fetching, repo cloning

## Best Practices

1. **Always use Wheel-Scout for builds**: Prevents reinventing wheels
2. **Let context builder run**: Automatic specialization saves time
3. **Configure allowlists**: Security and token reduction
4. **Monitor budgets**: Track usage to prevent runaway costs
5. **Reference landscape reports**: Implementers must cite existing solutions

## Troubleshooting

### Wheel-Scout Always Blocking

- Check `ai/research/landscape_reports/` for reports
- Verify report validation passes
- Review gate state in `ai/supervisor/gates.json`

### Context Not Building

- Check tool broker has web search tools
- Verify context builder has tool access
- Review `ai/context/specialized/` for outputs

### Agents Not Spawning

- Check platform integration files exist
- Verify supervisor state in `ai/supervisor/state.json`
- Review agent profiles in platform configs

## Files Reference

- Supervisor core: `scripts/supervisor/supervisor.py`
- Tool broker: `scripts/broker/tool_broker.py`
- Context builder: `scripts/workers/context_builder.ps1`
- Wheel-Scout: `scripts/workers/wheel_scout.ps1`
- Platform configs: `openclaw/`, `.cursor/`, `.claude/`, `gemini/`

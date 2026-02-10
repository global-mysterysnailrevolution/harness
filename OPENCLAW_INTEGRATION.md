# OpenClaw Integration Guide

## ⚠️ Important: Non-MCP Integration

**OpenClaw does not natively support MCP yet.** This integration uses an **OpenClaw Skill wrapper** instead of direct MCP integration.

See `VPS_DEPLOYMENT.md` for deployment instructions and `openclaw/harness_skill.md` for skill API documentation.

## Overview

OpenClaw provides built-in multi-agent orchestration, per-agent tool allowlists, and browser automation. This integration adds the supervisor layer, tool broker, Wheel-Scout, and dynamic context builder on top.

## What OpenClaw Already Provides

- ✅ Multi-agent orchestration (`sessions_spawn`, `sessions_send`)
- ✅ Per-agent tool allow/deny (`tools.allow`, `tools.deny`)
- ✅ Browser automation (`browser` tool with act/screenshot/console)
- ✅ Process sessions (isolated per-agent)
- ✅ Skills that load on-demand

## What We Add

- **Supervisor**: Task routing, gate enforcement, budget tracking
- **Tool Broker**: MCP tool management with allowlisting
- **Wheel-Scout**: Reality checks before building
- **Context Builder**: On-demand documentation and repo cloning
- **Dynamic Context**: Specialized context per agent

## Configuration

### Supervisor Config

Edit `openclaw/supervisor_config.json`:

```json
{
  "supervisor": {
    "enabled": true,
    "tool_broker": {"enabled": true},
    "wheel_scout": {"enabled": true, "required_for_build": true},
    "context_builder": {"enabled": true, "cache_hours": 1}
  }
}
```

### Agent Profiles

Edit `openclaw/agent_profiles.json` to define agent capabilities and context requirements.

## Usage

### Starting Supervisor

```python
from scripts.supervisor.supervisor import Supervisor
from pathlib import Path

supervisor = Supervisor(Path("."))

# Submit task
task_id = supervisor.submit_task("Build a React authentication component")

# Process task (supervisor handles Wheel-Scout, context building, agent spawning)
supervisor.process_task(task_id)
```

### OpenClaw-Specific Spawning

The supervisor uses OpenClaw's `sessions_spawn` with pre-hydrated context:

```python
# Context builder runs first
context_file = build_context_for_agent(
    agent_id="web-runner-1",
    agent_role="web-runner",
    task_description="Test login flow",
    repo_path=Path(".")
)

# Spawn with context
openclaw.sessions_spawn(
    agent_id="web-runner-1",
    tools={"allow": ["browser", "image"]},
    context_file=context_file  # Injected into agent
)
```

## Workflow Example

### Closed-Loop Web Testing

1. **Orchestrator** receives: "Test login flow"
2. **Supervisor** routes to web-runner agent
3. **Context Builder** fetches React testing docs, clones example repos
4. **Web-Runner** spawns with specialized context
5. **Web-Runner** executes test using `browser` tool
6. **Judge** evaluates results
7. **Fixer** patches code if needed
8. Loop until pass or budget exhausted

## Tool Broker Integration

OpenClaw agents connect to tool broker via MCP:

```json
{
  "mcp.servers": {
    "tool-broker": {
      "command": "python",
      "args": ["scripts/broker/tool_broker.py", "server"]
    }
  }
}
```

Agents use broker's meta-tools:
- `search_tools()` - Find available tools
- `call_tool()` - Execute tools via proxy

## Wheel-Scout Integration

Wheel-Scout runs as OpenClaw agent with restricted tools:

```json
{
  "wheel-scout": {
    "tools": {
      "allow": ["web_search", "github_search", "read"],
      "deny": ["group:fs", "group:runtime"]
    }
  }
}
```

Supervisor enforces gate: implementers blocked until Wheel-Scout clears.

## Context Builder Hook

Pre-spawn hook builds context automatically:

```python
# Hook runs before agent spawn
context_file = context_builder_hook.build_context_for_agent(
    agent_id="agent-1",
    agent_role="web-runner",
    task_description="Test login",
    repo_path=Path(".")
)

# Context injected into agent system prompt
```

## Best Practices

1. **Start with minimal tools**: Orchestrator uses `tools.profile: "minimal"`
2. **Use allowlists**: Explicitly allow only needed tools per agent
3. **Enable context builder**: Let it fetch docs/repos on-demand
4. **Respect Wheel-Scout**: Don't bypass reality checks
5. **Monitor budgets**: Track token usage and API calls

## Security

- **Tool allowlists**: Per-agent restrictions prevent unauthorized access
- **Wheel-Scout isolation**: Read-only tools, no code execution
- **Context builder**: Asks before cloning large repos
- **Budget limits**: Prevents runaway costs

## Troubleshooting

### Agents Not Spawning

- Check OpenClaw is running
- Verify `sessions_spawn` API available
- Check agent profiles in `agent_profiles.json`

### Context Not Building

- Verify context builder hook is enabled
- Check tool broker has web search tools
- Review `ai/context/specialized/` for generated contexts

### Wheel-Scout Blocking

- Check `ai/research/landscape_reports/` for reports
- Verify report validation passes
- Review gate state in `ai/supervisor/gates.json`

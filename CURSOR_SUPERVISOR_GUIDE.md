# Cursor Supervisor Guide

## Overview

Cursor integration uses MCP servers for tool broker and hooks for context building. The supervisor coordinates agents through Cursor's agent system.

## Configuration

### Supervisor Config

Edit `.cursor/supervisor.json` to enable supervisor features.

### MCP Tool Broker

Add tool broker as MCP server in Cursor settings:

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

### Hooks

Context builder hook runs before agent spawn:

```json
{
  "hooks": {
    "pre-spawn": {
      "command": "scripts/hooks/pre_spawn_context.ps1"
    }
  }
}
```

## Usage

### Supervisor Workflow

1. Supervisor receives task via Cursor agent interface
2. Context builder hook runs (if enabled)
3. Specialized context injected via MCP resources
4. Agent spawned with pre-hydrated context
5. Agent uses tool broker for tool access

### Tool Broker Access

Agents access tools through broker MCP server:

```javascript
// Agent calls broker via MCP
const tools = await mcp.call("tool-broker", "search_tools", {
  query: "web search",
  agent_id: "web-runner"
});
```

## Integration Points

- **MCP Resources**: Context files exposed as MCP resources
- **Hooks**: Pre-spawn hook builds context
- **Worktrees**: Each worktree has independent supervisor state

## Limitations

- Cursor doesn't have native multi-agent orchestration
- Supervisor runs as single agent coordinating others
- Tool broker provides unified tool access

## Best Practices

1. Use MCP resources for context injection
2. Enable pre-spawn hook for automatic context building
3. Configure tool broker allowlists per agent
4. Use worktrees for parallel feature development

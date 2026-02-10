# Tool Broker Guide

## Overview

The Tool Broker provides a unified interface to MCP (Model Context Protocol) tools, reducing token usage by avoiding schema injection and enabling per-agent tool allowlisting.

## Architecture

```
Agent → Tool Broker → MCP Servers
         ↓
    Allowlist Manager
         ↓
    Tool Discovery
```

## Key Concepts

### Meta-Tools vs Direct Tools

**Meta-Tools** (always available):
- `search_tools()` - Find tools by query
- `describe_tool()` - Get tool schema
- `call_tool()` - Execute tool via proxy
- `load_tools()` - Get full schemas for dynamic registration

**Direct Tools** (loaded on-demand):
- Full MCP tool schemas
- Only loaded when needed
- Filtered by agent allowlist

### Tool Allowlists

Each agent has an allowlist that controls:
- Which tools can be called
- Which MCP servers are accessible
- Pattern-based allow/deny rules

## Usage

### Command Line Interface

```bash
# Search for tools
python scripts/broker/tool_broker.py search --query "web search" --agent-id "web-runner"

# Describe a tool
python scripts/broker/tool_broker.py describe --tool-id "github:search_repos"

# Call a tool
python scripts/broker/tool_broker.py call --tool-id "github:search_repos" --args '{"query": "react"}'

# Load tool schemas
python scripts/broker/tool_broker.py load --tool-ids "github:search_repos,web:search" --agent-id "researcher"
```

### Python API

```python
from scripts.broker.tool_broker import ToolBroker

broker = ToolBroker()

# Search tools
results = broker.search_tools(
    query="web search",
    agent_id="web-runner",
    max_results=10
)

# Call tool via proxy
result = broker.call_tool(
    tool_id="github:search_repos",
    args={"query": "react hooks"},
    agent_id="researcher"
)
```

### Node.js API

```javascript
const { ToolBroker } = require('./scripts/broker/tool_broker.js');

const broker = new ToolBroker();

// Search tools
const results = broker.searchTools('web search', {
    agentId: 'web-runner',
    maxResults: 10
});

// Call tool via proxy
const result = broker.callTool(
    'github:search_repos',
    { query: 'react hooks' },
    'researcher'
);
```

## Configuration

### MCP Server Configuration

The broker discovers MCP servers from:
- `~/.cursor/User/settings.json` (Cursor)
- `~/.config/cursor/settings.json` (Cursor alternative)
- `.cursor/mcp.json` (Project-specific)

### Allowlist Configuration

Allowlists stored in `ai/supervisor/allowlists.json`:

```json
{
  "default": {
    "allow": [],
    "deny": [],
    "servers": []
  },
  "web-runner": {
    "allow": ["web:*", "browser:*"],
    "deny": ["dangerous_tool"],
    "servers": ["web", "browser"]
  },
  "researcher": {
    "allow": ["github:*", "web:search"],
    "servers": ["github", "web"]
  }
}
```

## Integration Patterns

### Pattern 1: Proxy Mode (Recommended)

Agents only see meta-tools. All actual tool calls go through broker:

```python
# Agent context only has:
tools = ["search_tools", "describe_tool", "call_tool"]

# When agent needs to search GitHub:
result = call_tool("github:search_repos", {"query": "react"})
```

**Benefits:**
- Minimal token usage (only 3-4 meta-tools)
- Full security control
- Works with any LLM framework

### Pattern 2: Hydration Mode

Broker loads tool schemas on-demand for frameworks that support it:

```python
# Agent requests tools
tools = load_tools(["github:search_repos", "web:search"], agent_id="researcher")

# Framework injects tools into agent context
agent.add_tools(tools)
```

**Benefits:**
- Better type safety
- Native tool calling
- Still filtered by allowlist

## ToolHive Integration (Future)

When ToolHive MCP Optimizer is available:

1. Broker detects ToolHive installation
2. Routes requests through ToolHive
3. Falls back to custom broker if unavailable

This provides:
- Intelligent tool routing
- Automatic optimization
- Unified access to multiple MCP servers

## Best Practices

1. **Use Proxy Mode by Default**: Saves tokens, maintains security
2. **Set Explicit Allowlists**: Don't rely on defaults
3. **Cache Tool Schemas**: Broker caches automatically
4. **Filter by Server**: Restrict which MCP servers agents can access
5. **Monitor Tool Usage**: Track which tools agents actually use

## Troubleshooting

### Tools Not Discovered

- Check MCP server configuration
- Verify servers are running
- Check broker logs for errors

### Tool Calls Failing

- Verify tool is in agent allowlist
- Check tool_id format (server:tool_name)
- Ensure MCP server is accessible

### High Token Usage

- Use proxy mode instead of hydration
- Reduce number of tools in allowlist
- Cache tool schemas (automatic)

## Security Considerations

1. **Default Deny**: Agents start with empty allowlist
2. **Pattern Matching**: Use patterns carefully (e.g., `github:*`)
3. **Server Isolation**: Restrict which servers agents can access
4. **Audit Logging**: Log all tool calls (future enhancement)

## Future Enhancements

- ToolHive MCP Optimizer integration
- Tool usage analytics
- Automatic allowlist suggestions
- Tool dependency resolution
- Multi-broker support for redundancy

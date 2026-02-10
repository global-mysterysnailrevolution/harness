# Tool Broker Agent

## Purpose
Provides unified access to MCP tools with discovery, allowlisting, and on-demand hydration to reduce token usage.

## Responsibilities
- Discover tools from configured MCP servers
- Enforce per-agent tool allowlists
- Provide tool search functionality
- Enable proxy tool calling (avoids schema injection)
- Support on-demand tool schema hydration
- Cache tool schemas to reduce redundant lookups

## Core Functions

### search_tools(query, tags, allow_servers, max_results)
Searches for tools matching query. Returns lightweight metadata (not full schemas) to save tokens.

**Returns:**
```json
[
  {
    "tool_id": "server:tool_name",
    "name": "tool_name",
    "short_desc": "Brief description",
    "server": "server_name",
    "confidence": 0.85
  }
]
```

### describe_tool(tool_id)
Returns full tool schema with examples. Useful for understanding tool capabilities before calling.

### call_tool(tool_id, args)
Calls a tool via proxy. Avoids injecting full schema into agent context - just passes args and returns result.

### load_tools(tool_ids)
Loads full tool schemas for frameworks that support dynamic tool registration. Returns list of MCP tool definitions.

## Integration

### With Supervisor
- Supervisor queries broker for available tools
- Broker filters by agent allowlist
- Supervisor injects only allowed tools into agent context

### With Context Builder
- Context builder uses broker to discover documentation tools
- Broker provides web search, GitHub API, etc. as tools
- Context builder calls tools via broker proxy

### With Wheel-Scout
- Wheel-Scout uses broker to search for existing solutions
- Broker provides research tools (web search, repo search)
- Results filtered by Wheel-Scout's tool profile

## Tool Allowlists

Per-agent allowlists stored in `ai/supervisor/allowlists.json`:

```json
{
  "agent_id": {
    "allow": ["github:*", "web_search"],
    "deny": ["dangerous_tool"],
    "servers": ["github", "web"]
  }
}
```

## Implementation

- Python: `scripts/broker/tool_broker.py`
- Node.js: `scripts/broker/tool_broker.js`
- Discovery: `scripts/broker/discovery.py`
- Allowlist Manager: `scripts/broker/allowlist_manager.py`

## Benefits

1. **Token Reduction**: Only meta-tools in agent context, not 50+ tool schemas
2. **Security**: Per-agent allowlists prevent unauthorized tool access
3. **Flexibility**: On-demand tool loading for dynamic frameworks
4. **Unified Interface**: Single endpoint for all MCP tools

## Future Enhancements

- ToolHive MCP Optimizer integration (hybrid approach)
- Custom broker fallback if ToolHive unavailable
- Tool usage analytics
- Automatic allowlist suggestions based on agent behavior

# Harness Tool Broker Skill

This skill exposes the harness tool broker to OpenClaw agents without requiring MCP support.

## Commands

### `harness_search_tools`
Search for available tools.

**Parameters:**
- `query` (string, required): Search query
- `max_results` (number, optional, default: 10): Maximum results to return
- `agent_id` (string, optional): Agent ID for allowlist filtering

**Returns:** List of tool metadata (tool_id, name, short_desc, server, confidence)

**Example:**
```json
{
  "command": "harness_search_tools",
  "args": {
    "query": "browser automation",
    "max_results": 5,
    "agent_id": "web-runner"
  }
}
```

### `harness_describe_tool`
Get full schema for a specific tool.

**Parameters:**
- `tool_id` (string, required): Tool ID (format: "server:tool_name")
- `agent_id` (string, optional): Agent ID for allowlist filtering

**Returns:** Full tool schema with description, parameters, examples

**Example:**
```json
{
  "command": "harness_describe_tool",
  "args": {
    "tool_id": "playwright:screenshot",
    "agent_id": "web-runner"
  }
}
```

### `harness_call_tool`
Call a tool via proxy.

**Parameters:**
- `tool_id` (string, required): Tool ID
- `args` (object, required): Tool arguments
- `agent_id` (string, optional): Agent ID for allowlist filtering

**Returns:** Tool execution result

**Example:**
```json
{
  "command": "harness_call_tool",
  "args": {
    "tool_id": "playwright:screenshot",
    "args": {
      "url": "https://example.com"
    },
    "agent_id": "web-runner"
  }
}
```

### `harness_load_tools`
Load full tool schemas for direct tool calling.

**Parameters:**
- `tool_ids` (array, required): List of tool IDs
- `agent_id` (string, optional): Agent ID for allowlist filtering

**Returns:** List of full MCP tool definitions

**Example:**
```json
{
  "command": "harness_load_tools",
  "args": {
    "tool_ids": ["playwright:screenshot", "playwright:click"],
    "agent_id": "web-runner"
  }
}
```

## Implementation

This skill calls `scripts/broker/tool_broker.py` via Python subprocess and returns JSON results.

**Important**: This is a CLI wrapper, not a magically new OpenClaw tool. To use it, you must:

1. **Register as OpenClaw skill** (recommended):
   - Copy `harness_skill_wrapper.py` to OpenClaw skills directory
   - Register in OpenClaw config as executable skill
   - Agents can then call skill commands

2. **Use restricted exec** (alternative):
   - Allow only: `python3 scripts/broker/tool_broker.py <command> --args <json>`
   - Configure OpenClaw exec approval flow
   - Agents call via restricted exec

3. **Run broker as HTTP service** (cleanest):
   - Start broker on `localhost:8000`
   - Agents call via HTTP (no shell access needed)
   - See `docker-compose.yml` for service mode

## Security

- All tool calls are filtered by agent allowlists
- Tool discovery uses VPS-local registry (`ai/supervisor/mcp.servers.json`)
- ToolHive gateway supported if `TOOLHIVE_GATEWAY_URL` is set

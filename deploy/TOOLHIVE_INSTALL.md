# ToolHive Installation Status

## Current Status

âŒ **ToolHive npm package not available**: @stacklok/toolhive doesn't exist in npm registry

## Installation Options

### Option 1: Build from Source (Recommended)

ToolHive needs to be built from source. See: https://github.com/stacklok/toolhive

`ash
# Clone and build
cd /opt
git clone https://github.com/stacklok/toolhive.git
cd toolhive
# Follow build instructions in README
`

### Option 2: Use Docker (if image exists)

`ash
docker pull stacklok/toolhive:latest
# Or build from source Dockerfile
`

### Option 3: Alternative MCP Gateway

For now, the broker works without ToolHive:
- Direct MCP server connections
- Tool discovery from mcp.servers.json
- ToolHive integration is optional enhancement

## Current Setup

âœ… **Environment variables configured**:
- /opt/harness/.env created
- TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080 (ready when ToolHive is installed)
- Broker service loads .env automatically

âœ… **Broker works without ToolHive**:
- Uses direct MCP connections
- Tool discovery from registry files
- ToolHive is optional for containerization/security

## Next Steps

1. Check ToolHive GitHub for latest installation method
2. Build/install ToolHive when ready
3. Set WANDB_API_KEY in .env for Weave tracing
4. Broker will automatically use ToolHive when available

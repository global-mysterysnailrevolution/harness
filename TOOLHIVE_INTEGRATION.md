# ToolHive Integration Guide

## Overview

ToolHive is a platform for running MCP servers securely in isolated containers, with registry/gateway/portal + secret management. This harness integrates with ToolHive to provide:

- **Secure MCP server execution** in isolated containers
- **Unified tool discovery** via ToolHive gateway
- **Token reduction** via ToolHive MCP Optimizer
- **Secret management** and access controls

## Architecture

```
Agent → Tool Broker → ToolHive Gateway → MCP Servers (containers)
```

The tool broker automatically uses ToolHive if `TOOLHIVE_GATEWAY_URL` is set.

## Setup

### 1. Install ToolHive

```bash
# Using Docker (recommended)
docker run -d \
  --name toolhive \
  -p 8080:8080 \
  -v toolhive-data:/data \
  stacklok/toolhive:latest

# Or using npm
npm install -g @stacklok/toolhive
```

### 2. Configure Environment

Set the ToolHive gateway URL:

```powershell
# Windows PowerShell
$env:TOOLHIVE_GATEWAY_URL = "http://localhost:8080"

# Linux/Mac
export TOOLHIVE_GATEWAY_URL=http://localhost:8080
```

Or add to your `.env` file:

```env
TOOLHIVE_GATEWAY_URL=http://localhost:8080
```

### 3. Register MCP Servers

Register your MCP servers with ToolHive:

```bash
# Via ToolHive CLI
toolhive register \
  --name playwright \
  --command npx \
  --args "@modelcontextprotocol/server-playwright"

# Or via API
curl -X POST http://localhost:8080/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "playwright",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-playwright"]
  }'
```

### 4. Configure Tool Broker

The tool broker automatically detects ToolHive if `TOOLHIVE_GATEWAY_URL` is set. No additional configuration needed.

## Usage

### Tool Discovery

The tool broker automatically uses ToolHive gateway for discovery:

```python
from scripts.broker.tool_broker import ToolBroker

broker = ToolBroker()
tools = broker.search_tools("browser automation")
# Tools discovered via ToolHive gateway
```

### Tool Calling

Tool calls are routed through ToolHive:

```python
result = broker.call_tool(
    "playwright:screenshot",
    {"url": "https://example.com"},
    agent_id="web-runner"
)
# Executed in isolated container via ToolHive
```

## ToolHive MCP Optimizer

The MCP Optimizer provides unified access + tool discovery/routing to reduce token usage.

### Enable Optimizer

Set the optimizer endpoint:

```env
TOOLHIVE_OPTIMIZER_URL=http://localhost:8080/optimizer
```

The tool broker will use the optimizer for:
- Tool search (unified across all servers)
- Tool routing (intelligent server selection)
- Token reduction (meta-tools only)

## Security

ToolHive provides:

- **Container isolation**: Each MCP server runs in its own container
- **Secret management**: Secrets scoped per server/agent
- **Access controls**: Per-agent tool allowlists
- **Network controls**: Isolated network per container

## Production Deployment

### Docker Compose

```yaml
version: '3.8'
services:
  toolhive:
    image: stacklok/toolhive:latest
    ports:
      - "8080:8080"
    volumes:
      - toolhive-data:/data
    environment:
      - TOOLHIVE_SECRET_KEY=your-secret-key

  harness:
    # Your harness service
    environment:
      - TOOLHIVE_GATEWAY_URL=http://toolhive:8080
```

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: toolhive-config
data:
  TOOLHIVE_GATEWAY_URL: "http://toolhive-service:8080"
```

## Troubleshooting

### ToolHive Not Detected

1. Check `TOOLHIVE_GATEWAY_URL` is set
2. Verify ToolHive is running: `curl http://localhost:8080/health`
3. Check tool broker logs for connection errors

### Tool Calls Failing

1. Verify MCP server is registered in ToolHive
2. Check container logs: `docker logs toolhive`
3. Verify agent allowlist includes the tool

### Performance Issues

1. Use ToolHive Optimizer for token reduction
2. Enable tool caching in broker config
3. Monitor ToolHive metrics

## References

- [ToolHive GitHub](https://github.com/stacklok/toolhive)
- [ToolHive Documentation](https://docs.stacklok.com/toolhive/)
- [MCP Optimizer Tutorial](https://docs.stacklok.com/toolhive/tutorials/mcp-optimizer)

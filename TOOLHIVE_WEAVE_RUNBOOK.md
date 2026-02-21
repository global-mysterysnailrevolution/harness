# ToolHive + Weave Integration Runbook

## Overview

This runbook explains how to set up ToolHive and Weave tracing for the harness Tool Broker on the VPS.

## Prerequisites

- Docker installed and running
- Python 3.12+ with pip
- Access to VPS via Tailscale SSH

## Step 1: Install ToolHive

ToolHive can be installed via Docker or npm. For VPS deployment, Docker is recommended.

### Option A: Docker (Recommended)

```bash
# Create volume
docker volume create toolhive-data

# Run ToolHive (localhost-only, no public exposure)
docker run -d \
  --name toolhive \
  -p 127.0.0.1:8080:8080 \
  -v toolhive-data:/data \
  stacklok/toolhive:latest
```

**Note:** If the Docker image doesn't exist, ToolHive may need to be built from source or installed via npm. See [ToolHive GitHub](https://github.com/stacklok/toolhive) for latest installation instructions.

### Option B: npm

```bash
npm install -g @stacklok/toolhive
toolhive start --port 8080 --bind 127.0.0.1
```

### Verify Installation

```bash
curl http://127.0.0.1:8080/health
```

## Step 2: Configure Environment Variables

Set the ToolHive gateway URL:

```bash
export TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080
```

For persistent configuration, add to `/opt/harness/.env` or systemd service environment:

```env
TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080
WANDB_API_KEY=your-wandb-api-key
WEAVE_PROJECT=globalmysterysnailrevolution/tool-broker
```

## Step 3: Install Python Dependencies

```bash
cd /opt/harness
source venv/bin/activate
pip install weave wandb requests flask
```

Or install from requirements:

```bash
pip install -r requirements.txt
```

## Step 4: Register MCP Servers

Register your first MCP server (e.g., Playwright):

```bash
# Via ToolHive API
curl -X POST http://127.0.0.1:8080/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "playwright",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-playwright"]
  }'
```

Or use the ToolHive CLI (if installed):

```bash
toolhive register \
  --name playwright \
  --command npx \
  --args "@modelcontextprotocol/server-playwright"
```

## Step 5: Verify Integration

Run the smoke test script:

```bash
cd /opt/harness
bash scripts/demo_toolhive_weave.sh
```

Or test manually:

```bash
# Test broker search
python3 scripts/broker/tool_broker.py search --query "browser" --agent-id "test"

# Test tool discovery
python3 scripts/broker/tool_broker.py describe --tool-id "playwright:screenshot"

# Test tool call (if tool is registered)
python3 scripts/broker/tool_broker.py call --tool-id "playwright:screenshot" --args '{"url":"https://example.com"}' --agent-id "test"
```

## Step 6: Verify Weave Tracing

1. Set `WANDB_API_KEY` environment variable
2. Run a broker operation
3. Check Weave dashboard: https://wandb.ai/globalmysterysnailrevolution/tool-broker

Traces should appear automatically for:
- `search_tools`
- `describe_tool`
- `call_tool`
- `load_tools`

## Troubleshooting

### ToolHive Not Starting

- Check Docker logs: `docker logs toolhive`
- Verify port 8080 is not in use: `lsof -i:8080`
- Try different ToolHive installation method (npm vs Docker)

### ToolHive Endpoints Not Found

The broker's `ToolHiveClient` will automatically discover endpoints. If discovery fails:

1. Check ToolHive is running: `curl http://127.0.0.1:8080/health`
2. Try OpenAPI discovery: `curl http://127.0.0.1:8080/openapi.json`
3. Check broker logs for discovered endpoints

### Weave Not Tracing

- Verify `WANDB_API_KEY` is set: `echo $WANDB_API_KEY`
- Check Weave is installed: `pip list | grep weave`
- Verify initialization: Look for "Weave tracing initialized" in broker logs
- Check Weave project name matches: `echo $WEAVE_PROJECT`

### Tool Calls Failing

1. Verify MCP server is registered: `curl http://127.0.0.1:8080/api/servers`
2. Check tool is available: `curl http://127.0.0.1:8080/api/tools`
3. Verify agent allowlist includes the tool
4. Check ToolHive container logs: `docker logs toolhive`

## Service Management

### Start ToolHive

```bash
docker start toolhive
```

### Stop ToolHive

```bash
docker stop toolhive
```

### Restart ToolHive

```bash
docker restart toolhive
```

### View ToolHive Logs

```bash
docker logs -f toolhive
```

### Auto-start ToolHive on Boot

Create systemd service:

```bash
cat > /etc/systemd/system/toolhive.service << 'EOF'
[Unit]
Description=ToolHive MCP Gateway
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/docker start toolhive
ExecStop=/usr/bin/docker stop toolhive

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable toolhive
systemctl start toolhive
```

## Security Notes

- ToolHive binds to `127.0.0.1` only (localhost)
- No public ports exposed
- All tool calls go through broker allowlist/approval workflow
- Secrets are redacted in Weave traces

## Next Steps

1. Register additional MCP servers as needed
2. Configure agent-specific allowlists
3. Monitor Weave traces for broker operations
4. Set up alerts for failed tool calls

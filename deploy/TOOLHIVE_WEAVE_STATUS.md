# ToolHive + Weave Integration Status

## âœ… Completed

1. **Weave Tracing Module**: scripts/observability/weave_tracing.py
   - Secret redaction
   - Automatic tracing decorators
   - Idempotent initialization

2. **ToolHive Client Adapter**: scripts/broker/toolhive_client.py
   - Endpoint discovery
   - Server registration
   - Tool listing and calling

3. **Broker Integration**: Updated scripts/broker/tool_broker.py
   - Weave decorators on all broker methods
   - ToolHive client integration
   - Automatic fallback to direct MCP

4. **Smoke Test Script**: scripts/demo_toolhive_weave.sh
   - End-to-end verification
   - ToolHive health checks
   - Broker operation tests

5. **Dependencies Installed**:
   - weave 0.52.26
   - wandb 0.24.2
   - requests 2.32.5

## âš ï¸ Pending

1. **ToolHive Installation**: Docker image stacklok/toolhive:latest not available
   - Need to install via npm or build from source
   - See: https://github.com/stacklok/toolhive

2. **Environment Variables**:
   - Set WANDB_API_KEY to enable Weave tracing
   - Set TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080 when ToolHive is running
   - Set WEAVE_PROJECT=globalmysterysnailrevolution/tool-broker (optional)

## Testing

`ash
# Test broker with Weave (requires WANDB_API_KEY)
export WANDB_API_KEY=your-key
cd /opt/harness
python3 scripts/broker/tool_broker.py search --query  test

# Run smoke test
bash scripts/demo_toolhive_weave.sh
`

## Next Steps

1. Install ToolHive (npm or build from source)
2. Set WANDB_API_KEY
3. Register MCP servers with ToolHive
4. Verify traces in Weave dashboard

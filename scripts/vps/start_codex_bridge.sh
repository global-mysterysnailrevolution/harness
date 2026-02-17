#!/bin/bash
# Start the Codex MCP bridge with HTTPS certs
set -e

# Kill existing
if [ -f /tmp/mcp-bridges/mcp-codex.pid ]; then
    pid=$(cat /tmp/mcp-bridges/mcp-codex.pid)
    kill "$pid" 2>/dev/null || true
    pkill -P "$pid" 2>/dev/null || true
    rm -f /tmp/mcp-bridges/mcp-codex.pid
fi
pkill -f 'bridge.js --port 8105' 2>/dev/null || true
sleep 2

# Source env for HTTPS certs and bearer token
cd /opt/harness/scripts
if [ -f /opt/harness/.env ]; then
    set -a
    source /opt/harness/.env
    set +a
fi

export MCP_BIND=0.0.0.0

# Start bridge
nohup node mcp_stdio_to_http_bridge.js --port 8105 -- codex mcp-server > /var/log/openclaw_codex_bridge.log 2>&1 &
echo $! > /tmp/mcp-bridges/mcp-codex.pid
echo "Codex bridge started (PID $!)"

sleep 4
echo ""
echo "Bridge log:"
head -5 /var/log/openclaw_codex_bridge.log

echo ""
echo "Port check:"
ss -tlnp | grep 8105 || echo "  Not listening yet"

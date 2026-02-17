#!/bin/bash
set -e

echo "=== Stopping old bridges ==="
for f in /tmp/mcp-bridges/*.pid; do
    [ -f "$f" ] || continue
    pid=$(cat "$f" 2>/dev/null)
    if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null || true
        # Also kill children
        pkill -P "$pid" 2>/dev/null || true
        echo "  Killed pid $pid ($(basename "$f"))"
    fi
    rm -f "$f"
done
sleep 2

echo "=== Starting bridges ==="
export MCP_BIND=0.0.0.0
cd /opt/harness/scripts
bash /opt/harness/scripts/run_mcp_from_config.sh &
BGPID=$!
sleep 5

echo ""
echo "=== Testing bridges ==="
for port in 8101 8102 8104; do
    resp=$(curl -s --max-time 10 -X POST "http://127.0.0.1:${port}/mcp" \
        -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' 2>&1)
    if echo "$resp" | grep -q "serverInfo"; then
        echo "  Port $port: OK"
    else
        echo "  Port $port: FAIL ($resp)"
    fi
done

echo ""
echo "=== Bridge PIDs ==="
ls -la /tmp/mcp-bridges/

echo ""
echo "=== Ports ==="
ss -tlnp | grep 810 || echo "  No bridges on 810x"

#!/bin/bash
# Smoke test script for ToolHive + Weave integration

set -e

echo "=== ToolHive + Weave Integration Smoke Test ==="
echo ""

# Check if ToolHive is running
echo "1. Checking ToolHive status..."
if docker ps | grep -q toolhive; then
    echo "   ✅ ToolHive container is running"
    TOOLHIVE_RUNNING=true
else
    echo "   ⚠️  ToolHive container not found. Starting it..."
    docker volume create toolhive-data 2>/dev/null || true
    docker rm -f toolhive 2>/dev/null || true
    
    # Try to start ToolHive (may fail if image doesn't exist)
    if docker run -d --name toolhive -p 127.0.0.1:8080:8080 -v toolhive-data:/data stacklok/toolhive:latest 2>/dev/null; then
        echo "   ✅ ToolHive started"
        sleep 5
        TOOLHIVE_RUNNING=true
    else
        echo "   ⚠️  ToolHive image not available. Install ToolHive manually."
        echo "   See: https://github.com/stacklok/toolhive"
        TOOLHIVE_RUNNING=false
    fi
fi

# Check ToolHive health
if [ "$TOOLHIVE_RUNNING" = true ]; then
    echo ""
    echo "2. Checking ToolHive health endpoint..."
    if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "   ✅ ToolHive health check passed"
        curl -s http://127.0.0.1:8080/health | python3 -m json.tool 2>/dev/null || echo "   (Health endpoint responded)"
    else
        echo "   ⚠️  ToolHive health check failed (may still be starting)"
    fi
    
    # Discover endpoints
    echo ""
    echo "3. Discovering ToolHive endpoints..."
    export TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080
    python3 << 'PYEOF'
import sys
sys.path.insert(0, 'scripts/broker')
try:
    from toolhive_client import ToolHiveClient
    client = ToolHiveClient()
    if client.is_available():
        print("   ✅ ToolHive client initialized")
        servers = client.list_servers()
        print(f"   Found {len(servers)} registered servers")
        tools = client.list_tools()
        print(f"   Found {len(tools)} available tools")
    else:
        print("   ⚠️  ToolHive client not available")
except Exception as e:
    print(f"   ⚠️  ToolHive client error: {e}")
PYEOF
fi

# Check Weave setup
echo ""
echo "4. Checking Weave tracing setup..."
python3 << 'PYEOF'
import sys
import os
sys.path.insert(0, 'scripts/observability')
try:
    from weave_tracing import init_weave
    if os.getenv("WANDB_API_KEY"):
        if init_weave():
            print("   ✅ Weave tracing initialized")
        else:
            print("   ⚠️  Weave initialization failed (check WANDB_API_KEY)")
    else:
        print("   ⚠️  WANDB_API_KEY not set (Weave disabled)")
except ImportError as e:
    print(f"   ⚠️  Weave not installed: {e}")
    print("   Install with: pip install weave wandb")
PYEOF

# Test broker search
echo ""
echo "5. Testing broker search_tools..."
export TOOLHIVE_GATEWAY_URL=http://127.0.0.1:8080
python3 << 'PYEOF'
import sys
import os
sys.path.insert(0, 'scripts/broker')
sys.path.insert(0, 'scripts/observability')
try:
    from tool_broker import ToolBroker
    broker = ToolBroker()
    results = broker.search_tools("browser automation", max_results=3, agent_id="test-agent")
    print(f"   ✅ Search returned {len(results)} results")
    if results:
        print(f"   First result: {results[0].get('name', 'N/A')}")
except Exception as e:
    print(f"   ⚠️  Broker search failed: {e}")
PYEOF

# Test broker describe
echo ""
echo "6. Testing broker describe_tool..."
python3 << 'PYEOF'
import sys
import os
sys.path.insert(0, 'scripts/broker')
try:
    from tool_broker import ToolBroker
    broker = ToolBroker()
    # Try to describe a tool (may fail if no tools available)
    schema = broker.describe_tool("test:tool", agent_id="test-agent")
    if schema:
        print("   ✅ Tool schema retrieved")
    else:
        print("   ⚠️  No tool found (expected if no tools registered)")
except Exception as e:
    print(f"   ⚠️  Broker describe failed: {e}")
PYEOF

echo ""
echo "=== Smoke Test Complete ==="
echo ""
echo "Next steps:"
echo "1. Set WANDB_API_KEY to enable Weave tracing"
echo "2. Register MCP servers with ToolHive (if not already done)"
echo "3. Test tool calls: python3 scripts/broker/tool_broker.py call --tool-id <id> --args '{}'"

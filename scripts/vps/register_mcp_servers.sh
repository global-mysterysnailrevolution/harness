#!/bin/bash
# Register MCP servers with MCPJungle gateway and create tool groups.
# Run after MCPJungle is up: bash scripts/vps/register_mcp_servers.sh
#
# Reads server definitions from ai/supervisor/mcp_bridges.json
# and creates tool groups from ai/supervisor/allowlists.json.

set -e
HARNESS_DIR="${HARNESS_DIR:-/opt/harness}"
MCPJUNGLE_URL="${MCPJUNGLE_GATEWAY_URL:-http://localhost:8000}"
BRIDGES_CONFIG="$HARNESS_DIR/ai/supervisor/mcp_bridges.json"
ALLOWLISTS="$HARNESS_DIR/ai/supervisor/allowlists.json"

[ -f "$HARNESS_DIR/.env" ] && set -a && source "$HARNESS_DIR/.env" && set +a

info() { echo "[mcpjungle] $*"; }

# Wait for MCPJungle to be ready
wait_ready() {
  local tries=0
  while ! curl -sf "$MCPJUNGLE_URL/health" > /dev/null 2>&1; do
    tries=$((tries + 1))
    if [ $tries -gt 30 ]; then
      echo "[mcpjungle] ERROR: Gateway not responding at $MCPJUNGLE_URL"
      exit 1
    fi
    sleep 2
  done
  info "Gateway ready at $MCPJUNGLE_URL"
}

# Register a single MCP server
register_server() {
  local name="$1" command="$2" transport="${3:-stdio}"
  shift 3
  local args_json="$*"

  # Check if already registered
  if curl -sf "$MCPJUNGLE_URL/api/servers/$name" > /dev/null 2>&1; then
    info "Server '$name' already registered"
    return
  fi

  local payload
  payload=$(python3 -c "
import json, sys
print(json.dumps({
    'name': '$name',
    'command': '$command',
    'args': json.loads('$args_json') if '$args_json' else [],
    'transport': '$transport',
}))
")

  local status
  status=$(curl -sf -o /dev/null -w '%{http_code}' \
    -X POST "$MCPJUNGLE_URL/api/servers" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    info "Registered server: $name"
  else
    info "WARN: Failed to register $name (HTTP $status)"
  fi
}

# Register servers from mcp_bridges.json
register_from_config() {
  if [ ! -f "$BRIDGES_CONFIG" ]; then
    info "No mcp_bridges.json found, registering defaults"
    register_server "filesystem" "npx" "stdio" '["-y","@modelcontextprotocol/server-filesystem","/harness/ai"]'
    register_server "everything" "npx" "stdio" '["-y","@modelcontextprotocol/server-everything"]'
    register_server "memory" "npx" "stdio" '["-y","@modelcontextprotocol/server-memory"]'
    return
  fi

  info "Registering servers from $BRIDGES_CONFIG"
  python3 -c "
import json, subprocess, sys

with open('$BRIDGES_CONFIG') as f:
    config = json.load(f)

for name, cfg in config.get('bridges', {}).items():
    if not cfg.get('enabled', True):
        continue
    if name == 'github' and not __import__('os').environ.get('GITHUB_PERSONAL_ACCESS_TOKEN'):
        continue
    cmd = cfg.get('command', '')
    args = json.dumps([a.replace('\${HARNESS_DIR}', '/harness') for a in cfg.get('args', [])])
    print(f'{name}|{cmd}|{args}')
" | while IFS='|' read -r name cmd args_json; do
    [ -n "$name" ] && register_server "$name" "$cmd" "stdio" "$args_json"
  done
}

# Create tool groups from allowlists
create_tool_groups() {
  if [ ! -f "$ALLOWLISTS" ]; then
    info "No allowlists.json, skipping tool groups"
    return
  fi

  info "Creating tool groups from allowlists"
  python3 -c "
import json, os

with open('$ALLOWLISTS') as f:
    data = json.load(f)

for agent, config in data.items():
    if agent == 'default':
        continue
    servers = config.get('servers', [])
    if not servers:
        continue
    print(f'{agent}|{json.dumps(servers)}')
" | while IFS='|' read -r group_name servers_json; do
    [ -z "$group_name" ] && continue

    payload=$(python3 -c "
import json
print(json.dumps({
    'name': '$group_name',
    'servers': json.loads('$servers_json'),
}))
")

    curl -sf -X POST "$MCPJUNGLE_URL/api/groups" \
      -H "Content-Type: application/json" \
      -d "$payload" > /dev/null 2>&1 \
      && info "Created tool group: $group_name" \
      || info "Tool group '$group_name' may already exist"
  done
}

# --- Main ---
wait_ready
register_from_config
create_tool_groups

info "Done. MCPJungle status:"
curl -sf "$MCPJUNGLE_URL/api/servers" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "(could not list servers)"

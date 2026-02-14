#!/bin/bash
# Run MCP stdio-to-HTTP bridges from mcp_bridges.json.
# Only starts servers that aren't already running. Add entries to config to add new MCP servers.
# Env: MCP_BIND, MCP_BEARER_TOKEN, GITHUB_PERSONAL_ACCESS_TOKEN, HARNESS_DIR

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="${HARNESS_DIR:-$(dirname "$SCRIPT_DIR")}"
CONFIG="${HARNESS_DIR}/ai/supervisor/mcp_bridges.json"
BRIDGE_JS="${SCRIPT_DIR}/mcp_stdio_to_http_bridge.js"

[ -f "${HARNESS_DIR}/.env" ] && set -a && source "${HARNESS_DIR}/.env" && set +a

mkdir -p /tmp/mcp-bridges
cd "$SCRIPT_DIR"

if [[ ! -f "$CONFIG" ]]; then
  echo "[mcp] No mcp_bridges.json, falling back to run_mcp_servers.sh"
  exec ./run_mcp_servers.sh
fi

start_bridge() {
  local name=$1 port=$2
  shift 2
  local pidfile="/tmp/mcp-bridges/mcp-$name.pid"

  if [[ -f "$pidfile" ]]; then
    local oldpid
    oldpid=$(cat "$pidfile")
    if kill -0 "$oldpid" 2>/dev/null; then
      echo "[$name] Already running on port $port (PID $oldpid)"
      return
    fi
  fi

  node "$BRIDGE_JS" --port "$port" -- "$@" &
  echo $! > "$pidfile"
  echo "[$name] Started on port $port (PID $(cat $pidfile))"
}

# Use record separator (ASCII 30) to avoid collisions with paths
SEP=$'\x1e'
while IFS="$SEP" read -r name port cmd args_str; do
  [[ -z "$name" ]] && continue
  if [[ "$name" == "github" ]] && [[ -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ]]; then
    echo "[$name] Skipped (set GITHUB_PERSONAL_ACCESS_TOKEN to enable)"
    continue
  fi
  args=()
  [[ -n "$args_str" ]] && IFS="$SEP" read -ra args <<< "$args_str"
  for i in "${!args[@]}"; do
    args[i]="${args[i]//\$\{HARNESS_DIR\}/$HARNESS_DIR}"
  done
  start_bridge "$name" "$port" "$cmd" "${args[@]}"
done < <(python3 -c "
import json, os
sep = chr(30)
with open('$CONFIG') as f:
    d = json.load(f)
for name, cfg in d.get('bridges', {}).items():
    if not cfg.get('enabled', True):
        continue
    port = cfg.get('port')
    cmd = cfg.get('command')
    args = [a.replace('\${HARNESS_DIR}', '$HARNESS_DIR') for a in cfg.get('args', [])]
    if not port or not cmd:
        continue
    print(sep.join([name, str(port), cmd, sep.join(args)]))
")

PROTO="${MCP_HTTPS_CERT:+https}"
PROTO="${PROTO:-http}"
HOST="${MCP_BIND:-127.0.0.1}"
[[ "$MCP_BIND" == "0.0.0.0" ]] && HOST="172.18.0.1"

echo ""
echo "MCP bridges (from config). Add to OpenClaw:"
python3 -c "
import json, os
with open('$CONFIG') as f:
    d = json.load(f)
for name, cfg in d.get('bridges', {}).items():
    if cfg.get('enabled', True) and cfg.get('port'):
        print(f\"  {name}: ${PROTO}://${HOST}:{cfg['port']}/mcp\")
"
echo ""

wait

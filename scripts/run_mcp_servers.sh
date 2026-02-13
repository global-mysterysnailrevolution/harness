#!/bin/bash
# Run MCP stdio-to-HTTP bridges for OpenClaw on VPS
# Usage: ./run_mcp_servers.sh
# Env: load from /opt/harness/.env (MCP_BEARER_TOKEN, MCP_HTTPS_*, MCP_BIND, GITHUB_PERSONAL_ACCESS_TOKEN)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(dirname "$SCRIPT_DIR")"
ALLOWED_FS="${HARNESS_DIR}/ai"

[ -f "${HARNESS_DIR}/.env" ] && set -a && source "${HARNESS_DIR}/.env" && set +a

export NODE_PATH="${NODE_PATH:-}"
mkdir -p /tmp/mcp-bridges
cd "$SCRIPT_DIR"

start_bridge() {
  local name=$1 port=$2
  shift 2
  local pidfile="/tmp/mcp-bridges/mcp-$name.pid"
  if [ -f "$pidfile" ]; then
    local oldpid=$(cat "$pidfile")
    if kill -0 "$oldpid" 2>/dev/null; then
      echo "[$name] Already running on port $port (PID $oldpid)"
      return
    fi
  fi
  node mcp_stdio_to_http_bridge.js --port "$port" -- "$@" &
  echo $! > "$pidfile"
  echo "[$name] Started on port $port (PID $(cat $pidfile))"
}

mkdir -p "$ALLOWED_FS"
start_bridge filesystem 8101 npx -y @modelcontextprotocol/server-filesystem "$ALLOWED_FS"
start_bridge everything 8102 npx -y @modelcontextprotocol/server-everything
start_bridge memory 8104 npx -y @modelcontextprotocol/server-memory

if [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
  export GITHUB_PERSONAL_ACCESS_TOKEN
  start_bridge github 8103 npx -y @modelcontextprotocol/server-github
else
  echo "[github] Skipped (set GITHUB_PERSONAL_ACCESS_TOKEN to enable)"
fi

PROTO="${MCP_HTTPS_CERT:+https}"
PROTO="${PROTO:-http}"
HOST="${MCP_BIND:-127.0.0.1}"
[ "$MCP_BIND" = "0.0.0.0" ] && HOST="172.18.0.1"

echo ""
echo "MCP bridges running. Add to OpenClaw config:"
echo "  filesystem: ${PROTO}://${HOST}:8101/mcp"
echo "  everything: ${PROTO}://${HOST}:8102/mcp"
echo "  memory:     ${PROTO}://${HOST}:8104/mcp"
echo "  github:     ${PROTO}://${HOST}:8103/mcp (if token set)"
echo ""

wait

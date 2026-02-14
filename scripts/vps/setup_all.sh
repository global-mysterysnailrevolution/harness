#!/bin/bash
# Full harness setup on VPS - runs from prompt trigger or manual invocation.
# Usage: ./setup_all.sh [--token TOKEN]
# Env: HARNESS_DIR (default /opt/harness), OPENCLAW_CONFIG, OPENCLAW_WORKSPACE

set -e
HARNESS_DIR="${HARNESS_DIR:-/opt/harness}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-/docker/openclaw-kx9d/data/.openclaw/openclaw.json}"
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-/docker/openclaw-kx9d/data/.openclaw/workspace}"
TOKEN=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --token) TOKEN="$2"; shift 2 ;;
    *) shift ;;
  esac
done

cd "$HARNESS_DIR"
echo "[setup] Harness dir: $HARNESS_DIR"

# 1. Git pull
if [[ -d .git ]]; then
  git pull --quiet 2>/dev/null || true
fi

# 2. Write token to .env if provided
if [[ -n "$TOKEN" ]]; then
  ENV_FILE="$HARNESS_DIR/.env"
  if [[ "$TOKEN" =~ ^sk-ant-|^sk-proj- ]]; then
    grep -q "^ANTHROPIC_API_KEY=" "$ENV_FILE" 2>/dev/null && sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$TOKEN|" "$ENV_FILE" || echo "ANTHROPIC_API_KEY=$TOKEN" >> "$ENV_FILE"
  elif [[ "$TOKEN" =~ ^sk- ]]; then
    grep -q "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null && sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$TOKEN|" "$ENV_FILE" || echo "OPENAI_API_KEY=$TOKEN" >> "$ENV_FILE"
  else
    grep -q "^OPENCLAW_TOKEN=" "$ENV_FILE" 2>/dev/null && sed -i "s|^OPENCLAW_TOKEN=.*|OPENCLAW_TOKEN=$TOKEN|" "$ENV_FILE" || echo "OPENCLAW_TOKEN=$TOKEN" >> "$ENV_FILE"
  fi
  echo "[setup] Token saved to .env"
fi

# 3. OpenClaw hardening
SETUP_PY="$HARNESS_DIR/scripts/openclaw_setup/apply_openclaw_hardening.py"
if [[ -f "$SETUP_PY" ]] && [[ -f "$OPENCLAW_CONFIG" ]]; then
  python3 "$SETUP_PY" --config-path "$OPENCLAW_CONFIG" --workspace-path "$OPENCLAW_WORKSPACE" 2>/dev/null && echo "[setup] OpenClaw hardening applied" || echo "[setup] OpenClaw hardening skipped"
fi

# 4. Start MCP servers (systemd or foreground)
if systemctl is-enabled harness-mcp-servers &>/dev/null; then
  systemctl start harness-mcp-servers 2>/dev/null && echo "[setup] MCP servers started" || true
elif [[ -f "$HARNESS_DIR/scripts/run_mcp_servers.sh" ]]; then
  cd "$HARNESS_DIR/scripts"
  export MCP_BIND="${MCP_BIND:-0.0.0.0}"
  nohup ./run_mcp_servers.sh >> /tmp/mcp-setup.log 2>&1 &
  echo "[setup] MCP servers launched in background"
fi

# 5. Restart OpenClaw if we patched config
if [[ -f "$OPENCLAW_CONFIG" ]]; then
  CONTAINER="${OPENCLAW_CONTAINER:-openclaw-kx9d-openclaw-1}"
  docker restart "$CONTAINER" 2>/dev/null && echo "[setup] OpenClaw restarted" || true
fi

echo "[setup] Done"

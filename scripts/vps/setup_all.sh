#!/bin/bash
# Full harness setup on VPS - runs once (or when explicitly requested).
# Usage: ./setup_all.sh [--token TOKEN] [--force]
# --force: run even if setup was already done
# Env: HARNESS_DIR, OPENCLAW_CONFIG, OPENCLAW_WORKSPACE

set -e
HARNESS_DIR="${HARNESS_DIR:-/opt/harness}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-/docker/openclaw-kx9d/data/.openclaw/openclaw.json}"
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-/docker/openclaw-kx9d/data/.openclaw/workspace}"
SETUP_FLAG="$HARNESS_DIR/ai/setup_complete.flag"
TOKEN=""
FORCE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --token) TOKEN="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) shift ;;
  esac
done

# Skip if already done (unless --force)
if [[ -f "$SETUP_FLAG" ]] && [[ -z "$FORCE" ]]; then
  echo "[setup] Already complete (use --force to re-run)"
  exit 0
fi

cd "$HARNESS_DIR"
echo "[setup] Harness dir: $HARNESS_DIR"

# 1. Git pull
if [[ -d .git ]]; then
  git pull --quiet 2>/dev/null || true
fi

# 2. Write token to .env if provided
if [[ -n "$TOKEN" ]]; then
  ENV_FILE="$HARNESS_DIR/.env"
  touch "$ENV_FILE"
  if [[ "$TOKEN" =~ ^sk-ant-|^sk-proj- ]]; then
    grep -q "^ANTHROPIC_API_KEY=" "$ENV_FILE" 2>/dev/null && sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$TOKEN|" "$ENV_FILE" || echo "ANTHROPIC_API_KEY=$TOKEN" >> "$ENV_FILE"
  elif [[ "$TOKEN" =~ ^sk- ]]; then
    grep -q "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null && sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$TOKEN|" "$ENV_FILE" || echo "OPENAI_API_KEY=$TOKEN" >> "$ENV_FILE"
  else
    grep -q "^OPENCLAW_TOKEN=" "$ENV_FILE" 2>/dev/null && sed -i "s|^OPENCLAW_TOKEN=.*|OPENCLAW_TOKEN=$TOKEN|" "$ENV_FILE" || echo "OPENCLAW_TOKEN=$TOKEN" >> "$ENV_FILE"
  fi
  echo "[setup] Token saved to .env"
fi

# 3. OpenClaw hardening (only if config exists)
CONFIG_CHANGED=""
SETUP_PY="$HARNESS_DIR/scripts/openclaw_setup/apply_openclaw_hardening.py"
if [[ -f "$SETUP_PY" ]] && [[ -f "$OPENCLAW_CONFIG" ]]; then
  BEFORE=$(md5sum "$OPENCLAW_CONFIG" 2>/dev/null | cut -d' ' -f1)
  python3 "$SETUP_PY" --config-path "$OPENCLAW_CONFIG" --workspace-path "$OPENCLAW_WORKSPACE" 2>/dev/null || true
  AFTER=$(md5sum "$OPENCLAW_CONFIG" 2>/dev/null | cut -d' ' -f1)
  [[ "$BEFORE" != "$AFTER" ]] && CONFIG_CHANGED=1
  echo "[setup] OpenClaw hardening applied"
fi

# 4. Ensure MCP servers running (config watcher handles dynamic additions)
if systemctl is-enabled harness-mcp-servers &>/dev/null; then
  systemctl start harness-mcp-servers 2>/dev/null || true
  echo "[setup] MCP servers (systemd)"
elif [[ -f "$HARNESS_DIR/scripts/run_mcp_from_config.sh" ]]; then
  cd "$HARNESS_DIR/scripts"
  export MCP_BIND="${MCP_BIND:-0.0.0.0}"
  nohup ./run_mcp_from_config.sh >> /tmp/mcp-setup.log 2>&1 &
  echo "[setup] MCP servers launched"
fi

# 5. Restart OpenClaw ONLY if we changed config
if [[ -n "$CONFIG_CHANGED" ]] && [[ -f "$OPENCLAW_CONFIG" ]]; then
  CONTAINER="${OPENCLAW_CONTAINER:-openclaw-kx9d-openclaw-1}"
  docker restart "$CONTAINER" 2>/dev/null && echo "[setup] OpenClaw restarted (config changed)" || true
else
  echo "[setup] OpenClaw not restarted (no config change)"
fi

# 6. Mark setup complete
mkdir -p "$(dirname "$SETUP_FLAG")"
touch "$SETUP_FLAG"
echo "[setup] Done"

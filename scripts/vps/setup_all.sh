#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# setup_all.sh -- One-click OpenClaw + Harness + Dashboard provisioning
# Targets: Ubuntu 22.04+ VPS with Docker pre-installed (e.g. Hostinger)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<user>/harness/main/scripts/vps/setup_all.sh | bash
#   OR
#   bash setup_all.sh [--env /path/to/setup.env] [--skip-openclaw] [--skip-tailscale]
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
trap 'echo "ERROR on line $LINENO"; exit 1' ERR

# ── Defaults (override via setup.env or flags) ──
GITHUB_HARNESS_REPO="${GITHUB_HARNESS_REPO:-global-mysterysnailrevolution/harness}"
GITHUB_DASHBOARD_REPO="${GITHUB_DASHBOARD_REPO:-global-mysterysnailrevolution/openclaw-dashboard}"
HARNESS_DIR="${HARNESS_DIR:-/opt/harness}"
DASHBOARD_DIR="${DASHBOARD_DIR:-/opt/openclaw-dashboard}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/docker/openclaw-kx9d}"
OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-kx9d-openclaw-1}"
DASHBOARD_PORT="${DASHBOARD_PORT:-7000}"
DASHBOARD_TOKEN="${DASHBOARD_TOKEN:-$(head -c 16 /dev/urandom | xxd -p)}"
SKIP_OPENCLAW=false
SKIP_TAILSCALE=false
ENV_FILE=""

# ── Parse arguments ──
while [[ $# -gt 0 ]]; do
  case $1 in
    --env) ENV_FILE="$2"; shift 2 ;;
    --skip-openclaw) SKIP_OPENCLAW=true; shift ;;
    --skip-tailscale) SKIP_TAILSCALE=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  echo "Loading config from $ENV_FILE"
  set -a; source "$ENV_FILE"; set +a
fi

log() { echo -e "\n\033[1;36m▸ $1\033[0m"; }
ok()  { echo -e "  \033[1;32m✓ $1\033[0m"; }
warn(){ echo -e "  \033[1;33m⚠ $1\033[0m"; }

echo "═══════════════════════════════════════════════════"
echo "  OpenClaw + Harness + Dashboard Setup"
echo "═══════════════════════════════════════════════════"
echo "  Harness repo: $GITHUB_HARNESS_REPO"
echo "  Dashboard repo: $GITHUB_DASHBOARD_REPO"
echo "  Harness dir: $HARNESS_DIR"
echo "  Dashboard dir: $DASHBOARD_DIR"
echo "  Dashboard port: $DASHBOARD_PORT"
echo ""

# ═══════════════════════════════════════════════════════════════════════
# 1) SYSTEM PREP
# ═══════════════════════════════════════════════════════════════════════
log "Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-pip python3-venv jq curl wget unzip xxd > /dev/null 2>&1
ok "System packages installed"

if ! command -v node &>/dev/null; then
  log "Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
  apt-get install -y -qq nodejs > /dev/null 2>&1
  ok "Node.js $(node --version) installed"
else
  ok "Node.js $(node --version) already present"
fi

if ! command -v docker &>/dev/null; then
  log "Installing Docker..."
  curl -fsSL https://get.docker.com | sh > /dev/null 2>&1
  systemctl enable --now docker
  ok "Docker installed"
else
  ok "Docker $(docker --version | cut -d' ' -f3) already present"
fi

# ═══════════════════════════════════════════════════════════════════════
# 2) TAILSCALE
# ═══════════════════════════════════════════════════════════════════════
if [[ "$SKIP_TAILSCALE" == "false" ]]; then
  if ! command -v tailscale &>/dev/null; then
    log "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh > /dev/null 2>&1
    ok "Tailscale installed"
  else
    ok "Tailscale already installed"
  fi

  TS_STATUS=$(tailscale status --json 2>/dev/null | jq -r '.BackendState // "Stopped"' 2>/dev/null || echo "Stopped")
  if [[ "$TS_STATUS" != "Running" ]]; then
    log "Starting Tailscale (interactive login)..."
    if [[ -n "${TAILSCALE_AUTH_KEY:-}" ]]; then
      tailscale up --authkey "$TAILSCALE_AUTH_KEY"
    else
      tailscale up
    fi
  fi
  TS_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
  ok "Tailscale IP: $TS_IP"
else
  warn "Tailscale setup skipped"
  TS_IP="0.0.0.0"
fi

# ═══════════════════════════════════════════════════════════════════════
# 3) UFW FIREWALL
# ═══════════════════════════════════════════════════════════════════════
log "Configuring firewall..."
if command -v ufw &>/dev/null; then
  ufw --force reset > /dev/null 2>&1
  ufw default deny incoming > /dev/null 2>&1
  ufw default allow outgoing > /dev/null 2>&1
  ufw allow ssh > /dev/null 2>&1
  ufw allow in on tailscale0 > /dev/null 2>&1
  ufw --force enable > /dev/null 2>&1
  ok "UFW: SSH + Tailscale only"
else
  apt-get install -y -qq ufw > /dev/null 2>&1
  ufw --force reset > /dev/null 2>&1
  ufw default deny incoming > /dev/null 2>&1
  ufw default allow outgoing > /dev/null 2>&1
  ufw allow ssh > /dev/null 2>&1
  ufw allow in on tailscale0 > /dev/null 2>&1
  ufw --force enable > /dev/null 2>&1
  ok "UFW installed and configured"
fi

# ═══════════════════════════════════════════════════════════════════════
# 4) CLONE HARNESS
# ═══════════════════════════════════════════════════════════════════════
log "Setting up harness..."
if [[ -d "$HARNESS_DIR/.git" ]]; then
  ok "Harness already cloned at $HARNESS_DIR, pulling latest..."
  git -C "$HARNESS_DIR" pull --ff-only origin main 2>/dev/null || true
else
  git clone "https://github.com/$GITHUB_HARNESS_REPO.git" "$HARNESS_DIR"
  ok "Harness cloned to $HARNESS_DIR"
fi

if [[ -f "$HARNESS_DIR/requirements.txt" ]]; then
  pip3 install -q -r "$HARNESS_DIR/requirements.txt" 2>/dev/null || true
  ok "Python dependencies installed"
fi

# ═══════════════════════════════════════════════════════════════════════
# 5) OPENCLAW DOCKER SETUP
# ═══════════════════════════════════════════════════════════════════════
if [[ "$SKIP_OPENCLAW" == "false" ]]; then
  log "Setting up OpenClaw container..."
  mkdir -p "$OPENCLAW_DIR/data"

  # docker-compose.yml from template
  if [[ ! -f "$OPENCLAW_DIR/docker-compose.yml" ]]; then
    TEMPLATE="$HARNESS_DIR/scripts/vps/docker-compose.template.yml"
    if [[ -f "$TEMPLATE" ]]; then
      sed \
        -e "s|__TAILSCALE_IP__|${TS_IP}|g" \
        -e "s|__HARNESS_DIR__|${HARNESS_DIR}|g" \
        "$TEMPLATE" > "$OPENCLAW_DIR/docker-compose.yml"
      ok "docker-compose.yml created from template"
    else
      warn "No docker-compose template found at $TEMPLATE -- skipping"
    fi
  else
    ok "docker-compose.yml already exists"
  fi

  # .env file
  if [[ ! -f "$OPENCLAW_DIR/.env" ]]; then
    if [[ -f "$HARNESS_DIR/scripts/vps/setup.env.example" ]]; then
      cp "$HARNESS_DIR/scripts/vps/setup.env.example" "$OPENCLAW_DIR/.env"
      warn "Created $OPENCLAW_DIR/.env from template -- EDIT IT with your API keys!"
    fi
  else
    ok ".env already exists"
  fi

  # Start container
  if docker ps --format '{{.Names}}' | grep -q "$OPENCLAW_CONTAINER"; then
    ok "OpenClaw container already running"
  else
    cd "$OPENCLAW_DIR"
    docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null
    ok "OpenClaw container started"
  fi

  # Wait for healthy
  log "Waiting for OpenClaw to be ready..."
  for i in $(seq 1 30); do
    if docker exec "$OPENCLAW_CONTAINER" openclaw --version &>/dev/null; then
      ok "OpenClaw is ready"
      break
    fi
    sleep 2
  done

  # Inject skills
  log "Injecting harness skills into OpenClaw..."
  SKILLS_SRC="$HARNESS_DIR/openclaw"
  SKILLS_DST="/data/.openclaw/skills"
  count=0
  for skill_file in "$SKILLS_SRC"/*.md; do
    [[ -f "$skill_file" ]] || continue
    fname=$(basename "$skill_file")
    docker cp "$skill_file" "$OPENCLAW_CONTAINER:$SKILLS_DST/$fname" 2>/dev/null || true
    count=$((count + 1))
  done
  # Also copy Python wrappers
  for py_file in "$SKILLS_SRC"/*.py; do
    [[ -f "$py_file" ]] || continue
    fname=$(basename "$py_file")
    docker cp "$py_file" "$OPENCLAW_CONTAINER:$SKILLS_DST/$fname" 2>/dev/null || true
    count=$((count + 1))
  done
  ok "Injected $count skill files"
else
  warn "OpenClaw setup skipped"
fi

# ═══════════════════════════════════════════════════════════════════════
# 6) DASHBOARD SETUP
# ═══════════════════════════════════════════════════════════════════════
log "Setting up dashboard..."
if [[ -d "$DASHBOARD_DIR/.git" ]]; then
  ok "Dashboard already cloned, pulling latest..."
  git -C "$DASHBOARD_DIR" pull --ff-only origin main 2>/dev/null || true
else
  git clone "https://github.com/$GITHUB_DASHBOARD_REPO.git" "$DASHBOARD_DIR"
  ok "Dashboard cloned to $DASHBOARD_DIR"
fi

# Determine workspace and openclaw dirs for the service
WORKSPACE_DIR="${OPENCLAW_DIR}/data/.openclaw/workspace"
OPENCLAW_AGENT_DIR="${OPENCLAW_DIR}/data/.openclaw"

# Create systemd service from template
SVCTEMPLATE="$HARNESS_DIR/scripts/vps/dashboard.service.template"
SVCFILE="/etc/systemd/system/agent-dashboard.service"
if [[ -f "$SVCTEMPLATE" ]]; then
  sed \
    -e "s|__DASHBOARD_DIR__|${DASHBOARD_DIR}|g" \
    -e "s|__DASHBOARD_PORT__|${DASHBOARD_PORT}|g" \
    -e "s|__DASHBOARD_TOKEN__|${DASHBOARD_TOKEN}|g" \
    -e "s|__WORKSPACE_DIR__|${WORKSPACE_DIR}|g" \
    -e "s|__OPENCLAW_DIR__|${OPENCLAW_AGENT_DIR}|g" \
    "$SVCTEMPLATE" > "$SVCFILE"
  systemctl daemon-reload
  systemctl enable agent-dashboard
  systemctl restart agent-dashboard
  ok "Dashboard service installed and started on port $DASHBOARD_PORT"
else
  warn "No service template found -- create $SVCFILE manually"
fi

# ═══════════════════════════════════════════════════════════════════════
# 7) MCP BRIDGES
# ═══════════════════════════════════════════════════════════════════════
log "Setting up MCP bridges config..."
MCP_FILE="$HARNESS_DIR/ai/supervisor/mcp_bridges.json"
if [[ ! -f "$MCP_FILE" ]]; then
  mkdir -p "$(dirname "$MCP_FILE")"
  cat > "$MCP_FILE" << 'MCPEOF'
{
  "bridges": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/opt/harness"],
      "port": 8101,
      "enabled": true,
      "note": "Read/write harness files"
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "port": 8102,
      "enabled": true,
      "note": "Persistent key-value memory"
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "port": 8103,
      "enabled": false,
      "note": "GitHub API (needs GITHUB_TOKEN env)"
    }
  }
}
MCPEOF
  ok "MCP bridges config created"
else
  ok "MCP bridges config already exists"
fi

# ═══════════════════════════════════════════════════════════════════════
# 8) HARNESS BOOTSTRAP
# ═══════════════════════════════════════════════════════════════════════
log "Running harness bootstrap..."
if [[ -f "$HARNESS_DIR/bootstrap.sh" ]]; then
  cd "$HARNESS_DIR"
  bash bootstrap.sh --force --skip-git 2>/dev/null || true
  ok "Harness bootstrap complete"
elif [[ -f "$HARNESS_DIR/scripts/vps/install_self_update.sh" ]]; then
  bash "$HARNESS_DIR/scripts/vps/install_self_update.sh" 2>/dev/null || true
  ok "Self-update pipeline installed"
else
  warn "No bootstrap script found -- manual setup needed"
fi

# ═══════════════════════════════════════════════════════════════════════
# 9) VERIFICATION
# ═══════════════════════════════════════════════════════════════════════
log "Running verification..."
ERRORS=0

# Check harness directory
if [[ -d "$HARNESS_DIR/ai" && -d "$HARNESS_DIR/scripts" && -d "$HARNESS_DIR/openclaw" ]]; then
  ok "Harness directory structure OK"
else
  warn "Harness directory incomplete"; ERRORS=$((ERRORS+1))
fi

# Check dashboard
if systemctl is-active agent-dashboard &>/dev/null; then
  ok "Dashboard service is running"
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${DASHBOARD_PORT}/api/auth/status" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" == "200" ]]; then
    ok "Dashboard API responding (HTTP $HTTP_CODE)"
  else
    warn "Dashboard API returned HTTP $HTTP_CODE"; ERRORS=$((ERRORS+1))
  fi
else
  warn "Dashboard service not running"; ERRORS=$((ERRORS+1))
fi

# Check OpenClaw
if [[ "$SKIP_OPENCLAW" == "false" ]]; then
  if docker ps --format '{{.Names}}' | grep -q "$OPENCLAW_CONTAINER"; then
    ok "OpenClaw container running"
    OC_VER=$(docker exec "$OPENCLAW_CONTAINER" openclaw --version 2>/dev/null || echo "unknown")
    ok "OpenClaw version: $OC_VER"
  else
    warn "OpenClaw container not running"; ERRORS=$((ERRORS+1))
  fi
fi

# Summary
echo ""
echo "═══════════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Harness:     $HARNESS_DIR"
echo "  Dashboard:   http://${TS_IP}:${DASHBOARD_PORT}"
echo "  Token:       $DASHBOARD_TOKEN"
echo ""
if [[ "$SKIP_OPENCLAW" == "false" ]]; then
  echo "  OpenClaw:    docker exec -it $OPENCLAW_CONTAINER openclaw"
  echo "  Skills:      $(ls "$HARNESS_DIR/openclaw/"*.md 2>/dev/null | wc -l) installed"
fi
echo ""
if [[ $ERRORS -gt 0 ]]; then
  echo "  ⚠ $ERRORS warnings -- check output above"
else
  echo "  ✓ All checks passed"
fi
echo ""
echo "  Next steps:"
echo "    1. Open http://${TS_IP}:${DASHBOARD_PORT} in your browser"
echo "    2. Register an account (first-time setup)"
echo "    3. Edit $OPENCLAW_DIR/.env with your API keys"
echo ""

#!/bin/bash
# Install vetting pipeline tools + MCPJungle on VPS (Linux).
# Idempotent: skips tools already installed.
# Usage: sudo bash scripts/vps/install_vetting_tools.sh

set -e

info()  { echo "[install] $*"; }
ok()    { echo "[install] OK: $*"; }
skip()  { echo "[install] SKIP: $* (already installed)"; }

# ---------- Trivy ----------
if command -v trivy &>/dev/null; then
  skip "trivy $(trivy --version 2>/dev/null | head -1)"
else
  info "Installing Trivy..."
  apt-get install -y wget apt-transport-https gnupg lsb-release 2>/dev/null || true
  wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor -o /usr/share/keyrings/trivy.gpg
  echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" \
    > /etc/apt/sources.list.d/trivy.list
  apt-get update -qq && apt-get install -y trivy
  ok "trivy $(trivy --version 2>/dev/null | head -1)"
fi

# ---------- Gitleaks ----------
if command -v gitleaks &>/dev/null; then
  skip "gitleaks $(gitleaks version 2>/dev/null)"
else
  info "Installing Gitleaks..."
  GITLEAKS_VER=$(curl -sL https://api.github.com/repos/gitleaks/gitleaks/releases/latest | grep tag_name | cut -d '"' -f4 | sed 's/v//')
  ARCH=$(uname -m); [[ "$ARCH" == "x86_64" ]] && ARCH="x64" || true
  curl -sL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VER}/gitleaks_${GITLEAKS_VER}_linux_${ARCH}.tar.gz" \
    | tar xz -C /usr/local/bin gitleaks
  chmod +x /usr/local/bin/gitleaks
  ok "gitleaks $(gitleaks version 2>/dev/null)"
fi

# ---------- Python tools (LLM Guard, pip-audit, Semgrep) ----------
PIP_CMD="pip3"
command -v pip3 &>/dev/null || PIP_CMD="pip"

install_pip_pkg() {
  local pkg="$1" cmd="${2:-$1}"
  if "$PIP_CMD" show "$pkg" &>/dev/null; then
    skip "$pkg (pip)"
  else
    info "Installing $pkg..."
    "$PIP_CMD" install --break-system-packages "$pkg" 2>/dev/null \
      || "$PIP_CMD" install "$pkg"
    ok "$pkg"
  fi
}

install_pip_pkg "llm-guard" "llm_guard"
install_pip_pkg "pip-audit" "pip-audit"
install_pip_pkg "semgrep" "semgrep"

# ---------- ClamAV (optional, best-effort) ----------
if command -v clamscan &>/dev/null; then
  skip "clamav"
else
  info "Installing ClamAV (optional)..."
  apt-get install -y clamav clamav-daemon 2>/dev/null && {
    freshclam 2>/dev/null || true
    ok "clamav"
  } || info "ClamAV install skipped (non-critical)"
fi

# ---------- Node.js / npm (ensure available) ----------
if ! command -v node &>/dev/null; then
  info "Installing Node.js 20.x..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
  ok "node $(node --version)"
fi

# ---------- openapi-mcp-generator ----------
if command -v openapi-mcp-generator &>/dev/null || npm list -g openapi-mcp-generator &>/dev/null 2>&1; then
  skip "openapi-mcp-generator"
else
  info "Installing openapi-mcp-generator..."
  npm install -g openapi-mcp-generator
  ok "openapi-mcp-generator"
fi

# ---------- MCPJungle (Docker) ----------
if ! command -v docker &>/dev/null; then
  info "Docker not found -- MCPJungle requires Docker."
  info "Install Docker first: https://docs.docker.com/engine/install/"
else
  HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
  COMPOSE_FILE="$HARNESS_DIR/deploy/docker-compose.mcpjungle.yml"
  if [[ -f "$COMPOSE_FILE" ]]; then
    if docker compose -f "$COMPOSE_FILE" ps --services 2>/dev/null | grep -q mcpjungle; then
      skip "MCPJungle (already running)"
    else
      info "Starting MCPJungle..."
      docker compose -f "$COMPOSE_FILE" up -d
      ok "MCPJungle started"
    fi
  else
    info "MCPJungle compose file not found at $COMPOSE_FILE"
    info "Pulling MCPJungle image for later use..."
    docker pull mcpjungle/mcpjungle:latest 2>/dev/null || true
    ok "MCPJungle image pulled"
  fi
fi

# ---------- Summary ----------
echo ""
echo "=== Vetting Pipeline Tools ==="
echo ""
printf "  %-25s %s\n" "trivy" "$(command -v trivy &>/dev/null && echo 'installed' || echo 'MISSING')"
printf "  %-25s %s\n" "gitleaks" "$(command -v gitleaks &>/dev/null && echo 'installed' || echo 'MISSING')"
printf "  %-25s %s\n" "llm-guard" "$($PIP_CMD show llm-guard 2>/dev/null | grep Version || echo 'MISSING')"
printf "  %-25s %s\n" "pip-audit" "$(command -v pip-audit &>/dev/null && echo 'installed' || echo 'MISSING')"
printf "  %-25s %s\n" "semgrep" "$(command -v semgrep &>/dev/null && echo 'installed' || echo 'MISSING')"
printf "  %-25s %s\n" "clamscan" "$(command -v clamscan &>/dev/null && echo 'installed' || echo 'optional/missing')"
printf "  %-25s %s\n" "openapi-mcp-generator" "$(command -v openapi-mcp-generator &>/dev/null && echo 'installed' || echo 'MISSING')"
printf "  %-25s %s\n" "MCPJungle (docker)" "$(docker compose -f "${HARNESS_DIR:-/opt/harness}/deploy/docker-compose.mcpjungle.yml" ps --services 2>/dev/null | grep -q mcpjungle && echo 'running' || echo 'not running')"
echo ""
echo "Done. Run 'python3 scripts/broker/tool_vetting.py vet --help' to test."

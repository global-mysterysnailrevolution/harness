#!/bin/bash
# Install OpenClaw skill CLIs inside the OpenClaw container.
# Enables: gemini (Gemini CLI), coding-agent (Codex), github (gh).
# GoG (gog) is optional — requires Go binary; add manually if needed.
#
# Run INSIDE the container (e.g. via docker exec):
#   docker exec -it openclaw-kx9d-openclaw-1 bash -c "$(cat scripts/vps/install_openclaw_skill_clis.sh)"
#
# Or from host with harness repo on VPS:
#   docker exec -i openclaw-kx9d-openclaw-1 bash -s < /opt/harness/scripts/vps/install_openclaw_skill_clis.sh
#
# Binaries go to /data/.local/bin (persisted via volume). custom-entrypoint.sh adds it to PATH.

set -e

INSTALL_DIR="/data/.local"
BIN_DIR="$INSTALL_DIR/bin"
mkdir -p "$BIN_DIR"

info()  { echo "[install-skill-clis] $*"; }
ok()    { echo "[install-skill-clis] OK: $*"; }
skip()  { echo "[install-skill-clis] SKIP: $* (already installed)"; }

# ---------- gh (GitHub CLI) ----------
if command -v gh &>/dev/null; then
  skip "gh $(gh --version 2>/dev/null | head -1)"
else
  info "Installing gh..."
  GH_VER="2.40.1"
  ARCH="linux_amd64"
  [[ "$(uname -m)" == "aarch64" ]] && ARCH="linux_arm64"
  curl -sL "https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_${ARCH}.tar.gz" \
    | tar xz -C /tmp
  mv "/tmp/gh_${GH_VER}_${ARCH}/bin/gh" "$BIN_DIR/"
  chmod +x "$BIN_DIR/gh"
  rm -rf "/tmp/gh_${GH_VER}_${ARCH}"
  ok "gh"
fi

# ---------- gemini (Google Gemini CLI) ----------
if command -v gemini &>/dev/null; then
  skip "gemini"
else
  info "Installing @google/gemini-cli..."
  npm config set prefix "$INSTALL_DIR" 2>/dev/null || true
  npm install -g @google/gemini-cli
  ok "gemini"
fi

# ---------- codex (OpenAI Codex / coding-agent) ----------
if command -v codex &>/dev/null; then
  skip "codex"
else
  info "Installing @openai/codex..."
  npm config set prefix "$INSTALL_DIR" 2>/dev/null || true
  npm install -g @openai/codex
  ok "codex"
fi

# ---------- Summary ----------
echo ""
echo "=== OpenClaw Skill CLIs ==="
echo ""
printf "  %-20s %s\n" "gh"    "$(command -v gh &>/dev/null && gh --version 2>/dev/null | head -1 || echo 'MISSING')"
printf "  %-20s %s\n" "gemini" "$(command -v gemini &>/dev/null && echo 'installed' || echo 'MISSING')"
printf "  %-20s %s\n" "codex"  "$(command -v codex &>/dev/null && echo 'installed' || echo 'MISSING')"
echo ""
echo "Binaries in: $BIN_DIR"
echo "Ensure custom-entrypoint.sh exports PATH with /data/.local/bin"
echo "Restart container to pick up: docker restart openclaw-kx9d-openclaw-1"
echo ""

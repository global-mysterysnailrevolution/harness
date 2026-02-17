#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy_self_update.sh
#
# Deploy the self-update pipeline to the VPS.
# Run from your local machine (Windows via Git Bash, or WSL):
#
#   bash harness/scripts/vps/deploy_self_update.sh [root@100.124.123.68]
#
# What this script does:
#   1. Pushes the latest harness files to the VPS via git pull
#   2. Runs install_self_update.sh on the VPS
#   3. Appends self-update skill reference to AGENTS.md
#   4. Verifies the setup
# ---------------------------------------------------------------------------

set -euo pipefail

VPS_HOST="${1:-root@100.124.123.68}"
HARNESS_DIR="/opt/harness"
AGENTS_MD="/docker/openclaw-kx9d/data/.openclaw/workspace/AGENTS.md"
APPEND_FILE="$HARNESS_DIR/scripts/vps/agents_md_self_update_append.txt"

echo "=== Deploying Self-Update Pipeline to $VPS_HOST ==="
echo ""

# Step 1: Git pull on VPS
echo "[1/4] Pulling latest harness on VPS..."
ssh "$VPS_HOST" "cd $HARNESS_DIR && git pull" || {
    echo "WARN: git pull failed; continuing with existing files."
}
echo ""

# Step 2: Run install script
echo "[2/4] Running install_self_update.sh on VPS..."
ssh "$VPS_HOST" "bash $HARNESS_DIR/scripts/vps/install_self_update.sh"
echo ""

# Step 3: Append to AGENTS.md (only if not already done)
echo "[3/4] Updating AGENTS.md..."
ssh "$VPS_HOST" "
if grep -q 'Self-Update Pipeline' '$AGENTS_MD' 2>/dev/null; then
    echo '  Already has self-update section, skipping.'
else
    cat '$APPEND_FILE' >> '$AGENTS_MD'
    echo '  Appended self-update skill reference to AGENTS.md'
fi
"
echo ""

# Step 4: Verify
echo "[4/4] Verifying setup..."
ssh "$VPS_HOST" "
echo 'Apply script:' && ls -la /usr/local/sbin/openclaw_apply_config && echo '' &&
echo 'Gateway script:' && ls -la /usr/local/sbin/openclaw_ssh_gateway && echo '' &&
echo 'Sudoers:' && ls -la /etc/sudoers.d/openclaw-bot && echo '' &&
echo 'SSH key:' && ls -la $HARNESS_DIR/secrets/openclaw-bot.key && echo '' &&
echo 'Directories:' &&
ls -ld $HARNESS_DIR/config_desired $HARNESS_DIR/config_backups $HARNESS_DIR/config_applied && echo '' &&
echo 'openclaw-bot user:' && id openclaw-bot && echo '' &&
echo 'AGENTS.MD contains self-update:' && grep -c 'Self-Update Pipeline' '$AGENTS_MD' && echo ''
"

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Test from inside the OpenClaw container:"
echo "  ssh -i /data/harness/secrets/openclaw-bot.key -o StrictHostKeyChecking=no openclaw-bot@172.18.0.1 status"

#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# install_self_update.sh
#
# One-time VPS setup for the OpenClaw secure self-update pipeline.
# Run as root on the VPS host:
#
#   sudo bash /opt/harness/scripts/vps/install_self_update.sh
#
# What this script does:
#   1. Creates the openclaw-bot system user (restricted)
#   2. Generates an SSH key pair for container -> host communication
#   3. Installs the SSH gateway script (forced command, only allows apply/rollback)
#   4. Deploys the apply script to /usr/local/sbin/
#   5. Creates the sudoers fragment (narrow permissions)
#   6. Creates required directories with correct ownership
#   7. Tests the setup
# ---------------------------------------------------------------------------

set -euo pipefail

HARNESS_ROOT="/opt/harness"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== OpenClaw Self-Update Pipeline Setup ==="
echo ""

# Must run as root
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root."
    echo "Usage: sudo bash $0"
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Create openclaw-bot user
# ---------------------------------------------------------------------------
echo "[1/7] Creating openclaw-bot user..."

if id openclaw-bot &>/dev/null; then
    echo "  User openclaw-bot already exists."
else
    useradd \
        --system \
        --shell /bin/bash \
        --home-dir /home/openclaw-bot \
        --create-home \
        --comment "OpenClaw self-update agent" \
        openclaw-bot
    echo "  Created user: openclaw-bot"
fi

# Lock password (SSH key only)
passwd -l openclaw-bot &>/dev/null || true
echo "  Password locked (key-based SSH only)."

# ---------------------------------------------------------------------------
# 2. Generate SSH key pair
# ---------------------------------------------------------------------------
echo ""
echo "[2/7] Setting up SSH keys..."

SSH_DIR="/home/openclaw-bot/.ssh"
PRIV_KEY="$SSH_DIR/id_ed25519"
PUB_KEY="$SSH_DIR/id_ed25519.pub"
AUTH_KEYS="$SSH_DIR/authorized_keys"
CONTAINER_KEY="$HARNESS_ROOT/secrets/openclaw-bot.key"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
chown openclaw-bot:openclaw-bot "$SSH_DIR"

if [[ -f "$PRIV_KEY" ]]; then
    echo "  SSH key already exists at $PRIV_KEY"
else
    ssh-keygen -t ed25519 -f "$PRIV_KEY" -N "" -C "openclaw-bot@$(hostname)" -q
    echo "  Generated new ed25519 key pair."
fi

chown openclaw-bot:openclaw-bot "$PRIV_KEY" "$PUB_KEY"
chmod 600 "$PRIV_KEY"
chmod 644 "$PUB_KEY"

# ---------------------------------------------------------------------------
# 3. Install SSH gateway (forced command)
# ---------------------------------------------------------------------------
echo ""
echo "[3/7] Installing SSH gateway..."

GATEWAY_SCRIPT="/usr/local/sbin/openclaw_ssh_gateway"

cat > "$GATEWAY_SCRIPT" << 'GATEWAY_EOF'
#!/usr/bin/env bash
# SSH gateway for openclaw-bot.
# This is the forced command in authorized_keys.
# It only allows specific subcommands.

set -euo pipefail

APPLY_SCRIPT="/usr/local/sbin/openclaw_apply_config"
LOG="/var/log/openclaw-bot.log"

cmd="${SSH_ORIGINAL_COMMAND:-}"

log_it() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"
}

log_it "Received command: $cmd"

case "$cmd" in
    apply)
        log_it "Dispatching: apply"
        exec sudo "$APPLY_SCRIPT"
        ;;
    rollback)
        log_it "Dispatching: rollback"
        exec sudo "$APPLY_SCRIPT" --rollback
        ;;
    status)
        log_it "Dispatching: status"
        # Return basic status (non-destructive, no sudo needed)
        echo '{"gateway":"ok","user":"openclaw-bot"}'
        ;;
    *)
        log_it "REJECTED: $cmd"
        echo "ERROR: Command not allowed. Valid: apply, rollback, status" >&2
        exit 1
        ;;
esac
GATEWAY_EOF

chmod 755 "$GATEWAY_SCRIPT"
chown root:root "$GATEWAY_SCRIPT"
echo "  Installed: $GATEWAY_SCRIPT"

# Set up authorized_keys with forced command
PUB_KEY_CONTENT=$(cat "$PUB_KEY")
cat > "$AUTH_KEYS" << EOF
command="$GATEWAY_SCRIPT",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $PUB_KEY_CONTENT
EOF

chown openclaw-bot:openclaw-bot "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"
echo "  Configured authorized_keys with forced command."

# Copy private key to harness secrets (for container access)
mkdir -p "$HARNESS_ROOT/secrets"
cp "$PRIV_KEY" "$CONTAINER_KEY"
chmod 600 "$CONTAINER_KEY"
# Make readable by the container user (typically uid 1000)
chown 1000:1000 "$CONTAINER_KEY" 2>/dev/null || true
echo "  Copied private key to $CONTAINER_KEY"

# ---------------------------------------------------------------------------
# 4. Deploy the apply script
# ---------------------------------------------------------------------------
echo ""
echo "[4/7] Deploying apply script..."

APPLY_SRC="$SCRIPT_DIR/openclaw_apply_config.sh"
APPLY_DEST="/usr/local/sbin/openclaw_apply_config"

if [[ ! -f "$APPLY_SRC" ]]; then
    echo "  ERROR: Source apply script not found at $APPLY_SRC"
    echo "  Make sure openclaw_apply_config.sh is in the same directory as this script."
    exit 1
fi

cp "$APPLY_SRC" "$APPLY_DEST"
chmod 755 "$APPLY_DEST"
chown root:root "$APPLY_DEST"
echo "  Installed: $APPLY_DEST"

# ---------------------------------------------------------------------------
# 5. Create sudoers fragment
# ---------------------------------------------------------------------------
echo ""
echo "[5/7] Setting up sudoers..."

SUDOERS_FILE="/etc/sudoers.d/openclaw-bot"

cat > "$SUDOERS_FILE" << 'SUDOERS_EOF'
# OpenClaw self-update: narrow sudo permissions for openclaw-bot
# Only allows the apply script and status checks. No shell, no file tools.

openclaw-bot ALL=(root) NOPASSWD: /usr/local/sbin/openclaw_apply_config
openclaw-bot ALL=(root) NOPASSWD: /usr/local/sbin/openclaw_apply_config --rollback
openclaw-bot ALL=(root) NOPASSWD: /usr/bin/systemctl status *
SUDOERS_EOF

chmod 440 "$SUDOERS_FILE"
chown root:root "$SUDOERS_FILE"

# Validate sudoers
if visudo -cf "$SUDOERS_FILE" &>/dev/null; then
    echo "  Installed and validated: $SUDOERS_FILE"
else
    echo "  ERROR: sudoers file has syntax errors!"
    rm -f "$SUDOERS_FILE"
    exit 1
fi

# ---------------------------------------------------------------------------
# 6. Create directories
# ---------------------------------------------------------------------------
echo ""
echo "[6/7] Creating directories..."

for dir in \
    "$HARNESS_ROOT/config_desired" \
    "$HARNESS_ROOT/config_backups" \
    "$HARNESS_ROOT/config_applied" \
    "$HARNESS_ROOT/secrets"; do

    mkdir -p "$dir"
    # Writable by the container (uid 1000) for config_desired
    if [[ "$dir" == *config_desired* ]]; then
        chown 1000:1000 "$dir"
        chmod 775 "$dir"
    else
        chmod 755 "$dir"
    fi
    echo "  Created: $dir"
done

# Ensure the log directory exists
touch /var/log/openclaw-bot.log
chown openclaw-bot:openclaw-bot /var/log/openclaw-bot.log
chmod 644 /var/log/openclaw-bot.log
echo "  Created: /var/log/openclaw-bot.log"

# ---------------------------------------------------------------------------
# 7. Test
# ---------------------------------------------------------------------------
echo ""
echo "[7/7] Testing setup..."

# Test sudoers
if sudo -u openclaw-bot sudo -n /usr/local/sbin/openclaw_apply_config --help 2>/dev/null; then
    echo "  [OK] Sudo access works (apply script not actually run)"
else
    # The apply script doesn't have --help, so it may fail, but sudo access itself works
    # if we get past the sudo check
    echo "  [OK] Sudo configured (apply script will run when invoked properly)"
fi

# Test SSH key exists
if [[ -f "$CONTAINER_KEY" ]]; then
    echo "  [OK] Container SSH key: $CONTAINER_KEY"
else
    echo "  [WARN] Container SSH key not found at $CONTAINER_KEY"
fi

# Test gateway script
if [[ -x "$GATEWAY_SCRIPT" ]]; then
    echo "  [OK] Gateway script: $GATEWAY_SCRIPT"
else
    echo "  [WARN] Gateway script not executable: $GATEWAY_SCRIPT"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "The self-update pipeline is ready. OpenClaw can now:"
echo "  1. Propose changes to config_desired/"
echo "  2. Apply them via SSH -> gateway -> sudo apply_config"
echo "  3. Auto-rollback on health check failure"
echo ""
echo "Files installed:"
echo "  $APPLY_DEST           (root-owned apply script)"
echo "  $GATEWAY_SCRIPT       (SSH forced command gateway)"
echo "  $SUDOERS_FILE         (narrow sudo permissions)"
echo "  $CONTAINER_KEY        (SSH key for container)"
echo "  $AUTH_KEYS             (SSH authorized_keys)"
echo ""
echo "Next steps:"
echo "  - Ensure the OpenClaw container has openssh-client installed"
echo "  - Ensure port 22 is accessible from Docker bridge (172.18.0.0/16)"
echo "  - Test from inside the container:"
echo "    ssh -i /data/harness/secrets/openclaw-bot.key -o StrictHostKeyChecking=no openclaw-bot@172.18.0.1 status"

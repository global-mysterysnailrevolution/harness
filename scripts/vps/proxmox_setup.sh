#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-time Proxmox host setup for OpenClaw integration.
# Run this on the Proxmox host as root (or via SSH from local machine).
#
# What it does:
#   1. Creates a dedicated 'openclaw' PVE user (no shell access)
#   2. Creates an API token for that user
#   3. Sets ACLs: VM management only, on path /vms (all VMs)
#   4. Prints credentials for harness/secrets/proxmox.env
#
# Usage:
#   bash proxmox_setup.sh
# ---------------------------------------------------------------------------

set -euo pipefail

PVE_USER="openclaw@pam"
TOKEN_NAME="openclaw-token"
ROLE_NAME="OpenClawVMAdmin"

echo "=== Proxmox Setup for OpenClaw ==="
echo ""

# --- Step 1: Create PVE user (PAM realm) ---
if pveum user list 2>/dev/null | grep -q "$PVE_USER"; then
    echo "[OK] User $PVE_USER already exists."
else
    echo "[+] Creating PAM user 'openclaw' ..."
    # Create system user with no login shell
    useradd -r -s /usr/sbin/nologin openclaw 2>/dev/null || true
    pveum user add "$PVE_USER" -comment "OpenClaw VM management agent"
    echo "[OK] User $PVE_USER created."
fi

# --- Step 2: Create custom role with VM-only privileges ---
if pveum role list 2>/dev/null | grep -q "$ROLE_NAME"; then
    echo "[OK] Role $ROLE_NAME already exists."
else
    echo "[+] Creating role '$ROLE_NAME' ..."
    pveum role add "$ROLE_NAME" -privs \
        "VM.Allocate,VM.Audit,VM.Clone,VM.Config.CDROM,VM.Config.CPU,VM.Config.Cloudinit,VM.Config.Disk,VM.Config.HWType,VM.Config.Memory,VM.Config.Network,VM.Config.Options,VM.Console,VM.Migrate,VM.Monitor,VM.PowerMgmt,VM.Snapshot,VM.Snapshot.Rollback,Datastore.AllocateSpace,Datastore.Audit,SDN.Use"
    echo "[OK] Role $ROLE_NAME created."
fi

# --- Step 3: Assign role to user on /vms path ---
echo "[+] Setting ACL: $PVE_USER -> $ROLE_NAME on /"
pveum aclmod / -user "$PVE_USER" -role "$ROLE_NAME"
echo "[OK] ACL applied."

# --- Step 4: Create API token ---
echo "[+] Creating API token '$TOKEN_NAME' ..."
# Delete existing token if present (idempotent)
pveum user token remove "$PVE_USER" "$TOKEN_NAME" 2>/dev/null || true

TOKEN_OUTPUT=$(pveum user token add "$PVE_USER" "$TOKEN_NAME" -privsep 0 2>&1)
TOKEN_SECRET=$(echo "$TOKEN_OUTPUT" | grep -oP 'value.*?(\S+)$' | awk '{print $NF}')

if [ -z "$TOKEN_SECRET" ]; then
    echo "[!] Could not parse token. Full output:"
    echo "$TOKEN_OUTPUT"
    echo ""
    echo "Look for the 'value' field above and paste it into proxmox.env manually."
else
    echo "[OK] Token created."
fi

# --- Step 5: Print credentials ---
PROXMOX_HOST=$(hostname -I | awk '{print $1}')
echo ""
echo "========================================"
echo "  Copy the following into:"
echo "  harness/secrets/proxmox.env"
echo "========================================"
echo ""
echo "PROXMOX_HOST=$PROXMOX_HOST"
echo "PROXMOX_PORT=8006"
echo "PROXMOX_TOKEN_ID=${PVE_USER}!${TOKEN_NAME}"
echo "PROXMOX_TOKEN_SECRET=${TOKEN_SECRET:-PASTE_TOKEN_HERE}"
echo "PROXMOX_NODE=$(hostname -s)"
echo "PROXMOX_VERIFY_SSL=false"
echo ""
echo "========================================"
echo ""
echo "Done. The 'openclaw' user can manage VMs but has no shell access"
echo "and no cluster/node admin privileges."

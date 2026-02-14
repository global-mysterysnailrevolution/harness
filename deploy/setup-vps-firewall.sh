#!/bin/bash
# VPS Firewall Hardening Script
# Sets up 3-layer defense: Docker port binding, DOCKER-USER iptables, UFW
#
# Run on VPS as root:
#   bash /opt/harness/deploy/setup-vps-firewall.sh
#
# Idempotent: safe to re-run.

set -euo pipefail

TAILSCALE_CIDR="100.64.0.0/10"
DOCKER_NETS="172.16.0.0/12"
LOCALHOST="127.0.0.0/8"
OPENCLAW_PORTS=(18789 50606)

echo "=== VPS Firewall Hardening ==="

# ---- DOCKER-USER iptables rules ----
echo ""
echo "--- Layer 2: DOCKER-USER iptables ---"

iptables -F DOCKER-USER 2>/dev/null || true

# Established connections
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

# Allow Tailscale to OpenClaw ports
for port in "${OPENCLAW_PORTS[@]}"; do
    iptables -A DOCKER-USER -p tcp --dport "$port" -s "$TAILSCALE_CIDR" -j RETURN
    echo "  ALLOW tcp:$port from $TAILSCALE_CIDR"
done

# Allow Docker internal + localhost
iptables -A DOCKER-USER -s "$DOCKER_NETS" -j RETURN
iptables -A DOCKER-USER -s "$LOCALHOST" -j RETURN

# Drop everything else to OpenClaw ports
for port in "${OPENCLAW_PORTS[@]}"; do
    iptables -A DOCKER-USER -p tcp --dport "$port" -j DROP
    echo "  DROP tcp:$port from all others"
done

# Pass all other traffic
iptables -A DOCKER-USER -j RETURN

# ---- UFW rules ----
echo ""
echo "--- Layer 3: UFW ---"

# Remove any existing "allow from anywhere" rules for our ports
for port in "${OPENCLAW_PORTS[@]}"; do
    ufw delete allow "$port/tcp" 2>/dev/null || true
done

# Add Tailscale-only rules (idempotent: ufw skips duplicates)
ufw allow in on tailscale0 to any port 22 proto tcp comment 'SSH (Tailscale only)' 2>/dev/null || true
ufw allow in on tailscale0 to any port 18789 proto tcp comment 'OpenClaw Gateway (Tailscale only)' 2>/dev/null || true
ufw allow in on tailscale0 to any port 50606 proto tcp comment 'Hostinger panel (Tailscale only)' 2>/dev/null || true

echo "  UFW rules applied"

# ---- Persist iptables ----
echo ""
echo "--- Persisting iptables ---"
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
netfilter-persistent save 2>/dev/null || true
echo "  Saved to /etc/iptables/rules.v4"

# ---- Verify ----
echo ""
echo "=== Verification ==="
echo ""
echo "Port bindings (should show Tailscale IP, not 0.0.0.0):"
ss -tlnp | grep -E '18789|50606' || echo "  (no Docker ports listening — is container running?)"
echo ""
echo "DOCKER-USER chain:"
iptables -L DOCKER-USER -n --line-numbers
echo ""
echo "UFW relevant rules:"
ufw status | grep -E '18789|50606|22'
echo ""
echo "=== Done ==="

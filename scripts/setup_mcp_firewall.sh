#!/bin/bash
# UFW firewall rules for MCP bridges
# Only allow Docker bridge (172.17.0.0/16) and localhost to reach ports 8101-8104
# Run as root: sudo ./setup_mcp_firewall.sh

set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0"
  exit 1
fi

# Allow from Docker bridges to MCP ports (172.17 = default, 172.18 = openclaw compose)
ufw allow from 172.17.0.0/16 to any port 8101 proto tcp comment 'MCP filesystem'
ufw allow from 172.17.0.0/16 to any port 8102 proto tcp comment 'MCP everything'
ufw allow from 172.17.0.0/16 to any port 8103 proto tcp comment 'MCP github'
ufw allow from 172.17.0.0/16 to any port 8104 proto tcp comment 'MCP memory'
ufw allow from 172.18.0.0/16 to any port 8101 proto tcp comment 'MCP openclaw net'
ufw allow from 172.18.0.0/16 to any port 8102 proto tcp
ufw allow from 172.18.0.0/16 to any port 8103 proto tcp
ufw allow from 172.18.0.0/16 to any port 8104 proto tcp

# Allow from localhost
ufw allow from 127.0.0.1 to any port 8101 proto tcp comment 'MCP localhost'
ufw allow from 127.0.0.1 to any port 8102 proto tcp
ufw allow from 127.0.0.1 to any port 8103 proto tcp
ufw allow from 127.0.0.1 to any port 8104 proto tcp

# Reload
ufw reload 2>/dev/null || true

echo "Firewall rules added. MCP ports 8101-8104 only allow Docker bridge and localhost."
echo "Run 'ufw status' to verify."

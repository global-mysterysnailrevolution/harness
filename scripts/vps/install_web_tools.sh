#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Install web browsing fast-lane tools into the OpenClaw container.
#
# Run inside the container:
#   docker exec -it <container> bash /data/harness/scripts/vps/install_web_tools.sh
#
# Or from the host via SSH:
#   ssh root@<vps> "docker exec openclaw bash /data/harness/scripts/vps/install_web_tools.sh"
# ---------------------------------------------------------------------------

set -euo pipefail

echo "=== Installing Web Fast-Lane Tools ==="
echo ""

# --- 1. Install mcp-server-fetch (Python, official MCP fetch server) ---
echo "[+] Installing mcp-server-fetch ..."
pip3 install --quiet --user mcp-server-fetch 2>/dev/null \
  || pip3 install --quiet mcp-server-fetch \
  || pip install --quiet mcp-server-fetch
echo "[OK] mcp-server-fetch installed."

# Verify it's importable
python3 -c "import mcp_server_fetch; print(f'    version: {getattr(mcp_server_fetch, \"__version__\", \"ok\")}')" 2>/dev/null \
  || echo "    (installed but version check skipped)"

# --- 2. Ensure npx is available (for brave-search, runs on demand) ---
if command -v npx &>/dev/null; then
    echo "[OK] npx available (brave-search will auto-install via npx on first use)."
else
    echo "[!] npx not found. brave-search MCP server needs Node.js + npx."
    echo "    Install Node.js or add /data/.local/bin to PATH."
fi

# --- 3. Create adapters directory if needed ---
ADAPTERS_DIR="/data/harness/adapters"
mkdir -p "$ADAPTERS_DIR"
echo "[OK] Adapters directory ready: $ADAPTERS_DIR"

# --- 4. Verify tools directory ---
TOOLS_DIR="/data/harness/scripts/tools"
if [ -f "$TOOLS_DIR/web_adapter_tool.py" ]; then
    echo "[OK] web_adapter_tool.py found in $TOOLS_DIR"
else
    echo "[!] web_adapter_tool.py not found in $TOOLS_DIR"
    echo "    Make sure harness is mounted at /data/harness"
fi

if [ -f "$TOOLS_DIR/proxmox_tool.py" ]; then
    echo "[OK] proxmox_tool.py found in $TOOLS_DIR"
else
    echo "[!] proxmox_tool.py not found (expected if Proxmox not configured yet)"
fi

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. To enable brave-search, get a free API key from https://brave.com/search/api/"
echo "     and set BRAVE_API_KEY in /data/harness/secrets/brave.env"
echo "  2. Fetch tool is ready to use immediately (no API key needed)."
echo "  3. Create site adapters in $ADAPTERS_DIR as needed."

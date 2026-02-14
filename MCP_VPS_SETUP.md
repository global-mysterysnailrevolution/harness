# Start MCP Servers on VPS

Run MCP servers on your VPS so OpenClaw (in Docker) can use filesystem, memory, GitHub, and other MCP tools.

**Config-driven:** When `ai/supervisor/mcp_bridges.json` exists, add new MCP servers by editing that file. The config watcher (cron every 5 min) starts any new bridges without restarting existing ones.

## Quick Start

### 1. SSH to VPS

```bash
ssh root@your-vps-ip
```

### 2. Ensure harness is at /opt/harness

```bash
# If not yet cloned
git clone https://github.com/global-mysterysnailrevolution/harness.git /opt/harness
cd /opt/harness
```

### 3. Install Node.js (if needed)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
apt install -y nodejs
```

### 4. Run MCP servers (foreground)

```bash
cd /opt/harness/scripts
chmod +x run_mcp_servers.sh
MCP_BIND=0.0.0.0 ./run_mcp_servers.sh
```

**Important:** `MCP_BIND=0.0.0.0` lets OpenClaw (in Docker) reach the bridges. The Docker bridge uses 172.18.x, so OpenClaw config should use `http://172.18.0.1:8101/mcp` etc.

### 5. Run as systemd service (recommended)

```bash
cp /opt/harness/deploy/harness-mcp-servers.service /etc/systemd/system/
# Add to /opt/harness/.env:
#   MCP_BIND=0.0.0.0
systemctl daemon-reload
systemctl enable harness-mcp-servers
systemctl start harness-mcp-servers
systemctl status harness-mcp-servers
```

### 6. Configure OpenClaw

**Important**: Do NOT add `mcp-integration` to `plugins.entries` — this is an invalid plugin ID that will crash the gateway. MCP servers are accessed via skills, not plugins.

The OpenClaw agent accesses MCP tools through its built-in memory, web search/fetch, and exec capabilities. The `memory-core` plugin (bundled, loads by default) provides file-backed memory tools. External MCP servers on ports 8101-8104 are available to the agent via HTTP from inside the Docker container at `http://172.18.0.1:<port>/mcp`.

To restart OpenClaw after config changes:

```bash
# Validate config first
python3 /opt/harness/scripts/openclaw_setup/config_guard.py validate \
  /docker/openclaw-kx9d/data/.openclaw/openclaw.json

# Then restart
docker restart openclaw-kx9d-openclaw-1
```

## Adding New MCP Servers (Config-Driven)

Edit `ai/supervisor/mcp_bridges.json`:

```json
{
  "bridges": {
    "my-new-server": {
      "port": 8105,
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-my-server", "${HARNESS_DIR}/ai"],
      "enabled": true
    }
  }
}
```

The config watcher (cron every 5 min) will start it. No restart of existing bridges.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_BIND` | 127.0.0.1 | Bind address. Use `0.0.0.0` for Docker access. |
| `MCP_BEARER_TOKEN` | (none) | Optional Bearer auth. Docker bridge IPs exempt if `MCP_ALLOW_LOCAL=1`. |
| `MCP_HTTPS_KEY` | (none) | Path to TLS key (enables HTTPS). |
| `MCP_HTTPS_CERT` | (none) | Path to TLS cert. |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | (none) | Enables GitHub MCP server on port 8103. |

## Ports

| Port | Server |
|------|--------|
| 8101 | Filesystem (restricted to `ai/` only) |
| 8102 | Everything (fetch, tools, resources) |
| 8103 | GitHub (requires token) |
| 8104 | Memory |

## Firewall (optional)

If using UFW, allow Docker bridge:

```bash
ufw allow from 172.17.0.0/16 to any port 8101 proto tcp
ufw allow from 172.17.0.0/16 to any port 8102 proto tcp
ufw allow from 172.17.0.0/16 to any port 8103 proto tcp
ufw allow from 172.17.0.0/16 to any port 8104 proto tcp
ufw allow from 172.18.0.0/16 to any port 8101 proto tcp
ufw allow from 172.18.0.0/16 to any port 8102 proto tcp
ufw allow from 172.18.0.0/16 to any port 8103 proto tcp
ufw allow from 172.18.0.0/16 to any port 8104 proto tcp
ufw reload
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| OpenClaw can't connect | Ensure `MCP_BIND=0.0.0.0` and OpenClaw uses `172.18.0.1` (host from Docker's view). |
| Port already in use | `kill $(cat /tmp/mcp-bridges/mcp-*.pid)` then restart. |
| GitHub not working | Set `GITHUB_PERSONAL_ACCESS_TOKEN` in `/opt/harness/.env`. |
| `plugin not found` crash | Never add `mcp-integration` to plugins.entries. Use `openclaw plugins list` to see valid IDs. |

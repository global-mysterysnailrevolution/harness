# VPS Deployment Guide (Hostinger + OpenClaw + Tailscale)

Complete guide for deploying and maintaining the harness on a Hostinger VPS running OpenClaw in Docker, secured via Tailscale.

## Architecture Overview

```
Windows PC (Cursor IDE)
  |
  | Tailscale VPN (100.x.x.x)
  |
  v
Hostinger VPS (Linux)
  |
  +-- Docker: OpenClaw container (gateway + WhatsApp + agent)
  |     - Port 63362 (internal) -> 18789 (Tailscale-only)
  |     - Port 50606 (Hostinger panel, Tailscale-only)
  |     - Mounts: ./data:/data, ./data/linuxbrew:/home/linuxbrew
  |
  +-- Tailscale: 100.124.123.68
  +-- UFW firewall + DOCKER-USER iptables rules
  +-- Harness repo: /opt/harness (git)

Windows PC
  +-- openclaw node host (connects to VPS gateway, runs browser relay)
  +-- Chrome extension (connects to local relay on :18792)
  +-- Cursor IDE + harness repo
```

## Prerequisites

| Component | Where | Notes |
|-----------|-------|-------|
| Tailscale | Both VPS + PC | Private networking between machines |
| Docker | VPS | Runs OpenClaw container |
| Git | Both | Harness repo sync |
| Node.js 20+ | VPS (in container) | Comes with OpenClaw image |
| Python 3.11+ | VPS (host + container) | For harness scripts |
| OpenClaw CLI | Windows PC | For node host + browser relay |

## VPS Setup

### 1. Docker Compose

The OpenClaw container runs from `/docker/openclaw-kx9d/`:

```yaml
# /docker/openclaw-kx9d/docker-compose.yml
services:
  openclaw:
    image: ghcr.io/hostinger/hvps-openclaw:latest
    init: true
    entrypoint: ["/data/custom-entrypoint.sh"]
    ports:
      # CRITICAL: Bind to Tailscale IP only, never 0.0.0.0
      - "100.124.123.68:${PORT}:${PORT}"
      - "100.124.123.68:18789:63362"
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./data:/data
      - ./data/linuxbrew:/home/linuxbrew
```

**Port binding**: Both ports are bound to the Tailscale IP (`100.124.123.68`), not `0.0.0.0`. This means they are only accessible via the Tailscale VPN, not from the public internet. See [Security Hardening](#security-hardening) for details.

**Custom entrypoint**: The `custom-entrypoint.sh` wrapper creates a `python` -> `python3` symlink (Debian images only have `python3`) and then calls the original `/entrypoint.sh`. Stored in the mounted data volume so it persists across image updates:

```bash
#!/bin/sh
# /docker/openclaw-kx9d/data/custom-entrypoint.sh
ln -sf /usr/bin/python3 /usr/bin/python 2>/dev/null || true
exec /entrypoint.sh "$@"
```

### 2. Environment Variables

```bash
# /docker/openclaw-kx9d/.env
PORT=50606
TZ=America/Phoenix
OPENCLAW_GATEWAY_TOKEN=<your-token>
OPENAI_API_KEY=<your-key>
WHATSAPP_NUMBER=<your-number>
NODE_TLS_REJECT_UNAUTHORIZED=0
```

### 3. OpenClaw Configuration

The main config is at `/docker/openclaw-kx9d/data/.openclaw/openclaw.json`. Key sections:

#### Models

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "ChatGPT 5.2",
        "fallbacks": ["Claude Sonnet 4.5", "Gemini 3 Flash Preview", "Grok 4.1 Fast Reasoning"]
      },
      "models": {
        "openai/gpt-5.2": { "alias": "ChatGPT 5.2" },
        "anthropic/claude-sonnet-4-5": { "alias": "Claude Sonnet 4.5" },
        "google/gemini-3-flash-preview": { "alias": "Gemini 3 Flash Preview" },
        "xai/grok-4-1-fast-reasoning": { "alias": "Grok 4.1 Fast Reasoning" }
      }
    }
  }
}
```

**Important**: Do NOT add `params` blocks (e.g. `temperature`, `maxTokens`) to model configs. GPT-5.2 does not support `temperature` and the API will return `400 unsupported parameter`.

#### Memory & Compaction

```json
{
  "agents": {
    "defaults": {
      "compaction": {
        "mode": "safeguard",
        "memoryFlush": {
          "enabled": true,
          "softThresholdTokens": 4000,
          "systemPrompt": "Session nearing compaction. Store durable memories now. Never store secrets...",
          "prompt": "Write any lasting notes to memory/YYYY-MM-DD.md or MEMORY.md..."
        }
      },
      "memorySearch": {
        "experimental": { "sessionMemory": true },
        "sources": ["memory", "sessions"],
        "sync": { "sessions": { "deltaBytes": 100000, "deltaMessages": 50 } },
        "query": { "hybrid": { "enabled": true, "vectorWeight": 0.7, "textWeight": 0.3, "candidateMultiplier": 4 } }
      },
      "contextPruning": { "mode": "cache-ttl", "ttl": "1h" }
    }
  }
}
```

#### Concurrency

```json
{
  "agents": {
    "defaults": {
      "maxConcurrent": 4,
      "subagents": { "maxConcurrent": 8 }
    }
  }
}
```

#### Tools

```json
{
  "tools": {
    "profile": "coding",
    "deny": ["group:automation"],
    "web": {
      "search": { "enabled": true, "maxResults": 5 },
      "fetch": { "enabled": true, "maxCharsCap": 50000 }
    }
  }
}
```

**Note**: The `coding` profile references `group:memory` in its built-in allowlist. The `memory-core` plugin is loaded by default as a bundled extension and provides the memory tools. The `group:memory` warning in logs is cosmetic and does not affect functionality.

#### Hooks

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "boot-md": { "enabled": true },
        "command-logger": { "enabled": true },
        "session-memory": { "enabled": true }
      }
    }
  }
}
```

#### Gateway

```json
{
  "gateway": {
    "mode": "local",
    "bind": "lan",
    "port": 18789,
    "nodes": { "browser": { "mode": "auto" } },
    "controlUi": { "allowInsecureAuth": true },
    "auth": { "mode": "token", "token": "<gateway-token>" },
    "remote": { "token": "<gateway-token>" }
  }
}
```

#### Channels

```json
{
  "channels": {
    "whatsapp": {
      "allowFrom": ["<your-number>"],
      "dmPolicy": "allowlist",
      "groupPolicy": "disabled",
      "selfChatMode": true,
      "dmHistoryLimit": 25,
      "configWrites": false,
      "sendReadReceipts": false
    }
  }
}
```

#### Plugins

```json
{
  "plugins": {
    "entries": {
      "whatsapp": { "enabled": true },
      "discord": { "enabled": true },
      "telegram": { "enabled": true },
      "slack": { "enabled": true },
      "googlechat": { "enabled": true },
      "nostr": { "enabled": true }
    }
  }
}
```

**Warning**: Never add unknown plugin IDs to `plugins.entries`. An invalid ID (e.g. `mcp-integration`) will crash the gateway and kill WhatsApp. Use `docker exec openclaw-kx9d-openclaw-1 openclaw plugins list` to see valid IDs.

### 4. Workspace Files

The OpenClaw workspace at `/docker/openclaw-kx9d/data/.openclaw/workspace/` contains:

| File | Purpose |
|------|---------|
| `TOOLS.md` | Agent reads this to know available tools, Python environment, etc. |
| `HEARTBEAT.md` | Periodic checks the agent performs (pending requests, email, etc.) |
| `AGENTS.md` | Agent instructions, personality, Learning Loop |
| `MEMORY.md` | Curated long-term rules |
| `memory/YYYY-MM-DD.md` | Daily memory files from compaction flushes |

### 5. Harness Config Hardening

The harness provides automated config management:

```bash
# Apply golden template to VPS config (with backup + validation + health check)
python3 scripts/openclaw_setup/apply_openclaw_hardening.py \
  --config-path /docker/openclaw-kx9d/data/.openclaw/openclaw.json

# Validate config without applying
python3 scripts/openclaw_setup/apply_openclaw_hardening.py --dry-run

# Validate a config file directly
python3 scripts/openclaw_setup/config_guard.py validate /path/to/openclaw.json

# Health check running container
python3 scripts/openclaw_setup/config_guard.py health-check

# Rollback to last good config
python3 scripts/openclaw_setup/config_guard.py rollback /path/to/openclaw.json
```

**ConfigGuard** (`scripts/openclaw_setup/config_guard.py`):
- Validates plugin IDs against known set (prevents crash-causing entries)
- Validates enum values (gateway.mode, compaction.mode, tools.profile, etc.)
- Creates timestamped backups before every write
- Health-checks the Docker container after config changes
- Auto-rolls back if the container crashes

**Golden template** (`scripts/openclaw_setup/openclaw_vps_config.json`):
- Defines optimal default settings for VPS deployment
- Deep-merged into existing config (preserves channels, auth, identity, meta, wizard)
- Does NOT include model `params` blocks (temperature, maxTokens)

## Security Hardening

### Docker Port Isolation (3-Layer Defense)

The VPS uses three independent layers to prevent public exposure of the OpenClaw gateway:

#### Layer 1: Docker Port Binding

Docker ports are bound exclusively to the Tailscale interface:

```yaml
ports:
  - "100.124.123.68:${PORT}:${PORT}"     # Hostinger panel
  - "100.124.123.68:18789:63362"          # Gateway WebSocket
```

This means `docker-proxy` only listens on `100.124.123.68`, not `0.0.0.0`.

#### Layer 2: DOCKER-USER iptables Chain

Docker's own iptables rules bypass UFW entirely. The `DOCKER-USER` chain is the official place for custom firewall rules that Docker respects:

```
Chain DOCKER-USER:
1  RETURN   -- established/related connections
2  RETURN   tcp  100.64.0.0/10 -> :18789    (Tailscale)
3  RETURN   tcp  100.64.0.0/10 -> :50606    (Tailscale)
4  RETURN   -- 172.16.0.0/12               (Docker internal)
5  RETURN   -- 127.0.0.0/8                 (Localhost)
6  DROP     tcp  -> :18789                  (Everything else)
7  DROP     tcp  -> :50606                  (Everything else)
8  RETURN   -- (all other traffic passes)
```

To apply these rules:

```bash
# Flush and recreate DOCKER-USER rules
iptables -F DOCKER-USER
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A DOCKER-USER -p tcp --dport 18789 -s 100.64.0.0/10 -j RETURN
iptables -A DOCKER-USER -p tcp --dport 50606 -s 100.64.0.0/10 -j RETURN
iptables -A DOCKER-USER -s 172.16.0.0/12 -j RETURN
iptables -A DOCKER-USER -s 127.0.0.0/8 -j RETURN
iptables -A DOCKER-USER -p tcp --dport 18789 -j DROP
iptables -A DOCKER-USER -p tcp --dport 50606 -j DROP
iptables -A DOCKER-USER -j RETURN

# Persist across reboots
iptables-save > /etc/iptables/rules.v4
netfilter-persistent save 2>/dev/null || true
```

#### Layer 3: UFW Rules

UFW rules restrict gateway access to the Tailscale interface:

```bash
# SSH: Tailscale only
ufw allow in on tailscale0 to any port 22 proto tcp

# OpenClaw gateway: Tailscale only
ufw allow in on tailscale0 to any port 18789 proto tcp comment 'OpenClaw Gateway (Tailscale only)'

# Hostinger panel: Tailscale only
ufw allow in on tailscale0 to any port 50606 proto tcp

# MCP ports: Docker internal only
ufw allow from 172.17.0.0/16 to any port 8101:8104 proto tcp
ufw allow from 172.18.0.0/16 to any port 8101:8104 proto tcp
ufw allow from 127.0.0.1 to any port 8101:8104 proto tcp

# Web (if needed)
ufw allow 80/tcp
ufw allow 443/tcp

# Default policy
ufw default deny incoming
ufw default allow outgoing
```

**Why 3 layers?** Docker bypasses UFW via its own iptables chains. If any single layer fails (Docker update resets rules, UFW misconfigured, Hostinger network changes), the other two still protect you. The gateway WebSocket gives access to WhatsApp, the agent, and all connected tools.

### Hostinger's External Firewall

Hostinger also has a network-level firewall in their VPS panel that blocks non-standard ports by default. This provides a fourth layer but is not under your direct control -- **do not rely on it**.

## Windows PC Setup

### 1. Node Host

The node host connects your Windows PC to the VPS gateway, enabling browser control:

```
Windows: openclaw node run
  -> Connects to VPS gateway (100.124.123.68:18789)
  -> Starts browser relay on localhost:18792
  -> Chrome extension connects to relay
```

**Configuration** (`~\.openclaw\node.json`):
```json
{
  "version": 1,
  "nodeId": "<auto-generated>",
  "displayName": "Windows Browser Node",
  "gateway": {
    "host": "100.124.123.68",
    "port": 18789,
    "tls": false
  }
}
```

**Start manually**:
```powershell
openclaw node run
```

**Install as scheduled task** (requires Admin PowerShell):
```powershell
openclaw node install
```

**Check status**:
```powershell
openclaw node status
```

### 2. Chrome Extension

1. Run `openclaw browser extension install` to install native messaging host files
2. Chrome -> `chrome://extensions` -> Enable "Developer mode"
3. "Load unpacked" -> select `%USERPROFILE%\.openclaw\browser\chrome-extension`
4. Pin the extension, click it on any tab

**Badge meanings:**
- Green/ON: Connected to relay, working
- Red `!`: Relay not reachable (node host not running, or not connected to VPS)

### 3. Harness Repo

```powershell
git clone https://github.com/global-mysterysnailrevolution/harness.git C:\Users\<you>\harness
```

## Updating / Redeployment

### Updating OpenClaw Config

```bash
# On VPS: Edit config
nano /docker/openclaw-kx9d/data/.openclaw/openclaw.json

# Validate before restart
python3 /opt/harness/scripts/openclaw_setup/config_guard.py validate \
  /docker/openclaw-kx9d/data/.openclaw/openclaw.json

# Restart
docker restart openclaw-kx9d-openclaw-1
```

Or use the hardening script for safe, validated updates:
```bash
python3 /opt/harness/scripts/openclaw_setup/apply_openclaw_hardening.py \
  --config-path /docker/openclaw-kx9d/data/.openclaw/openclaw.json
```

### Updating Harness

```bash
cd /opt/harness && git pull
```

### Updating OpenClaw Image

```bash
cd /docker/openclaw-kx9d
docker compose pull
docker compose down && docker compose up -d

# Re-apply python symlink (automatic via custom-entrypoint.sh)
# Re-apply DOCKER-USER rules (if Docker recreated iptables)
iptables -L DOCKER-USER -n  # check if rules survived
```

**After container recreation:**
- The `python` symlink is automatically created by `custom-entrypoint.sh`
- DOCKER-USER iptables rules may need re-application (check with `iptables -L DOCKER-USER -n`)
- The iptables rules should persist across reboots via `/etc/iptables/rules.v4`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| WhatsApp not connecting after restart | Check logs: `docker logs --tail 30 openclaw-kx9d-openclaw-1` |
| `plugin not found` crash | Remove invalid plugin ID from `openclaw.json`, restart |
| `400 unsupported parameter: 'temperature'` | Remove `params` block from model configs in `openclaw.json` |
| `python: not found` in agent exec | Check `custom-entrypoint.sh` exists and has symlink command |
| Chrome extension red `!` | Start node host: `openclaw node run` |
| Port 18789 not reachable via Tailscale | Check `docker compose up` used Tailscale-bound ports |
| `group:memory` warning in logs | Cosmetic; `memory-core` plugin is loaded, tools work fine |
| Config change crashed gateway | Run `python3 config_guard.py rollback /path/to/openclaw.json` |
| DOCKER-USER rules gone after restart | Re-run the iptables commands, save with `iptables-save` |

## File Locations

### VPS
| Path | Content |
|------|---------|
| `/docker/openclaw-kx9d/docker-compose.yml` | Docker Compose config |
| `/docker/openclaw-kx9d/.env` | Environment variables |
| `/docker/openclaw-kx9d/data/.openclaw/openclaw.json` | OpenClaw main config |
| `/docker/openclaw-kx9d/data/.openclaw/workspace/` | Agent workspace |
| `/docker/openclaw-kx9d/data/custom-entrypoint.sh` | Custom entrypoint (python symlink) |
| `/opt/harness/` | Harness repo |
| `/etc/iptables/rules.v4` | Persisted iptables rules |

### Windows
| Path | Content |
|------|---------|
| `~\.openclaw\openclaw.json` | Local OpenClaw config (minimal, for node host) |
| `~\.openclaw\node.json` | Node host connection config |
| `~\.openclaw\browser\chrome-extension\` | Chrome extension files |
| `~\harness\` | Harness repo |

## References

- [Security Hardening Guide](./SECURITY_HARDENING.md)
- [MCP VPS Setup](./MCP_VPS_SETUP.md)
- [Tool Vetting Pipeline](./TOOL_VETTING_PIPELINE.md)
- [Approval Workflow](./APPROVAL_WORKFLOW.md)
- [Prompt-Only Setup](./PROMPT_ONLY_SETUP.md)
- [OpenClaw Docs](https://docs.openclaw.ai)

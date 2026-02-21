# OpenClaw MCP Servers & Skills Setup

Complete guide to add MCP servers and ClawHub skills to your OpenClaw installation.

## Architecture Overview

OpenClaw supports two ways to extend capabilities:

1. **Skills** (ClawHub) — Teach the agent to use CLI tools (gog, gh, slack, etc.). Installed via `clawhub install`.
2. **MCP Plugin** — Connect to MCP servers over HTTP. Requires `openclaw-mcp-plugin` and HTTP-exposing MCP servers.

---

## Part 1: ClawHub Skills (Recommended First)

Skills use existing CLI tools. Browse at [clawhub.ai](https://clawhub.ai).

### Install ClawHub CLI

```bash
npm install -g clawhub
```

### Search and Install Skills

```bash
# Search for skills
clawhub search "google workspace"
clawhub search "github"
clawhub search "slack"

# Install (examples - check ClawHub for exact slugs)
clawhub install gog        # Google Workspace (Gmail, Calendar, Drive)
clawhub install gh        # GitHub (issues, PRs, repos)
clawhub install slack     # Slack messaging
```

Skills install to `./skills` or your OpenClaw workspace. Restart the OpenClaw gateway to load them.

---

## Part 2: MCP Plugin (OpenClaw 2026.1.0+)

The [openclaw-mcp-plugin](https://github.com/lunarpulse/openclaw-mcp-plugin) connects OpenClaw to MCP servers over HTTP.

### Prerequisites

- OpenClaw 2026.1.0 or higher
- Node.js 18+
- MCP servers that expose HTTP/Streamable transport

### Install the Plugin

**For Docker deployments** (your VPS), the OpenClaw data dir is typically under `/docker/openclaw-*/data/`:

```bash
# On VPS - find OpenClaw data dir first
OPENCLAW_DATA=$(docker inspect openclaw-kx9d-openclaw-1 2>/dev/null | jq -r '.[0].Mounts[] | select(.Destination | contains(".openclaw")) | .Source' | head -1)
# Or if config is at /docker/openclaw-kx9d/data/.openclaw/
OPENCLAW_DATA="/docker/openclaw-kx9d/data"

mkdir -p "$OPENCLAW_DATA/.openclaw/extensions"
cd "$OPENCLAW_DATA/.openclaw/extensions"
git clone https://github.com/lunarpulse/openclaw-mcp-plugin mcp-integration
cd mcp-integration
npm install
```

**For local/non-Docker:**

```bash
cd ~/.openclaw/extensions/ || mkdir -p ~/.openclaw/extensions && cd ~/.openclaw/extensions
git clone https://github.com/lunarpulse/openclaw-mcp-plugin mcp-integration
cd mcp-integration
npm install
```

**Note:** OpenClaw 2026.1.0+ required. Check with `openclaw --version` or your Docker image tag.

### Configure MCP Servers in openclaw.json

Add to `~/.openclaw/openclaw.json` (or `/docker/openclaw-kx9d/data/.openclaw/openclaw.json` for Docker):

```json
{
  "plugins": {
    "entries": {
      "mcp-integration": {
        "enabled": true,
        "config": {
          "enabled": true,
          "servers": {
            "filesystem": {
              "enabled": true,
              "transport": "http",
              "url": "http://127.0.0.1:8101/mcp"
            },
            "fetch": {
              "enabled": true,
              "transport": "http",
              "url": "http://127.0.0.1:8102/mcp"
            },
            "github": {
              "enabled": true,
              "transport": "http",
              "url": "http://127.0.0.1:8103/mcp"
            },
            "time": {
              "enabled": true,
              "transport": "http",
              "url": "http://127.0.0.1:8104/mcp"
            }
          }
        }
      }
    }
  }
}
```

### Run MCP Servers (HTTP Bridge)

Most official MCP servers use stdio. Use the bridge script to run them as HTTP:

**On VPS (Linux):**

```bash
cd /opt/harness/scripts
chmod +x run_mcp_servers.sh mcp_stdio_to_http_bridge.js
./run_mcp_servers.sh
```

**Install systemd service (optional):**

```bash
cp /opt/harness/deploy/harness-mcp-servers.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable harness-mcp-servers
systemctl start harness-mcp-servers
```

**Apply OpenClaw config patch:**

```bash
python3 /opt/harness/patch_openclaw_mcp_plugin.py /docker/openclaw-kx9d/data/.openclaw/openclaw.json
docker restart openclaw-kx9d-openclaw-1
```

**Install openclaw-mcp-plugin** (in OpenClaw extensions dir on the host that runs the gateway).

---

## Part 3: Account Setup Tutorial

Each integration requires accounts and API keys. Follow the steps below.

---

### 1. GitHub

**Used for:** Repos, issues, PRs, code search.

**Setup:**

1. Go to [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Name it e.g. `OpenClaw MCP`
4. Select scopes: `repo`, `read:org`, `read:user`, `workflow`
5. Generate and copy the token

**Config:**

```bash
# For MCP GitHub server - set in env when running the bridge
export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_xxxxxxxxxxxx"

# For gog/gh skill - configure in openclaw.json skills.entries
```

**Install gh CLI (for Skills):**

```bash
# Windows (scoop)
scoop install gh

# Linux
sudo apt install gh  # or from https://cli.github.com/
gh auth login
```

---

### 2. Google Workspace (Gmail, Calendar, Drive)

**Used for:** Email, calendar, Drive files.

**Setup:**

1. Install gog CLI: `brew install steipete/tap/gogcli` (macOS) or from [gog releases](https://github.com/steipete/gog/releases)
2. Create OAuth 2.0 credentials in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
   - Create OAuth 2.0 Client ID (Desktop app)
   - Download `client_secret.json`
   - Add redirect URI: `http://localhost:8080/oauth/callback`
3. Run: `gog auth credentials /path/to/client_secret.json`
4. Run: `gog auth add you@gmail.com --services gmail,calendar,drive,contacts,sheets,docs`

**Config:**

```bash
export GOG_ACCOUNT="you@gmail.com"
```

---

### 3. Slack

**Used for:** Channels, messages, notifications.

**Setup:**

1. Go to [Slack API Apps](https://api.slack.com/apps) → Create New App → From scratch
2. Add OAuth scopes: `channels:read`, `channels:history`, `chat:write`, `users:read`, `emoji:read`
3. Install to workspace
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

**Config:**

```bash
export SLACK_BOT_TOKEN="xoxb-xxxxxxxxxxxx"
```

For MCP Slack server, use the same token in env.

---

### 4. Brave Search (Web Search)

**Used for:** Web search (OpenClaw has built-in web tools; this is for MCP Brave Search if needed).

**Setup:**

1. Go to [Brave Search API](https://brave.com/search/api/)
2. Create an API key

**Config:**

```bash
# OpenClaw built-in - configure via:
openclaw configure --section web
# Or set BRAVE_API_KEY in environment
```

---

### 5. Notion

**Used for:** Pages, databases, notes.

**Setup:**

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Create new integration
3. Copy the Internal Integration Secret
4. Share pages/databases with the integration

**Config:**

```bash
export NOTION_API_KEY="secret_xxxxxxxxxxxx"
```

---

### 6. PostgreSQL / Supabase

**Used for:** Database queries.

**Setup:**

- **PostgreSQL:** Use connection string `postgresql://user:pass@host:5432/dbname`
- **Supabase:** Dashboard → Settings → Database → Connection string

**Config:**

```bash
export POSTGRES_URL="postgresql://..."
# or for Supabase
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_KEY="eyJ..."
```

---

### 7. Docker

**Used for:** Container management.

**Setup:** No API key. Ensure Docker is installed and the OpenClaw process can talk to the Docker socket.

```bash
# Linux - add user to docker group
sudo usermod -aG docker $USER
```

---

### 8. Filesystem MCP

**Used for:** Read/write files (restricted to allowed directories).

**Setup:** Configure allowed directory when starting the bridge. No API key.

---

## Part 3.5: Security (HTTPS + Auth + Firewall)

See **[MCP_SECURITY_SETUP.md](MCP_SECURITY_SETUP.md)** for:

- HTTPS (self-signed or Let's Encrypt)
- Bearer token auth
- Firewall rules (Docker + localhost only)
- Restricted filesystem path (`/opt/harness/ai` only)

Run `./scripts/generate_mcp_certs.sh` first, then `./scripts/setup_mcp_firewall.sh`, then start the bridges.

---

## Part 4: Applying the Config

### Option A: Docker (Your VPS)

```bash
# SSH to VPS
ssh root@100.124.123.68

# Edit OpenClaw config
nano /docker/openclaw-kx9d/data/.openclaw/openclaw.json
# Paste the plugins section from Part 2

# Restart OpenClaw
docker restart openclaw-kx9d-openclaw-1
```

### Option B: Local OpenClaw

```bash
# Edit config
nano ~/.openclaw/openclaw.json

# Restart gateway
openclaw gateway restart
```

---

## Part 5: Verify

1. Open OpenClaw UI: http://100.124.123.68:50606 (or your Tailscale IP)
2. Send a message: "List all MCP tools"
3. If configured correctly, the agent will use the `mcp` tool to list available tools
4. For skills: "Check my calendar" (gog) or "List my GitHub issues" (gh)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Plugin not loading | Check `openclaw status` and `openclaw logs \| grep MCP` |
| MCP server connection failed | Ensure bridge/HTTP servers are running on expected ports |
| Skill not found | Run `clawhub list` to verify install; check `skills.load` in config |
| OAuth token expired | Re-run `gog auth add` or `gh auth login` with `--force-consent` |
| Context overflow | Add fewer MCP servers; use `tools.allow` to limit tools per agent |

---

## Quick Reference: Accounts Checklist

| Service | Account | API Key / Token | Where to Get |
|---------|---------|-----------------|--------------|
| GitHub | GitHub.com | Personal Access Token | github.com/settings/tokens |
| Google | Google account | OAuth via gog CLI | console.cloud.google.com |
| Slack | Slack workspace | Bot OAuth Token | api.slack.com/apps |
| Brave | Brave account | API Key | brave.com/search/api |
| Notion | Notion account | Integration Secret | notion.so/my-integrations |
| PostgreSQL | DB admin | Connection string | Your DB provider |
| Supabase | Supabase project | URL + Service Key | supabase.com dashboard |

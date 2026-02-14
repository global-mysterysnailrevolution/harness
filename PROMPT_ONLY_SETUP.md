# Prompt-Only Setup — No Manual Scripts

Set up the full harness by **sending a prompt**. No scripts to run from your laptop.

## How It Works

1. **You send a prompt** (WhatsApp, portal, or API)
2. **Cron + setup trigger** detects it and runs setup on the VPS
3. **Done** — OpenClaw hardening, MCP servers, token saved

## One-Time VPS Deploy

SSH to your VPS once and run:

```bash
cd /opt/harness
git pull
chmod +x scripts/vps/setup_all.sh

# Install cron (checks for setup prompts every minute)
sudo cp deploy/harness-setup-cron /etc/cron.d/
sudo chmod 644 /etc/cron.d/harness-setup-cron

# Start MCP servers on boot
sudo cp deploy/harness-mcp-servers.service /etc/systemd/system/
echo "MCP_BIND=0.0.0.0" >> .env
sudo systemctl daemon-reload
sudo systemctl enable harness-mcp-servers
sudo systemctl start harness-mcp-servers

# Optional: Setup trigger API (for webhook/portal)
pip install flask
sudo cp deploy/harness-setup-trigger.service /etc/systemd/system/
sudo systemctl enable harness-setup-trigger
sudo systemctl start harness-setup-trigger
```

## Ways to Trigger Setup

### 1. WhatsApp (to OpenClaw bot)

Send a message like:

```
Set up everything. Token: sk-ant-xxxxxxxx
```

or

```
Configure harness. Token: sk-xxx
```

The WhatsApp monitor syncs messages from OpenClaw. The cron runs `setup_trigger.py` every minute, finds your message, extracts the token, and runs setup.

**Requires:** WhatsApp monitor running (syncs OpenClaw sessions). Add to cron:

```
* * * * * root cd /opt/harness && python3 scripts/whatsapp_monitor.py >> /var/log/harness-monitor.log 2>&1
```

### 2. Portal (execute queue)

If you have the WhatsApp monitor server (port 8001):

1. Open `http://your-vps:8001` (or via SSH tunnel)
2. Submit: `Set up. Token: sk-xxx`
3. Cron picks it up within a minute

### 3. API (immediate)

```bash
curl -X POST http://your-vps:8003/trigger \
  -H "Content-Type: application/json" \
  -d '{"token":"sk-ant-xxx"}'
```

Requires `harness-setup-trigger` service running.

### 4. OpenClaw skill (from bot)

If the OpenClaw agent has an HTTP/fetch tool, it can POST to the setup API when the user says "set up" with a token. See `openclaw/setup_trigger_skill.md`.

## What Gets Run

When a setup trigger is found, `scripts/vps/setup_all.sh` runs:

1. `git pull` (refresh harness)
2. Save token to `.env`
3. Apply OpenClaw hardening (`apply_openclaw_hardening.py`)
4. Start MCP servers (if not already running)
5. Restart OpenClaw container

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Setup never runs | Check cron: `grep harness /var/log/syslog` or `tail /var/log/harness-setup.log` |
| WhatsApp messages not in feed | Run `python3 scripts/whatsapp_monitor.py` manually. Set `OPENCLAW_CONTAINER` and `SESSIONS_FILE` for your deployment. |
| Token not extracted | Include token in message: "Token: sk-xxx" or "sk-ant-xxx" |
| MCP servers not starting | `systemctl status harness-mcp-servers`; ensure `MCP_BIND=0.0.0.0` in `.env` |

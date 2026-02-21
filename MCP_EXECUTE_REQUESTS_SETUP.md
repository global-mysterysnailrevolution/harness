# MCP: Execute Requests → Cursor

This lets Cursor see execute requests from the harness (WhatsApp/portal commands queued for the broker).

## Option A: Remote (VPS) — Cursor connects to MCP on VPS

Best when you have SSH access. The MCP server runs on the VPS; Cursor connects via tunnel.

### 1. Deploy MCP server on VPS

```bash
# On VPS
cd /opt/harness
pip install -r requirements-mcp-execute.txt
# Run with SSE (HTTP) so Cursor can connect
python -m mcp_execute_requests.server --transport sse --port 8002
```

Or as systemd (`/etc/systemd/system/harness-mcp-execute.service`):

```ini
[Unit]
Description=MCP server for harness execute requests
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/harness
Environment=WHATSAPP_TRANSCRIPTS_DIR=/opt/harness/whatsapp-transcripts
Environment=HOOK_OUTPUT_DIR=/opt/harness/ai/execute_requests
ExecStart=/usr/bin/python3 -m mcp_execute_requests.server --transport sse --port 8002
Restart=always

[Install]
WantedBy=multi-user.target
```

### 2. SSH tunnel from Windows

```powershell
ssh -L 8002:127.0.0.1:8002 root@100.124.123.68
# Leave this running; Cursor connects to localhost:8002
```

### 3. Add to Cursor MCP config

Open **Cursor Settings → Features → MCP**, or edit `%USERPROFILE%\.cursor\mcp.json`:

```json
{
  "mcpServers": {
    "harness-execute-requests": {
      "url": "http://localhost:8002/sse",
      "transport": "sse"
    }
  }
}
```

Restart Cursor. You’ll have `list_execute_requests` and `get_execute_request` tools.

---

## Option B: Local (sync + stdio)

If you prefer not to run an SSH tunnel, sync the data locally and run the MCP server.

### 1. Sync from VPS

```powershell
cd C:\Users\globa\harness-continue
python sync_execute_requests.py
```

Run this when you want fresh data (e.g. before starting Cursor).

### 2. Add to Cursor MCP config

```json
{
  "mcpServers": {
    "harness-execute-requests": {
      "command": "python",
      "args": [
        "-m",
        "mcp_execute_requests.server",
        "--transport",
        "stdio"
      ],
      "env": {
        "WHATSAPP_TRANSCRIPTS_DIR": "C:\\Users\\globa\\harness-continue\\execute_requests_sync\\whatsapp-transcripts",
        "HOOK_OUTPUT_DIR": "C:\\Users\\globa\\harness-continue\\execute_requests_sync\\execute_requests"
      }
    }
  }
}
```

Use absolute paths. Run `sync_execute_requests.py` first so the sync dir exists.

---

## Cursor rule for “monitoring”

Add `.cursor/rules/check-execute-requests.mdc` so Cursor checks for pending requests at the start of conversations:

```yaml
---
description: Check for pending execute requests from harness
alwaysApply: true
---

When starting a conversation, if the harness-execute-requests MCP server is available, call `list_execute_requests` to check for pending commands from WhatsApp/portal. If any are pending, summarize them and ask the user if they want to act on them.
```

---

## Tools

| Tool | Description |
|------|-------------|
| `list_execute_requests` | List pending and recent execute requests |
| `get_execute_request` | Get details of a request by ID |

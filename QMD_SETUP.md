# QMD Setup for OpenClaw

QMD provides fast local search (BM25 + vector + reranking) for your OpenClaw workspace and memory. All models run locally—no API keys required.

## What's Installed

- **Bun** — `C:\Users\globa\.bun\bin\bun.exe` (required by QMD)
- **QMD** — `bun install -g github:tobi/qmd`
- **Index** — `C:\Users\globa\.cache\qmd\index.sqlite` (7 docs from OpenClaw workspace)
- **Models** — `C:\Users\globa\.cache\qmd\models\` (~330MB embedding model)

## Quick Start

### 1. Start QMD MCP Server (before using OpenClaw)

```powershell
cd C:\Users\globa\harness-continue
.\scripts\qmd\start_qmd_mcp.ps1
```

Leave this running. OpenClaw connects to `http://127.0.0.1:8181/mcp`.

### 2. OpenClaw Config

Your `openclaw.json` already has QMD MCP configured under `plugins.entries.mcp-integration.config.servers.qmd`.

**Note:** You need the [openclaw-mcp-plugin](https://github.com/lunarpulse/openclaw-mcp-plugin) installed for MCP to work. If not installed:

```bash
openclaw plugins install @openclaw/mcp-integration
# or from repo
openclaw plugins install github:lunarpulse/openclaw-mcp-plugin
```

### 3. Restart OpenClaw Gateway

After starting QMD MCP, restart the OpenClaw gateway so it picks up the MCP tools.

## QMD Commands (CLI)

Use the wrapper (Bun's `qmd` uses bash; this works on Windows):

```powershell
.\scripts\qmd\qmd.ps1 status
.\scripts\qmd\qmd.ps1 search "learning loop"
.\scripts\qmd\qmd.ps1 vsearch "how to save rules"
.\scripts\qmd\qmd.ps1 query "memory guardrails"
.\scripts\qmd\qmd.ps1 embed   # Re-embed after adding/editing docs
```

Or run via Bun directly:

```powershell
$env:XDG_CACHE_HOME = "$env:USERPROFILE\.cache"
bun "C:\Users\globa\.bun\install\global\node_modules\qmd\src\qmd.ts" status
```

## Add More Collections

```powershell
.\scripts\qmd\qmd.ps1 collection add "C:\Users\globa\harness-continue" --name harness --mask "**/*.md"
.\scripts\qmd\qmd.ps1 embed
```

## MCP Tools Exposed to OpenClaw

When QMD MCP is running and the MCP plugin is loaded:

- `qmd_search` — BM25 keyword search
- `qmd_vector_search` — Semantic vector search
- `qmd_deep_search` — Hybrid + query expansion + reranking
- `qmd_get` — Retrieve document by path or docid
- `qmd_multi_get` — Retrieve multiple documents
- `qmd_status` — Index health and collection info

## Harness Integration

To add QMD to a fresh OpenClaw config:

```powershell
python scripts/openclaw_setup/apply_openclaw_hardening.py --with-qmd
```

For remote (VPS) with QMD on a different host:

```powershell
python scripts/openclaw_setup/apply_openclaw_hardening.py --config-path /path/to/openclaw.json --with-qmd --qmd-mcp-url http://vps-ip:8181
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `bun: command not found` | Add `%USERPROFILE%\.bun\bin` to PATH |
| `SQLiteError: unable to open database file` | Set `$env:XDG_CACHE_HOME = "$env:USERPROFILE\.cache"` and ensure `~\.cache\qmd` exists |
| QMD MCP not connecting | Ensure `start_qmd_mcp.ps1` is running before OpenClaw gateway |
| MCP tools not showing | Install openclaw-mcp-plugin and restart gateway |

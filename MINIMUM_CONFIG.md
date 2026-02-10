# Minimum Configuration Guide

This guide lists the **minimum required configuration** for each platform to get the harness working.

## Codex CLI

### Required Environment Variables
- None (Codex CLI handles authentication internally)

### Required Files
- `.cursor/mcp.json` (if using MCP servers)
- `ai/supervisor/allowlists.json` (created by bootstrap)

### First Steps
1. Run `.\bootstrap.ps1`
2. Configure MCP servers in `.cursor/mcp.json` (optional)
3. Run `.\scripts\verify_harness.ps1`

## Cursor

### Required Environment Variables
- None (Cursor handles authentication internally)

### Required Files
- `.cursor/hooks.json` (created by bootstrap)
- `.cursor/mcp.json` (if using MCP servers)
- `ai/supervisor/allowlists.json` (created by bootstrap)

### First Steps
1. Run `.\bootstrap.ps1`
2. Configure MCP servers in `.cursor/mcp.json` (optional)
3. Restart Cursor to load hooks
4. Run `.\scripts\verify_harness.ps1`

## Claude Code

### Required Environment Variables
- `ANTHROPIC_API_KEY` (required for Claude API)

### Required Files
- `.claude/settings.json` (created by bootstrap)
- `.claude/supervisor.json` (created by bootstrap)
- `.claude/agents/*.md` (created by bootstrap)
- `ai/supervisor/allowlists.json` (created by bootstrap)

### First Steps
1. Set `ANTHROPIC_API_KEY` environment variable
2. Run `.\bootstrap.ps1`
3. Configure agent allowlists in `ai/supervisor/allowlists.json`
4. Run `.\scripts\verify_harness.ps1`

## OpenClaw

### Required Environment Variables
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (depending on model)
- `TOOLHIVE_GATEWAY_URL` (optional, for ToolHive integration)

### Required Files
- `openclaw/supervisor_config.json` (created by bootstrap)
- `openclaw/agent_profiles.json` (created by bootstrap)
- `ai/supervisor/allowlists.json` (created by bootstrap)

### First Steps
1. Set API key environment variable
2. Run `.\bootstrap.ps1`
3. Configure OpenClaw in `openclaw/supervisor_config.json`
4. Set `TOOLHIVE_GATEWAY_URL` if using ToolHive (optional)
5. Run `.\scripts\verify_harness.ps1`

## Gemini

### Required Environment Variables
- `GEMINI_API_KEY` (required for Gemini API)

### Required Files
- `gemini/supervisor_config.json` (created by bootstrap)
- `gemini/context_builder.py` (created by bootstrap)
- `ai/supervisor/allowlists.json` (created by bootstrap)

### First Steps
1. Set `GEMINI_API_KEY` environment variable
2. Run `.\bootstrap.ps1`
3. Configure Gemini in `gemini/supervisor_config.json`
4. Run `.\scripts\verify_harness.ps1`

## ToolHive (Optional but Recommended)

### Required Environment Variables
- `TOOLHIVE_GATEWAY_URL` (e.g., `http://localhost:8080`)

### Setup
1. Install ToolHive (Docker recommended):
   ```bash
   docker run -d --name toolhive -p 8080:8080 stacklok/toolhive:latest
   ```
2. Set `TOOLHIVE_GATEWAY_URL` environment variable
3. Register MCP servers with ToolHive (see `TOOLHIVE_INTEGRATION.md`)

## Common Configuration

### All Platforms Require:
- `ai/supervisor/allowlists.json` - Tool access control
- `ai/supervisor/gates.json` - Gate enforcement rules
- `ai/supervisor/state.json` - Supervisor state (auto-created)
- `ai/supervisor/task_queue.json` - Task queue (auto-created)

### Optional but Recommended:
- MCP server configuration (platform-specific location)
- ToolHive gateway URL (for secure MCP execution)
- Custom agent profiles in `ai/supervisor/allowlists.json`

## Quick Start Checklist

- [ ] Run `.\bootstrap.ps1`
- [ ] Set required API key for your platform
- [ ] Configure `ai/supervisor/allowlists.json` (minimal default created)
- [ ] Run `.\scripts\verify_harness.ps1` (should pass all tests)
- [ ] Run `.\scripts\demo.ps1` (golden demo - optional)
- [ ] Configure MCP servers (optional)
- [ ] Set up ToolHive (optional but recommended for production)

## Troubleshooting

### "API key not found"
- Set the required environment variable for your platform
- Restart your terminal/IDE after setting

### "MCP config not found"
- This is optional - harness works without MCP servers
- Configure `.cursor/mcp.json` or platform-specific MCP config if needed

### "Supervisor files missing"
- Run `.\bootstrap.ps1` again to create missing files
- Check that `ai/supervisor/` directory exists

### "Tool broker not working"
- Install MCP SDK: `pip install mcp`
- Or set up ToolHive gateway (recommended)
- Check `TOOLHIVE_GATEWAY_URL` if using ToolHive

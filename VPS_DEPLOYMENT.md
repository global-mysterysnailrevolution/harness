# VPS Deployment Guide (Hostinger/OpenClaw)

## Critical Pre-Deployment Checklist

Before deploying the harness on a Hostinger VPS with OpenClaw, ensure these blockers are resolved:

### ✅ Blocker A: OpenClaw Skill Wrapper (RESOLVED)

**Problem**: OpenClaw doesn't natively speak MCP yet, so direct MCP integration won't work.

**Solution**: Use the OpenClaw Skill wrapper (`openclaw/harness_skill_wrapper.py`) that exposes tool broker commands as skill commands.

**Setup:**
1. Copy `openclaw/harness_skill_wrapper.py` to your OpenClaw skills directory
2. Register the skill in OpenClaw config
3. Agents can now call:
   - `harness_search_tools`
   - `harness_describe_tool`
   - `harness_call_tool`
   - `harness_load_tools`

**See**: `openclaw/harness_skill.md` for full API documentation.

### ✅ Blocker B: VPS-Friendly Tool Registry (RESOLVED)

**Problem**: Tool broker discovery was Cursor-centric and wouldn't work on a clean VPS.

**Solution**: Harness-native MCP registry at `ai/supervisor/mcp.servers.json` (created by bootstrap).

**Setup:**
1. Bootstrap creates `ai/supervisor/mcp.servers.json` automatically
2. Edit this file to add/configure MCP servers
3. Discovery order:
   1. ToolHive gateway (if `TOOLHIVE_GATEWAY_URL` set)
   2. `ai/supervisor/mcp.servers.json` (harness-native)
   3. Cursor configs (fallback for local dev)
   4. Tool registry cache

**See**: `ai/supervisor/mcp.servers.json` for example configuration.

### MCP Servers on VPS

Run MCP bridges on the host so OpenClaw (in Docker) can use filesystem, memory, GitHub tools:

```bash
cd /opt/harness/scripts
MCP_BIND=0.0.0.0 ./run_mcp_servers.sh
```

Or install as systemd service: see **[MCP_VPS_SETUP.md](MCP_VPS_SETUP.md)**.

### ⚠️ Blocker C: PowerShell Requirement (CHOOSE ONE)

**Problem**: Harness assumes `pwsh` on Linux for verification/demo/workers.

**Options:**

#### Option 1: Install PowerShell (Fastest)
```bash
# Ubuntu/Debian
curl -L -o /tmp/powershell.tar.gz https://github.com/PowerShell/PowerShell/releases/download/v7.4.0/powershell-7.4.0-linux-x64.tar.gz
mkdir -p /opt/microsoft/powershell/7
tar zxf /tmp/powershell.tar.gz -C /opt/microsoft/powershell/7
ln -s /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh

# Verify
pwsh --version
```

#### Option 2: Port Scripts to Python/Bash (Cleaner)
- Worker scripts can be ported to Python (most already have Python versions)
- Demo script has Linux version: `scripts/demo.sh`
- Verification can use Python directly

**Recommendation**: Install `pwsh` for fastest deployment, port scripts later if needed.

## Deployment Steps

### 1. Install Prerequisites

```bash
# Install PowerShell (if using Option 1)
# (see above)

# Install Python 3.11+
sudo apt update
sudo apt install -y python3.11 python3-pip

# Install MCP SDK (optional, for direct MCP support)
pip3 install mcp

# Install Node.js (for MCP servers via npx)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 2. Install OpenClaw

Follow Hostinger's one-click Docker template or OpenClaw's official installation guide.

### 3. Clone and Bootstrap Harness

```bash
# Clone harness
git clone https://github.com/global-mysterysnailrevolution/harness.git
cd harness

# Bootstrap (creates all configs)
pwsh bootstrap.ps1  # or: python3 bootstrap.py (if ported)

# Verify installation
pwsh scripts/verify_harness.ps1  # or: bash scripts/verify_harness.sh (if ported)
```

### 4. Configure OpenClaw Skill

```bash
# Copy skill wrapper to OpenClaw skills directory
cp openclaw/harness_skill_wrapper.py /path/to/openclaw/skills/
cp openclaw/harness_skill.md /path/to/openclaw/skills/

# Make executable
chmod +x /path/to/openclaw/skills/harness_skill_wrapper.py
```

Add to OpenClaw config:
```json
{
  "skills": {
    "harness_tool_broker": {
      "command": "python3",
      "args": ["/path/to/openclaw/skills/harness_skill_wrapper.py"],
      "description": "Harness tool broker skill"
    }
  }
}
```

### 5. Configure MCP Servers

Edit `ai/supervisor/mcp.servers.json`:

```json
{
  "servers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-playwright"],
      "enabled": true
    }
  }
}
```

### 6. (Optional) Set Up ToolHive

```bash
# Run ToolHive container
docker run -d \
  --name toolhive \
  -p 8080:8080 \
  -v toolhive-data:/data \
  stacklok/toolhive:latest

# Set environment variable
export TOOLHIVE_GATEWAY_URL=http://localhost:8080
```

### 7. Test Integration

```bash
# Test tool broker via skill wrapper
python3 openclaw/harness_skill_wrapper.py harness_search_tools '{"query": "browser", "max_results": 5}'

# Test via OpenClaw agent
# (use OpenClaw's agent interface to call harness_search_tools skill)
```

## Security Considerations

### MCP Server Installation

**CRITICAL**: Do not allow arbitrary MCP server installation without:

1. **Wheel-Scout Gate**: Landscape report required before installing new tools
2. **Container Isolation**: Use ToolHive for secure execution
3. **Allowlist-Only**: Only install known-good MCP servers
4. **Secret Scoping**: Secrets scoped per server, not global

### Recommended Approach

1. **Pre-configure known servers** in `ai/supervisor/mcp.servers.json`
2. **Use ToolHive** for dynamic server execution (containerized)
3. **Enforce Wheel-Scout** before any new tool installation
4. **Monitor tool usage** via supervisor budget tracking

## Troubleshooting

### "MCP config not found"
- Check `ai/supervisor/mcp.servers.json` exists
- Verify bootstrap ran successfully
- Check file permissions

### "Tool broker skill not found"
- Verify skill wrapper is in OpenClaw skills directory
- Check OpenClaw config includes the skill
- Verify Python path is correct

### "PowerShell not found"
- Install `pwsh` (see Option 1 above)
- Or use Python/Bash versions of scripts

### "ToolHive gateway not responding"
- Verify ToolHive container is running: `docker ps | grep toolhive`
- Check `TOOLHIVE_GATEWAY_URL` is set correctly
- Test gateway: `curl http://localhost:8080/health`

## Next Steps

1. **Closed-Loop Web Testing**: Set up the web-runner → judge → fixer loop
2. **ToolHive Integration**: Enable ToolHive for secure MCP execution
3. **Monitoring**: Set up supervisor state monitoring
4. **Scaling**: Configure multiple agents with different tool profiles

## References

- [OpenClaw Browser Tool](https://docs.openclaw.ai/tools/browser)
- [OpenClaw Local Models](https://docs.openclaw.ai/gateway/local-models)
- [ToolHive Integration Guide](./TOOLHIVE_INTEGRATION.md)
- [OpenClaw Integration Guide](./OPENCLAW_INTEGRATION.md)

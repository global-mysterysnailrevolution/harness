# Final OpenClaw Integration Fixes

## Summary of Fixes

All remaining issues from the security review have been addressed.

## ✅ Fixed Issues

### 1. Removed Per-Call Tools Parameter

**Problem**: Example showed `sessions_spawn(agent_id="...", tools={...})` but OpenClaw doesn't support per-call tools.

**Fix**: Updated to spawn by `agentId` only. Tools are defined in `openclaw/agent_profiles.json` and applied automatically.

**Before**:
```python
session_id = openclaw.sessions_spawn(
    agent_id="web-runner-1",
    tools={"allow": ["browser", "image"]}  # ❌ Not supported
)
```

**After**:
```python
session_id = openclaw.sessions_spawn(
    agent_id="web-runner-1"
    # Tools from openclaw/agent_profiles.json applied automatically ✅
)
```

### 2. ToolHive Localhost Binding

**Problem**: Docker Compose exposed ToolHive on all interfaces (`0.0.0.0:8080`).

**Fix**: Bound to localhost only (`127.0.0.1:8080:8080`).

**Before**:
```yaml
ports:
  - "8080:8080"  # ❌ Exposed on all interfaces
```

**After**:
```yaml
ports:
  - "127.0.0.1:8080:8080"  # ✅ localhost only
```

### 3. Hostinger Hardening Guide

**Added**: Complete hardening checklist:
- Firewall configuration (default-deny)
- File permissions (600/700)
- Disable insecure auth
- Network isolation
- Secrets management
- Process isolation
- Monitoring & logging

**File**: `HOSTINGER_HARDENING.md`

### 4. Project Intake System

**Added**: Pre-swarm intake phase that collects:
- Target URLs and auth requirements
- Test requirements and boundaries
- Code change policy
- Secrets needed
- Budget limits
- Stopping conditions
- Agent role configuration
- Forge policy

**Files**:
- `scripts/supervisor/project_intake.py` - Intake system
- `PROJECT_INTAKE.md` - Usage guide

### 5. AgentId-Based Spawning Documentation

**Added**: Clear documentation that agents are spawned by `agentId`, with tools defined in profiles, not per-call.

## Already Fixed (From Previous Work)

- ✅ Removed `context_file` parameter (uses workspace files + `sessions_send`)
- ✅ Removed MCP client assumptions (uses skill wrapper)
- ✅ Linux bootstrap script (`bootstrap.sh`)
- ✅ Security hardening (single choke point, forge approval, etc.)

## Verification Checklist

- [x] No `context_file` in `sessions_spawn` examples
- [x] No per-call `tools={}` parameter
- [x] No `mcp.servers` config assumptions
- [x] ToolHive bound to localhost
- [x] Hostinger hardening guide complete
- [x] Project intake system implemented
- [x] AgentId-based spawning documented

## Next Steps

1. **Harden Hostinger VPS**: Follow `HOSTINGER_HARDENING.md`
2. **Run Project Intake**: `python scripts/supervisor/project_intake.py collect`
3. **Configure Agent Profiles**: Edit `openclaw/agent_profiles.json`
4. **Start ToolHive**: `docker-compose up -d toolhive`
5. **Test Integration**: Verify skill wrapper works

## Architecture (Final)

```
OpenClaw Agent (agentId-based, tools from profile)
    ↓
Skill Wrapper (harness_search_tools, etc.)
    ↓
Tool Broker (Security Policy: allowlists, rate limits, validation, budgets)
    ↓
ToolHive Gateway (localhost:8080, containerized)
    ↓
MCP Servers (separate containers, read-only filesystem)
```

All security boundaries enforced at broker level.

## References

- [OpenClaw Session Tools](https://docs.openclaw.ai/concepts/session-tool)
- [OpenClaw Multi-Agent](https://docs.openclaw.ai/concepts/multi-agent)
- [Hostinger Hardening](./HOSTINGER_HARDENING.md)
- [Project Intake](./PROJECT_INTAKE.md)
- [Security Hardening](./SECURITY_HARDENING.md)

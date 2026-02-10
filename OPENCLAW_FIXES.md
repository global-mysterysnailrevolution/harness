# OpenClaw Integration Fixes

## Critical Issues Fixed

### 1. ✅ Removed `context_file` Parameter (Doesn't Exist in OpenClaw API)

**Problem**: `OPENCLAW_INTEGRATION.md` and `context_builder_hook.py` referenced `context_file` parameter in `sessions_spawn()`, but OpenClaw doesn't support this.

**Fix**:
- Updated `OPENCLAW_INTEGRATION.md` to use workspace files + `sessions_send` instead
- Updated `context_builder_hook.py` to write context to workspace files
- Context is now written to `ai/context/specialized/{agent_id}_CONTEXT.md` in workspace
- Agent receives initial message via `sessions_send` pointing to context file

**New Pattern**:
```python
# Write context to workspace
context_file = workspace_path / "ai/context/specialized" / f"{agent_id}_CONTEXT.md"
context_file.write_text(context_content)

# Spawn agent
session_id = openclaw.sessions_spawn(agent_id="web-runner-1", tools={...})

# Send message pointing to context
openclaw.sessions_send(
    session_id=session_id,
    message=f"Read {context_file} and acknowledge constraints."
)
```

### 2. ✅ Linux-Native Bootstrap Script

**Problem**: Harness assumed PowerShell (`pwsh`) on Linux, creating friction for VPS deployment.

**Fix**:
- Created `bootstrap.sh` - Pure bash script for Linux/Mac
- Creates all required directories and config files
- No PowerShell dependency
- Creates `.openclaw/` directories for team/task structure

**Usage**:
```bash
bash bootstrap.sh
# or
./bootstrap.sh
```

### 3. ✅ Orchestrator Prompt for Claude-Teams-Style Workflow

**Created**: `openclaw/orchestrator_prompt.md`

**Features**:
- Shared task system (`.openclaw/tasks/` JSON files)
- Team structure (`.openclaw/teams/`)
- Agent inboxes (`.openclaw/inbox/`)
- Explicit dependencies (`blocked_by`, `blocking`)
- Messaging protocol via `sessions_send`
- Integration with harness (Wheel-Scout = researcher, Tool Broker via skills)

**Usage**: Paste into OpenClaw main agent as instructions.

### 4. ✅ Docker Compose for VPS Deployment

**Created**: `docker-compose.yml` and `Dockerfile.broker`

**Services**:
- ToolHive gateway (optional but recommended)
- Harness broker (optional service mode)

**Benefits**:
- Isolated services
- Easy VPS deployment
- Network configuration
- Volume persistence

### 5. ✅ Updated Context Builder Hook

**Changes**:
- Now accepts `workspace_path` parameter
- Writes context to workspace (not injected via API)
- Returns Path object for context file location
- Compatible with workspace file pattern

## Deployment Path (Updated)

### On Hostinger VPS:

```bash
# 1. Clone harness
git clone https://github.com/global-mysterysnailrevolution/harness.git
cd harness

# 2. Bootstrap (Linux-native, no pwsh needed)
bash bootstrap.sh

# 3. (Optional) Start ToolHive
docker-compose up -d toolhive

# 4. Configure OpenClaw
# - Copy harness_skill_wrapper.py to OpenClaw skills
# - Register skill in OpenClaw config
# - Use orchestrator_prompt.md as main agent instructions

# 5. Test
python3 openclaw/harness_skill_wrapper.py harness_search_tools '{"query": "browser"}'
```

## Key Differences from Previous Version

| Before | After |
|--------|-------|
| `context_file` parameter (doesn't exist) | Workspace files + `sessions_send` |
| PowerShell-only bootstrap | Bash bootstrap + PowerShell option |
| No orchestrator prompt | Complete orchestrator prompt |
| No Docker setup | Docker Compose for services |
| Cursor-centric MCP discovery | VPS-friendly registry first |

## Integration Points

### Context Builder
- Writes to workspace: `ai/context/specialized/{agent_id}_CONTEXT.md`
- Agent receives message: "Read {path} and acknowledge constraints"

### Tool Broker
- Accessed via OpenClaw Skill (not MCP)
- Commands: `harness_search_tools`, `harness_describe_tool`, `harness_call_tool`, `harness_load_tools`

### Task System
- Tasks in `.openclaw/tasks/{id}.json`
- Team metadata in `.openclaw/teams/{team_id}/team.json`
- Status in `.openclaw/status.md`

### Messaging
- Via `sessions_send` (agent-to-agent)
- Inbox files: `.openclaw/inbox/{agent_id}.md`

## Next Steps

1. **Test on Hostinger VPS**: Deploy and verify all components work
2. **Configure ToolHive**: Set up gateway for secure MCP execution
3. **Set up Closed-Loop Testing**: Implement Runner → Judge → Fixer loop
4. **Add MCP Forge**: Gated workflow for dynamic MCP server installation

## References

- [OpenClaw Session Tools](https://docs.openclaw.ai/concepts/session-tool)
- [OpenClaw Multi-Agent](https://docs.openclaw.ai/concepts/multi-agent)
- [VPS Deployment Guide](./VPS_DEPLOYMENT.md)
- [OpenClaw Integration Guide](./OPENCLAW_INTEGRATION.md)

# Security Hardening Guide

## Single VPS Architecture Principles

On a single Hostinger VPS, treat this as a **multi-tenant automation platform**. The security model is:

**OpenClaw Agents → Single Choke Point (Broker) → Everything Else**

## 1. Single Choke Point: Make Broker Boring

### Architecture

```
OpenClaw Agent → Skill Wrapper → Tool Broker → ToolHive Gateway → MCP Servers (containers)
```

**Key Principle**: Agents never touch Docker, never touch arbitrary network, never touch random CLIs directly.

### Broker Interface

Agents get exactly one interface to "do tool things":

- **Option A (Recommended)**: OpenClaw Skill wrapper
  - `harness_search_tools`
  - `harness_describe_tool`
  - `harness_call_tool`
  - `harness_load_tools`

- **Option B (Alternative)**: Restricted exec
  - Only allow: `python -m scripts.broker.tool_broker call --tool <name> --json <args>`
  - No other exec commands allowed

### Capability-Scoped Access

Broker enforces per-agent:
- **Tool allowlists** (which tools can be called)
- **Rate limits** (max calls per time window)
- **Argument validation** (block dangerous patterns)
- **Budget limits** (tokens, API calls, cost)

See `ai/supervisor/security_policy.json` for configuration.

## 2. MCP Servers: Containers Only

### ToolHive Gateway (Recommended)

All MCP servers run in containers via ToolHive:
- Separate containers per server
- Read-only filesystem where possible
- No host Docker socket exposed
- Strict egress rules (firewall)

### Architecture

```
Agent → Broker → ToolHive Gateway → MCP Server Container
```

**Why**: "MCP forge" without containment is remote code execution.

## 3. Secrets Policy

### Rules

1. **Never in context**: Secrets never written to `ai/context/` or workspace files
2. **Never in repo**: No secrets committed to git
3. **Scoped per tool**: Broker injects secrets only at call time for specific tool
4. **Log redaction**: Broker redacts secrets from logs/artifacts

### Implementation

- Secrets in Hostinger env vars or local secrets file (readable only by broker user)
- Broker injects via environment variables to tool containers
- Log redaction at broker boundary (see `security_policy.py`)

## 4. Deterministic Discovery

### Registry-First Approach

Start with fixed, explicit registry:
- `ai/supervisor/mcp.servers.json` - Approved MCP servers + versions + tools
- Only after system works end-to-end, add search/install automation

### Discovery Order

1. ToolHive gateway (if `TOOLHIVE_GATEWAY_URL` set)
2. `ai/supervisor/mcp.servers.json` (harness-native registry)
3. Cursor configs (fallback for local dev)
4. Tool registry cache

**Why**: Dynamic discovery is where reliability and security go to die early.

## 5. Hard Safety Gate: Forge Approval

### No New Executable Code Without Approval

**Required for**:
- Pulling new MCP server image
- Building from new repo
- Attaching secrets to tool
- Installing new npm packages

### Approval Workflow

1. **Propose**: System creates proposal in `ai/supervisor/forge_approvals/`
2. **Smoke Test**: Run harmless test (list tools, no-op call)
3. **Human Approval**: Explicit approve command/click required
4. **Promote**: Only then add to registry and enable

### Implementation

See `scripts/broker/forge_approval.py` for approval system.

**Usage**:
```python
from scripts.broker.forge_approval import ForgeApproval

forge = ForgeApproval()

# Propose new server
proposal = forge.propose_server(
    server_name="new-server",
    source="docker_image",
    source_id="image:tag",
    proposed_by="agent-1"
)

# Human must approve
forge.approve(proposal["id"], approved_by="human", smoke_test_result={...})
```

## 6. Network Boundary

### Binding

- ToolHive: `localhost:8080` or private Docker network
- Broker: `localhost:8000` (if running as service)
- OpenClaw: Public UI/API only if needed

### Firewall

- Block all egress except:
  - ToolHive gateway (if external)
  - Approved API endpoints
  - DNS

## 7. Artifact Hygiene

### Storage

- Screenshots/logs under `ai/artifacts/<run_id>/...`
- Bounded by:
  - Size: `max_artifact_size_mb` (default: 100MB)
  - Time: `artifact_retention_days` (default: 7 days)

### Cleanup

Automatic cleanup of old artifacts to prevent disk DoS.

## 8. Broker Identity & Auth

### Agent Identity

Broker requires agent/session identity:
- Agent ID from OpenClaw session
- Signed token (if available)
- Enables per-agent policy enforcement

### Implementation

All broker calls include `agent_id` parameter for:
- Allowlist checks
- Rate limiting
- Budget tracking
- Audit logging

## Implementation Checklist

- [x] Single choke point (broker with skill wrapper)
- [x] Security policy enforcement (rate limits, validation, budgets)
- [x] Forge approval system (no new code without approval)
- [x] Secrets policy (never in context/repo, scoped per tool)
- [x] Deterministic registry (`mcp.servers.json`)
- [x] Log redaction (secrets redacted at boundary)
- [x] Artifact hygiene (bounded storage)
- [ ] ToolHive gateway setup (Docker Compose)
- [ ] Network firewall rules
- [ ] Broker HTTP service (optional, for localhost access)

## Next Steps

1. **Set up ToolHive**: `docker-compose up -d toolhive`
2. **Configure security policy**: Edit `ai/supervisor/security_policy.json`
3. **Test approval workflow**: Propose → Smoke test → Approve
4. **Enable forge approval**: Set `forge_approval_required: true` in security policy
5. **Configure budgets**: Set per-agent limits in security policy

## References

- [VPS Deployment Guide](./VPS_DEPLOYMENT.md)
- [OpenClaw Integration](./OPENCLAW_INTEGRATION.md)
- [ToolHive Integration](./TOOLHIVE_INTEGRATION.md)

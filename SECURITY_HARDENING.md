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

## 6. Network Boundary — Docker + Tailscale Hardening

### Principle: Three-Layer Defense-in-Depth

Docker bypasses UFW via its own iptables chains. A single misconfigured port binding (`0.0.0.0:18789` instead of `100.124.123.68:18789`) exposes the OpenClaw gateway — and with it, WhatsApp, the agent, and all connected tools — to the public internet. We use three independent layers:

| Layer | What it does | Survives Docker restart? |
|-------|-------------|------------------------|
| **Docker port binding** | Bind to Tailscale IP only in `docker-compose.yml` | Yes (compose config) |
| **DOCKER-USER iptables** | DROP non-Tailscale traffic to Docker ports | Needs `/etc/iptables/rules.v4` |
| **UFW rules** | Restrict ports to `tailscale0` interface | Yes (ufw persistent) |

### Docker Compose Port Binding

Always bind Docker-published ports to the Tailscale IP, never `0.0.0.0`:

```yaml
ports:
  # CORRECT: Tailscale-only
  - "100.124.123.68:18789:63362"
  
  # WRONG: Exposed to all interfaces including public internet
  # - "18789:63362"
```

### DOCKER-USER iptables Rules

```bash
iptables -F DOCKER-USER
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A DOCKER-USER -p tcp --dport 18789 -s 100.64.0.0/10 -j RETURN  # Tailscale
iptables -A DOCKER-USER -p tcp --dport 50606 -s 100.64.0.0/10 -j RETURN  # Tailscale
iptables -A DOCKER-USER -s 172.16.0.0/12 -j RETURN                        # Docker nets
iptables -A DOCKER-USER -s 127.0.0.0/8 -j RETURN                          # Localhost
iptables -A DOCKER-USER -p tcp --dport 18789 -j DROP                       # Drop all else
iptables -A DOCKER-USER -p tcp --dport 50606 -j DROP                       # Drop all else
iptables -A DOCKER-USER -j RETURN                                          # Pass other traffic

# Persist
iptables-save > /etc/iptables/rules.v4
```

### UFW Rules

```bash
ufw allow in on tailscale0 to any port 22 proto tcp
ufw allow in on tailscale0 to any port 18789 proto tcp comment 'OpenClaw Gateway (Tailscale only)'
ufw allow in on tailscale0 to any port 50606 proto tcp
```

### Verification

```bash
# Check port bindings (should show Tailscale IP, not 0.0.0.0)
ss -tlnp | grep -E '18789|50606'

# Check DOCKER-USER chain
iptables -L DOCKER-USER -n --line-numbers

# Check UFW
ufw status | grep -E '18789|50606|22'

# Test public non-access (should fail/timeout)
curl -m 5 http://<public-ip>:18789 2>&1 || echo "GOOD: not publicly accessible"
```

### Binding Summary

| Port | Service | Binding | Access |
|------|---------|---------|--------|
| 18789 | OpenClaw Gateway WS | Tailscale IP only | Tailscale VPN |
| 50606 | Hostinger panel | Tailscale IP only | Tailscale VPN |
| 8101-8104 | MCP servers | Docker internal + localhost | Container-to-host |
| 22 | SSH | Tailscale interface | Tailscale VPN |
| 80, 443 | Web | All interfaces | Public (if needed) |

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

## 9. OpenClaw Config Safety

### ConfigGuard

All OpenClaw config changes should go through `ConfigGuard` (`scripts/openclaw_setup/config_guard.py`):

- **Validates** plugin IDs against known set (prevents crash-causing `"plugin not found"` errors)
- **Validates** enum values (gateway.mode, compaction.mode, tools.profile, etc.)
- **Backs up** config before every write (timestamped `.guard-bak.*` files)
- **Health-checks** the Docker container after changes
- **Auto-rolls back** if the container crashes

### Known Config Pitfalls

| Pitfall | Impact | Prevention |
|---------|--------|-----------|
| Unknown plugin ID in `plugins.entries` | Gateway crash, WhatsApp dies | ConfigGuard validates against `openclaw plugins list` |
| `params.temperature` on GPT-5.2 | `400 unsupported parameter` on every message | Don't add `params` to model configs |
| Invalid `contextPruning.maxTokens` | Gateway won't start | Use only documented keys |
| `gateway.mode` unset | Gateway won't start | Always set to `local` for VPS |
| `python` binary not found | Agent exec commands fail | Custom entrypoint creates symlink |

## Implementation Checklist

- [x] Single choke point (broker with skill wrapper)
- [x] Security policy enforcement (rate limits, validation, budgets)
- [x] Forge approval system (no new code without approval)
- [x] Secrets policy (never in context/repo, scoped per tool)
- [x] Deterministic registry (`mcp.servers.json`)
- [x] Log redaction (secrets redacted at boundary)
- [x] Artifact hygiene (bounded storage)
- [x] Docker port isolation (Tailscale-only binding)
- [x] DOCKER-USER iptables rules (defense-in-depth)
- [x] UFW firewall rules (Tailscale interface restriction)
- [x] ConfigGuard validation + auto-rollback
- [x] Custom entrypoint (python symlink persistence)
- [ ] ToolHive gateway setup (Docker Compose)
- [ ] Broker HTTP service (optional, for localhost access)

## References

- [VPS Deployment Guide](./VPS_DEPLOYMENT.md)
- [OpenClaw Integration](./OPENCLAW_INTEGRATION.md)
- [ToolHive Integration](./TOOLHIVE_INTEGRATION.md)

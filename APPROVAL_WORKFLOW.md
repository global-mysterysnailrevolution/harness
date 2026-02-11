# Approval Workflow Guide

## Overview

When an agent tries to call a tool that isn't in its allowlist, the broker can request approval instead of immediately failing. This enables controlled access expansion without manual allowlist editing.

## How It Works

### 1. Agent Requests Tool

When an agent calls a tool not in its allowlist:

```python
result = broker.call_tool("new-tool:action", {"param": "value"}, agent_id="web-runner")
```

### 2. Broker Returns Approval Request

Instead of failing, broker returns:

```json
{
  "error": "approval_required",
  "request_id": "abc123def456",
  "agent_id": "web-runner",
  "tool_id": "new-tool:action",
  "how_to_approve": "python3 scripts/broker/tool_broker.py approve --request-id abc123def456",
  "summary": "Agent 'web-runner' wants to call tool 'new-tool:action'"
}
```

### 3. Review Pending Approvals

```bash
python3 scripts/broker/tool_broker.py pending
```

Returns list of all pending requests:

```json
[
  {
    "id": "abc123def456",
    "agent_id": "web-runner",
    "tool_id": "new-tool:action",
    "args": {"param": "value"},
    "status": "pending",
    "requested_at": "2024-01-15T10:30:00",
    "summary": "Agent 'web-runner' wants to call tool 'new-tool:action'"
  }
]
```

### 4. Approve or Reject

**Approve:**
```bash
python3 scripts/broker/tool_broker.py approve --request-id abc123def456
```

This:
- Adds tool to agent's allowlist
- Marks request as approved
- Agent can retry the call

**Reject:**
```bash
python3 scripts/broker/tool_broker.py reject --request-id abc123def456 --reason "Tool not needed for this task"
```

This:
- Marks request as rejected
- Does NOT add to allowlist
- Agent call will fail

## Configuration

### Enable/Disable Approval Workflow

Edit `ai/supervisor/security_policy.json`:

```json
{
  "tool_approval_required": true  // false = fail immediately, true = request approval
}
```

### Auto-Approve Patterns

You can configure patterns that auto-approve (future enhancement):

```json
{
  "auto_approve_patterns": [
    "read:*",  // Auto-approve all read operations
    "browser:screenshot"  // Auto-approve screenshots
  ]
}
```

## Integration with OpenClaw

### Option 1: Manual Review

1. Agent calls tool → gets `approval_required`
2. Orchestrator logs request
3. Human reviews `pending` list
4. Human approves/rejects via CLI
5. Agent retries (if approved)

### Option 2: Automated Notification

Integrate with notification system (WhatsApp, email, etc.):

```python
# In orchestrator
pending = broker.allowlist_manager.get_pending_approvals()
for request in pending:
    send_notification(f"Approve {request['tool_id']} for {request['agent_id']}? (yes/no)")
```

## Approval Storage

Approvals are stored in:
- `ai/supervisor/pending_approvals.json` - Pending requests
- `ai/supervisor/allowlists.json` - Updated when approved

## Security Considerations

1. **Approval is required by default** - Set `tool_approval_required: false` only in dev
2. **Approvals are persistent** - Once approved, tool stays in allowlist
3. **Review before approving** - Check `args` in pending request
4. **Audit trail** - All approvals/rejections logged with timestamps

## Example Workflow

```bash
# 1. Agent tries tool (not in allowlist)
# → Returns approval_required

# 2. Check pending
python3 scripts/broker/tool_broker.py pending

# 3. Review request details
# Check agent_id, tool_id, args

# 4. Approve if safe
python3 scripts/broker/tool_broker.py approve --request-id abc123

# 5. Agent retries call → succeeds
```

## CLI Reference

```bash
# List pending approvals
python3 scripts/broker/tool_broker.py pending

# Approve a request
python3 scripts/broker/tool_broker.py approve --request-id <id>

# Reject a request
python3 scripts/broker/tool_broker.py reject --request-id <id> --reason "Reason here"
```

## References

- [Security Hardening](./SECURITY_HARDENING.md)
- [Tool Broker Guide](./TOOL_BROKER_GUIDE.md)
- [VPS Deployment](./VPS_DEPLOYMENT.md)

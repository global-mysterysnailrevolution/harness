# OpenClaw Skill Wrapper Setup

## Overview

The `harness_skill_wrapper.py` is a **CLI wrapper** that calls the tool broker. It does NOT automatically become a first-class OpenClaw tool - you must wire it in explicitly.

## Option 1: Register as OpenClaw Skill (Recommended)

### Step 1: Copy Wrapper to Skills Directory

```bash
# Find OpenClaw skills directory (usually ~/.openclaw/skills or configured path)
cp openclaw/harness_skill_wrapper.py /path/to/openclaw/skills/
chmod +x /path/to/openclaw/skills/harness_skill_wrapper.py
```

### Step 2: Register in OpenClaw Config

Edit OpenClaw config (usually `~/.openclaw/config.yaml` or `openclaw.json`):

```yaml
skills:
  harness_tool_broker:
    command: "python3"
    args: ["/path/to/openclaw/skills/harness_skill_wrapper.py"]
    description: "Harness tool broker skill"
    enabled: true
```

### Step 3: Agents Can Now Call

Agents can call:
- `harness_search_tools`
- `harness_describe_tool`
- `harness_call_tool`
- `harness_load_tools`

## Option 2: Restricted Exec (Alternative)

### Configure Restricted Exec

Edit OpenClaw config to allow only the broker command:

```yaml
tools:
  exec:
    allowed_commands:
      - "python3 scripts/broker/tool_broker.py search --query * --max-results *"
      - "python3 scripts/broker/tool_broker.py describe --tool-id *"
      - "python3 scripts/broker/tool_broker.py call --tool-id * --args *"
      - "python3 scripts/broker/tool_broker.py load --tool-ids *"
    require_approval: true  # Require approval for each exec
```

### Agents Call Via Exec

Agents use `exec` tool with the allowed command pattern.

## Option 3: HTTP Service (Cleanest, No Shell)

### Start Broker as Service

```bash
# Via Docker Compose
docker-compose up -d harness-broker

# Or directly
python3 -m scripts.broker.tool_broker server --port 8000 --host 127.0.0.1
```

### Configure HTTP Tool

Agents call broker via HTTP (if OpenClaw supports HTTP tool):

```yaml
tools:
  http:
    allowed_endpoints:
      - "http://127.0.0.1:8000/api/tools/search"
      - "http://127.0.0.1:8000/api/tools/describe"
      - "http://127.0.0.1:8000/api/tools/call"
```

**Note**: This requires broker HTTP API implementation (future enhancement).

## Current Status

The skill wrapper is a **CLI tool** that needs explicit wiring. Choose one of the three options above based on your security model and OpenClaw capabilities.

## Security Considerations

- **Option 1 (Skill)**: Requires skill registration, but cleanest integration
- **Option 2 (Exec)**: Requires strict allowlisting and approval flow
- **Option 3 (HTTP)**: No shell access, but requires HTTP API implementation

## References

- [OpenClaw Skills Documentation](https://docs.openclaw.ai/concepts/system-prompt)
- [Tool Broker Guide](./TOOL_BROKER_GUIDE.md)
- [Security Hardening](./SECURITY_HARDENING.md)

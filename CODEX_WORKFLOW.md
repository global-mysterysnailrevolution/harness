# Codex CLI Workflow Guide

## Overview

This guide explains how the harness integrates with Codex CLI for parallel worker execution and context management.

## Codex CLI Commands

### Background Terminals (`/ps`)

Spawn background workers using Codex's background terminal feature:

```bash
# Spawn context priming worker
codex /ps scripts/workers/context_priming.ps1 --FeatureName "new-feature"

# Spawn memory extraction worker
codex /ps scripts/workers/memory_extraction.ps1 --ContextRemaining 1500 --ContextTotal 10000

# Spawn log monitor
codex /ps scripts/workers/log_monitor.ps1 --ServerCommand "npm start"

# Spawn test writer
codex /ps scripts/workers/test_writer.ps1 --FeaturePath "src/features/new-feature"
```

### Context Status (`/status`)

Monitor context usage to trigger memory extraction:

```bash
# Check context status
codex /status

# Expected output format (approximate):
# Context: 1500/10000 tokens (15.0% remaining)
```

The harness automatically monitors this and triggers memory extraction at 15% threshold.

## MCP Server Integration

Codex runs as an MCP server for IDE integration:

```bash
# Add Codex as MCP server (if not already configured)
codex mcp add codex -- codex mcp-server
```

Configuration in Cursor/IDE:
```json
{
  "mcp.servers": {
    "codex": {
      "command": "codex",
      "args": ["mcp-server"]
    }
  }
}
```

## Parallel Worker Orchestration

### Context Priming (Always Parallel)

When starting a new feature:

```bash
# Main agent starts feature work
# Harness automatically spawns:
codex /ps scripts/workers/context_priming.ps1 --FeatureName "feature-name"
```

Workers run in parallel:
1. Repo-scout maps structure
2. Web-researcher finds docs
3. Implementation-bridger creates plan

### Memory Extraction (Automatic Trigger)

When context approaches limit:

```bash
# Harness detects via /status or token counting
# Automatically spawns:
codex /ps scripts/workers/memory_extraction.ps1 --ContextRemaining 1500 --ContextTotal 10000
```

### Log Monitoring (When Testing)

When dev server is detected:

```bash
# Harness detects server start
# Spawns log monitor:
codex /ps scripts/workers/log_monitor.ps1
```

### Test Writing (Parallel with Features)

When feature implementation detected:

```bash
# Harness detects feature work
# Spawns test writer:
codex /ps scripts/workers/test_writer.ps1 --FeaturePath "src/feature"
```

## Safe/Autonomy Controls

Codex CLI supports autonomy controls. The harness respects these:

- **Safe mode**: Asks before risky operations
- **Autonomous mode**: Proceeds with safety gates only
- **Full autonomy**: Only for non-destructive operations

Configure in Codex settings or via environment variables.

## Workflow Examples

### Starting a New Feature

```bash
# 1. Main agent: "Implement feature X"
# 2. Harness spawns context priming (parallel)
codex /ps scripts/workers/context_priming.ps1 --FeatureName "feature-x"

# 3. Main agent works on feature
# 4. Harness spawns test writer (parallel)
codex /ps scripts/workers/test_writer.ps1 --FeaturePath "src/features/x"

# 5. Results available in ai/context/
```

### Memory Checkpoint

```bash
# 1. Main agent working, context filling up
# 2. Harness monitors: codex /status
# 3. At 15% threshold, spawns memory extraction
codex /ps scripts/workers/memory_extraction.ps1 --ContextRemaining 1500 --ContextTotal 10000

# 4. Memory checkpointed to ai/memory/
# 5. Main agent continues with compacted context + memory pointers
```

### Testing with Logs

```bash
# 1. Start dev server
npm start

# 2. Harness detects and spawns log monitor
codex /ps scripts/workers/log_monitor.ps1 --ServerCommand "npm start"

# 3. Logs monitored, anomalies logged to ai/context/LOG_FINDINGS.md
```

## Best Practices

1. **Always use `/ps` for workers**: Keeps them in background
2. **Monitor `/status` regularly**: For memory extraction triggers
3. **Check lock files**: Before spawning workers, check `ai/_locks/`
4. **Respect cooldowns**: Memory extraction has 5-minute cooldown
5. **Clean up locks**: Workers clean up locks, but verify if stuck

## Troubleshooting

### Workers Not Spawning

- Check Codex CLI is installed and in PATH
- Verify `/ps` command works: `codex /ps echo "test"`
- Check lock files aren't stuck: `ls ai/_locks/`

### Context Status Not Available

- Falls back to token-counting approximation
- Uses file size heuristics
- May trigger slightly early/late

### MCP Server Not Connecting

- Verify Codex is installed: `codex --version`
- Check MCP configuration in IDE settings
- Restart IDE after configuration changes

## Platform Compatibility

Works with:
- **Codex CLI**: Native support via `/ps` and `/status`
- **OpenClaw**: Compatible via standard file-based communication
- **Cursor**: Via MCP server integration
- **Claude Code**: Via subagent definitions

The harness adapts to available features on each platform.

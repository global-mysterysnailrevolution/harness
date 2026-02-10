# Gemini Integration Guide

## Overview

Gemini integration uses the Gemini API's multi-agent capabilities with function calling for context injection and tool broker integration.

## Configuration

### Supervisor Config

Edit `gemini/supervisor_config.json`:

```json
{
  "gemini": {
    "api_key_env": "GEMINI_API_KEY",
    "model": "gemini-2.0-flash-exp",
    "multi_agent": {
      "enabled": true,
      "coordination_method": "function_calling"
    }
  }
}
```

## Usage

### Supervisor Workflow

1. Supervisor uses Gemini API to create agent sessions
2. Context builder prepares specialized context
3. Context injected via function calling
4. Agents coordinate through Gemini's multi-agent system
5. Tool broker provides unified tool access

### Context Injection

Context injected via Gemini function calling:

```python
from gemini.context_builder import build_context_for_gemini_agent, inject_context_via_function_calling

# Build context
context_file = build_context_for_gemini_agent(
    agent_id="agent-1",
    agent_role="web-runner",
    task_description="Test login flow",
    repo_path=Path(".")
)

# Inject via function calling
context_data = inject_context_via_function_calling(context_file)

# Use in Gemini API call
gemini_api.call_function(context_data)
```

### Tool Broker Integration

Agents access tools through broker:

```python
# Agent calls broker function
result = gemini_api.call_function({
    "function": "tool_broker_call",
    "parameters": {
        "tool_id": "github:search_repos",
        "args": {"query": "react"},
        "agent_id": "agent-1"
    }
})
```

## Multi-Agent Coordination

Gemini's multi-agent system handles:
- Agent spawning
- Message passing
- State coordination

Supervisor layer adds:
- Task routing
- Gate enforcement
- Budget tracking
- Context building

## Limitations

- Gemini API rate limits
- Function calling overhead
- Context size limits

## Best Practices

1. Use function calling for context injection
2. Cache contexts to reduce API calls
3. Monitor token usage (Gemini API costs)
4. Use tool broker to reduce tool schema bloat

## Troubleshooting

### API Errors

- Check `GEMINI_API_KEY` environment variable
- Verify API quota not exceeded
- Review rate limits

### Context Not Injecting

- Check context file exists
- Verify function calling format
- Review Gemini API response

### Agents Not Coordinating

- Check multi-agent is enabled
- Verify function calling setup
- Review supervisor state

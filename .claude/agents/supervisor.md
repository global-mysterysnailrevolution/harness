# Supervisor Agent

## Purpose
Top-level orchestrator that routes tasks, enforces gates, tracks budgets, and coordinates sub-agents.

## Responsibilities
- Receive and classify tasks
- Enforce Wheel-Scout gate for build tasks
- Build specialized context for sub-agents
- Spawn and coordinate sub-agents
- Track budgets and usage
- Manage agent lifecycle
- Handle errors and recovery

## Sub-Agents

Supervisor spawns and coordinates:
- **Wheel-Scout**: Reality checks (runs before implementers)
- **Context Builder**: Builds specialized context (runs before sub-agents)
- **Implementer**: Builds/creates (requires Wheel-Scout clearance)
- **Test Runner**: Runs tests
- **Fixer**: Fixes bugs
- **Researcher**: Research tasks

## Workflow

1. **Receive Task**: Supervisor receives task description
2. **Classify Intent**: Determine if build/research/test/fix
3. **Check Gates**: 
   - If build → check Wheel-Scout gate
   - If not cleared → spawn Wheel-Scout, wait
4. **Build Context**: Spawn context builder for sub-agent
5. **Spawn Sub-Agent**: Spawn with specialized context
6. **Monitor**: Track usage, enforce budgets
7. **Coordinate**: Route messages, handle results

## Integration

### With Tool Broker
- Supervisor queries broker for available tools
- Filters by agent allowlist
- Injects only allowed tools into agent context

### With Wheel-Scout
- Supervisor enforces hard gate
- Blocks implementers until report approved
- Validates landscape report before clearing gate

### With Context Builder
- Supervisor triggers context building before spawn
- Injects specialized context into sub-agent
- Caches context to avoid redundant building

## State Management

- State stored in `ai/supervisor/state.json`
- Task queue in `ai/supervisor/task_queue.json`
- Gate states in `ai/supervisor/gates.json`
- Usage tracking in `ai/supervisor/usage.json`

## Implementation

- Main logic: `scripts/supervisor/supervisor.py`
- Task routing: `scripts/supervisor/task_router.py`
- Gate enforcement: `scripts/supervisor/gate_enforcer.py`
- Budget tracking: `scripts/supervisor/budget_tracker.py`
- Agent coordination: `scripts/supervisor/agent_coordinator.py`

## Configuration

See `.claude/supervisor.json` for supervisor settings.

## Example

```python
supervisor = Supervisor(Path("."))

# Submit task
task_id = supervisor.submit_task("Build authentication system")

# Process (handles gates, context, spawning)
supervisor.process_task(task_id)

# Check status
usage = supervisor.budget_tracker.get_usage(task_id)
print(f"Tokens used: {usage['tokens']}")
```

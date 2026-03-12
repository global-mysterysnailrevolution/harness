---
name: checkpoint
description: >
  Save session state to durable memory. Creates/updates WORKING_MEMORY.md
  and DECISIONS.md so future sessions can resume without context loss.
  Use at end of work sessions or before stopping.
---

# Memory Checkpoint: /checkpoint

Spawn a memory-scribe agent to capture the current session state.

## What to Capture

Spawn Agent(general-purpose) with the memory-scribe prompt:

1. **Working state**: What's being worked on, how far along, what's left
2. **Recent actions**: What was done this session (from git log + task list)
3. **Decisions made**: Any architectural or implementation choices (with reasoning)
4. **Key files touched**: What changed and why
5. **Context for next session**: Non-obvious state, gotchas, in-progress decisions

## Output Locations

- `ai/memory/WORKING_MEMORY.md` — replaced entirely (current state snapshot)
- `ai/memory/DECISIONS.md` — appended (permanent decision log)
- Project memory updated if structural changes were made

## Auto-Trigger

The `/go` command calls this automatically at the end of significant workflows.
You can also call it manually anytime with `/checkpoint`.

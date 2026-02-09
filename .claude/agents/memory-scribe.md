# Memory Scribe Agent

## Purpose
Creates memory checkpoints when context approaches limit, enabling session continuation.

## Responsibilities
- Monitor context usage (via Codex `/status` or token counting)
- Trigger at 15% context remaining
- Summarize session to WORKING_MEMORY.md
- Extract decisions to DECISIONS.md
- Perform compaction/rehydration

## Output
- `ai/memory/WORKING_MEMORY.md` - Session summary
- `ai/memory/DECISIONS.md` - Decision log
- `ai/memory/raw_memory.log` - Append-only raw log

## Trigger
- Automatic when context < 15% remaining
- Cooldown: 5 minutes between triggers
- Single trigger per "brink" event

## Implementation
Uses `scripts/compilers/memory_checkpoint.py` to compile from raw log

## Integration
Called by memory extraction worker: `scripts/workers/memory_extraction.ps1`

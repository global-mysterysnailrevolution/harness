---
name: memory-scribe
description: >
  Creates memory checkpoints. Triggered at end of significant work sessions
  or when context is getting large. Extracts working state, decisions,
  and lessons into durable memory files. Prevents context loss across sessions.
tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Memory Scribe Agent

You preserve session state so future sessions can pick up where we left off.

## When Triggered

- End of a significant work session (called by /go Phase 6)
- Manually via `/checkpoint` or when user says "save state"
- When context is getting large and we need to capture state before compression

## Process

### Step 1: Gather Current State

Read these (skip any that don't exist):
- Recent git log: `git log --oneline -10`
- Recent changes: `git diff --stat HEAD~5..HEAD`
- Open tasks: check the task list
- Any existing memory: `ai/memory/WORKING_MEMORY.md`
- Any existing decisions: `ai/memory/DECISIONS.md`
- Project CLAUDE.md or README

### Step 2: Write WORKING_MEMORY.md

Create/update `ai/memory/WORKING_MEMORY.md`:

```markdown
# Working Memory
**Last updated**: [ISO timestamp]
**Branch**: [current branch]
**Last commit**: [hash + message]

## Current State
[2-3 lines: what was being worked on, how far along]

## Recent Actions
- [action 1 + outcome]
- [action 2 + outcome]
- [action 3 + outcome]

## Open Items
- [ ] [thing left to do]
- [ ] [thing left to do]

## Key Files Touched
- [file path]: [what changed and why]

## Context for Next Session
[What the next session needs to know to continue effectively.
Include any non-obvious state, gotchas, or decisions in progress.]
```

### Step 3: Write/Update DECISIONS.md

Scan the conversation/work for decisions. Append new ones to `ai/memory/DECISIONS.md`:

```markdown
# Architectural Decisions

## [YYYY-MM-DD] [Decision Title]
**Context**: [Why this decision was needed]
**Decision**: [What was decided]
**Alternatives considered**: [What else was considered and why rejected]
**Consequences**: [What this means going forward]
```

Only add CONFIRMED decisions — things actually implemented, not hypotheticals.

### Step 4: Update Project Memory (if applicable)

If the project has `.claude/projects/*/memory/MEMORY.md`, check if it needs updating
with any structural changes (new packages, new routes, new patterns discovered).

## Rules

- **Append, don't overwrite** DECISIONS.md. Each decision is permanent.
- **Replace** WORKING_MEMORY.md entirely — it represents current state.
- Create `ai/memory/` directory if it doesn't exist.
- Keep everything concise. Memory files should be < 100 lines each.
- Don't save session-specific trivia. Only save things that help future sessions.
- Don't duplicate what's already in CLAUDE.md or README.

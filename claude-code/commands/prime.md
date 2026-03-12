---
name: prime
description: >
  Context primer for any project. Scans the repo structure, loads session memory,
  and generates a brief context pack. Use at the start of a session, when switching
  tasks, or when you need to re-orient. Triggers on: "prime", "what's the state",
  "load context", "map the repo".
---

# Context Primer: /prime

Generate a rapid context snapshot for the current project.

## Step 1: Project Detection

Check what kind of project this is:
```
- Is this a git repo? (git rev-parse --is-inside-work-tree)
- What's the root? (git rev-parse --show-toplevel)
- Current branch? (git branch --show-current)
```

If NOT in a git repo, just scan the current directory.

## Step 2: Structure Scan (one command)

Run a single tree/find to get the project shape. Exclude noise dirs.
Use Glob patterns to find key files:
- `**/package.json`, `**/pyproject.toml`, `**/Cargo.toml` → detect stack
- `**/CLAUDE.md`, `**/README.md` → existing documentation
- `**/tsconfig.json`, `**/.eslintrc*` → config conventions

Read the top-level package.json / pyproject.toml to understand the project.

## Step 3: Recent Activity

```bash
git log --oneline -10 2>/dev/null
git diff --stat HEAD~5..HEAD 2>/dev/null
```

## Step 4: Memory Recovery

Check for existing session state:
- Project memory: `.claude/projects/*/memory/MEMORY.md`
- Harness memory: `ai/memory/WORKING_MEMORY.md`, `ai/memory/DECISIONS.md`
- Task state: any open tasks in the task list

## Step 5: Output

Present a concise summary (NOT a wall of text):

```
Project: [name] ([stack])
Branch: [branch] | Last commit: [message] ([time ago])
Structure: [X] files, [Y] packages/modules
Memory: [restored/none] | Open tasks: [N]
Key insight: [one line about current state]
```

Then suggest what to work on next based on:
- Open tasks from previous session
- Recent git activity
- Any TODO/FIXME comments in recently changed files

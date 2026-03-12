---
name: chrome
description: "Authenticated browser access via Claude in Chrome. Use /chrome when a task requires access to logged-in accounts (Gmail, GitHub dashboard, Notion, YouTube Studio, etc.), when playwright-cli hits an auth wall, or when the user says 'use my browser', 'log in to', 'check my account', 'authenticated', or needs to interact with a site that requires their active session cookies."
version: 1.0.0
allowed-tools: Bash(claude:*)
---

# /chrome — Authenticated Browser via Claude in Chrome

Spawns a **separate Claude Code process** connected to the user's actual Chrome browser via the Claude in Chrome extension. This gives full access to logged-in sessions, cookies, and open tabs — things playwright-cli cannot reach.

## How it works

Launch a subprocess using `claude --chrome -p "task"` via Bash. The subprocess:
1. Connects to the user's Chrome browser (extension must be running)
2. Executes the task with full auth context
3. Returns the result as text output
4. Exits automatically (`-p` mode)

## Usage pattern

```bash
claude --chrome -p "Navigate to GitHub, go to my notifications, and list the 5 most recent unread notifications with their repo and title"
```

### With budget cap (recommended for autonomous use)

```bash
claude --chrome --max-budget-usd 0.50 -p "Go to Gmail, find the most recent email from AWS, and extract the subject and first paragraph"
```

### With specific allowed tools

```bash
claude --chrome --allowedTools "Bash(playwright-cli:*) Read Write" -p "task description"
```

## When to use /chrome vs other tools

| Situation | Tool |
|-----------|------|
| Site works without login | `playwright-cli` via `/browse` |
| Need perf profiling / console debugging | Chrome DevTools MCP |
| Need to read a public page | `WebFetch` |
| **Site requires login / auth cookies** | `/chrome` (this skill) |
| **Need to act on user's actual accounts** | `/chrome` (this skill) |
| **playwright-cli hit an auth wall** | Escalate to `/chrome` |

## Spawning from a sub-agent

When an agent or sub-agent detects an auth requirement mid-workflow, it should escalate by running:

```bash
claude --chrome --max-budget-usd 0.50 -p "$(cat <<'EOF'
<task description here, including what data to extract or what action to take>

Return results as structured text (markdown table, JSON, or bullet list).
EOF
)"
```

The `--max-budget-usd` flag prevents runaway costs since this spawns a full Claude session.

## Important constraints

- **Chrome extension must be running** — if the user hasn't started it, this will fail. Inform the user they need the Claude in Chrome extension active.
- **Costs a separate session** — this spawns a full Claude Code process with its own API usage. Use only when auth is genuinely required.
- **Cannot run headless** — requires the user's desktop Chrome. Not suitable for CI/CD.
- **Security-sensitive** — has access to all the user's logged-in sessions. Only use for tasks the user has explicitly requested or approved.
- **Always cap budget** — use `--max-budget-usd` when spawning autonomously to prevent cost overruns.

## Auth escalation pattern for browser agent

When composing the prompt for a `browser` agent (via `/browse`), include this fallback instruction:

> If you encounter a login wall or auth-required page that blocks progress, do NOT attempt to guess credentials. Instead, escalate by running:
> `claude --chrome --max-budget-usd 0.50 -p "task requiring auth"`
> and incorporate the result back into your workflow.

## Example: Check GitHub PR reviews

```bash
claude --chrome --max-budget-usd 0.25 -p "Go to github.com, navigate to my open pull requests, and list any PRs that have new review comments I haven't responded to. Format as: repo | PR title | reviewer | comment preview"
```

## Example: Extract data from authenticated dashboard

```bash
claude --chrome --max-budget-usd 0.50 -p "Navigate to Vercel dashboard, find the production deployment for my-app, and report: deployment status, last deploy time, and any recent error logs"
```

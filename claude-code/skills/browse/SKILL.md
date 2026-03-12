---
name: browse
description: "Autonomous browser agent for multi-step web tasks. Use /browse when the user needs to: navigate a website and extract information, fill out multi-step forms, scrape structured data from pages, test a web UI flow end-to-end, take screenshots of specific pages or states, interact with authenticated web apps, or perform any task requiring multiple browser actions. Do NOT use for simple URL fetching where WebFetch suffices — use /browse when the task requires clicking, navigating, form-filling, or multi-page interaction."
version: 1.0.0
---

# /browse — Autonomous Browser Agent

When this skill is invoked, spawn a **background or foreground sub-agent** (type: `general-purpose`) to handle the browsing task autonomously. The sub-agent runs the full browser session and returns a concise summary — keeping snapshots, element refs, and verbose output out of the main context.

## When to use /browse vs other tools

| Need | Use |
|------|-----|
| Fetch a single page's text content | `WebFetch` — no browser needed |
| Quick one-command screenshot | `playwright-cli screenshot` directly via Bash |
| Multi-step browsing (navigate, click, fill, extract) | `/browse` — spawns agent |
| Web scraping across multiple pages | `/browse` — spawns agent |
| Test a web UI flow interactively | `/browse` — spawns agent |
| Browser task during a larger workflow (e.g., `/go`) | Spawn `browser` agent directly via Agent tool |
| Site requires login / auth cookies | `/chrome` — spawns `claude --chrome -p` subprocess |

## How to spawn the browser agent

Use the Agent tool with these parameters:

```
Agent(
  subagent_type: "general-purpose",
  description: "Browse: <3-5 word summary>",
  prompt: <see template below>
)
```

### Agent prompt template

Compose the prompt by combining:
1. The task description from the user
2. The browsing protocol below

```
You are a browser automation agent using playwright-cli.

## Task
<user's browsing task here>

## Protocol
1. Run `playwright-cli open [url]` to start a browser session
2. Run `playwright-cli snapshot` after each navigation to get element refs
3. Use element refs (e1, e2, ...) from snapshots to interact: click, fill, select, etc.
4. For multi-page flows, snapshot after each action to get updated refs
5. Take screenshots with `playwright-cli screenshot --filename=<descriptive>.png` when visual output is needed
6. Always `playwright-cli close` when done

## Output requirements
- Return a concise summary of what was found/done
- Include any extracted data in structured format (markdown table, JSON, etc.)
- If screenshots were taken, list their file paths
- Do NOT include raw snapshot YAML in your response — summarize what you saw
- If a step fails, report the error and what you tried

## Key commands
- `playwright-cli open [url]` — launch browser
- `playwright-cli goto <url>` — navigate
- `playwright-cli snapshot` — get element refs
- `playwright-cli click <ref>` — click element
- `playwright-cli fill <ref> "text"` — fill input
- `playwright-cli type "text"` — type into focused element
- `playwright-cli press Enter` — press key
- `playwright-cli select <ref> "value"` — dropdown
- `playwright-cli screenshot [--filename=name.png]` — capture
- `playwright-cli eval "js expression"` — run JS
- `playwright-cli tab-new [url]` / `tab-select <i>` — tab management
- `playwright-cli console` — check console logs
- `playwright-cli network` — check network requests
- `playwright-cli close` — end session
```

## Foreground vs background

- **Foreground** (default): When the user is waiting for results — e.g., "browse this page and tell me what you find"
- **Background** (`run_in_background: true`): When browsing is part of a larger parallel workflow — e.g., scraping data while also doing code changes

## Named sessions for parallel browsing

If the task requires multiple concurrent browser sessions, use `-s=name`:

```bash
playwright-cli -s=site1 open https://site1.com
playwright-cli -s=site2 open https://site2.com
```

## Authentication / persistent state

For sites requiring login, first try `--persistent` flag or `state-save`/`state-load`:

```bash
playwright-cli open https://app.com --persistent
# ... login flow ...
playwright-cli state-save auth.json
# Later:
playwright-cli state-load auth.json
```

### Auth escalation to Claude in Chrome

If playwright-cli hits a login wall that can't be bypassed with saved state, **escalate** to the user's authenticated Chrome:

```bash
claude --chrome --max-budget-usd 0.50 -p "Navigate to [site], [do the auth-requiring task], and return [the needed data] as structured text"
```

Include this fallback in the agent prompt template (add to the Protocol section):

> 7. If you encounter a login/auth wall you cannot bypass, escalate by running:
>    `claude --chrome --max-budget-usd 0.50 -p "task description"`
>    and incorporate the result. Do NOT guess credentials.

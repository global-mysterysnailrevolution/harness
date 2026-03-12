# Browser Automation Stack — OpenClaw Port

## 1. Overview

Claude Code ships a four-tier browser automation system that selects the cheapest
tool that can solve a given browsing task. The tiers are:

| Tier | Tool | Cost | Auth | Headless |
|------|------|------|------|---------|
| 1 | WebFetch | Minimal — no browser spawn | No | Yes |
| 2 | playwright-cli | Low — compact DOM snapshots | Via state files | Yes |
| 3 | Chrome DevTools MCP | ~9% context for tool defs | No (separate Chrome) | Yes |
| 4 | Claude in Chrome | ~7.7% context for tool defs | Yes (user's sessions) | No |

The system's defining feature is **automatic tier escalation**: an agent starts at
Tier 1 and escalates upward only when the current tier is insufficient. The decision
is made at task-analysis time, not at invocation time, so tokens are never wasted
opening a full browser for a task that only needs page text.

The `browser` agent (Tier 2) includes an **auth escalation pattern**: when it
encounters a login wall mid-workflow, it automatically escalates to Tier 4 by
spawning a `claude --chrome -p` subprocess rather than failing or asking the user.

---

## 2. Problem Statement

OpenClaw's current browser capability is:

- `web_adapter_skill.md` — wraps `WebFetch` for single-page text extraction
- No multi-step interaction (click, fill, navigate, scroll)
- No auth-aware browsing
- No performance profiling or network inspection
- No tier selection logic — every browsing task uses WebFetch regardless of complexity
- No auth escalation pattern

This means:

| Task | Claude Code | OpenClaw |
|------|-------------|---------|
| Read page text | WebFetch | web_adapter_skill (ok) |
| Fill a form, click submit | playwright-cli | UNSUPPORTED |
| Scrape paginated results | playwright-cli | UNSUPPORTED |
| Debug 404 on an API call | Chrome DevTools MCP | UNSUPPORTED |
| Post to a logged-in GitHub repo | Claude in Chrome | UNSUPPORTED |
| Auto-escalate on login wall | Auto via browser agent | UNSUPPORTED |

Porting the browser stack adds these capabilities and, critically, adds the
**decision layer** that prevents developers from defaulting to heavyweight tools
for simple tasks.

---

## 3. Source Analysis

### 3.1 Decision Flow

Claude Code's `/browse` and `browser` agent use this decision tree (embedded in the
`CLAUDE.md` harness rules and the browser agent's system prompt):

```
Task requires browsing?
│
├─ Just need page text? → WebFetch (Tier 1, no browser)
│
├─ Need to click/fill/navigate/scrape (public)?
│   → playwright-cli via /browse or browser agent (Tier 2)
│
├─ Debugging perf, network, console errors?
│   → Chrome DevTools MCP tools (Tier 3)
│
└─ Need logged-in access (Gmail, GitHub dashboard, Notion)?
    → /chrome or chrome agent (Tier 4)
```

The supervisor applies this decision tree during Phase 3 (skill routing) of `/go`.
The `skill-router` agent returns an `INVOKE_VIA` recommendation that includes the
tier level.

### 3.2 Tier 2: playwright-cli

The `browser` agent uses playwright-cli as its sole browser primitive. Key commands:

```bash
# Navigate and take a snapshot (compact accessibility tree, not full HTML)
npx playwright-cli open https://example.com --snapshot

# Click an element
npx playwright-cli click "button[type=submit]"

# Fill an input
npx playwright-cli fill "input[name=email]" "user@example.com"

# Wait for an element
npx playwright-cli wait-for "text=Success"

# Save authentication state
npx playwright-cli open https://example.com --save-storage=.auth/state.json

# Load saved auth state
npx playwright-cli open https://example.com --load-storage=.auth/state.json
```

The browser agent runs these as Bash commands. Each snapshot returns a compact
representation of the page's accessibility tree (not full HTML), which is
dramatically smaller than raw page source — critical for keeping context costs low.

When 3+ browser commands are needed, Claude Code spawns a sub-agent for the entire
task rather than running commands inline. This prevents snapshot noise from
accumulating in the main context window.

### 3.3 Auth Escalation Pattern

The browser agent (Tier 2) includes this logic in its system prompt:

```
When you encounter a login wall or are redirected to an authentication page:
1. Do NOT attempt to guess credentials.
2. Do NOT ask the user for their password.
3. Escalate by running:
   claude --chrome --max-budget-usd 0.50 -p "Complete the task that requires
   auth: {original_task_description}"
4. Incorporate the subprocess result into your workflow.
```

The subprocess is a full Claude session with access to the user's actual Chrome
browser profile (cookies, saved passwords, active sessions).

### 3.4 Tier 3: Chrome DevTools MCP

Claude Code exposes Chrome DevTools Protocol via a set of MCP tools prefixed
`mcp__chrome-devtools__*`. These provide:

- `take_screenshot` — visual snapshot for debugging layout
- `get_network_request` / `list_network_requests` — inspect HTTP traffic
- `get_console_message` / `list_console_messages` — read JS errors
- `evaluate_script` — run arbitrary JS in the page context
- `lighthouse_audit` — Core Web Vitals + accessibility + SEO scores
- `performance_start_trace` / `performance_stop_trace` / `performance_analyze_insight` — flame chart analysis
- `take_memory_snapshot` — heap profiling

These are used when the task is specifically about debugging or performance, not
general browsing.

### 3.5 Tier 4: Claude in Chrome

Invoked via `claude --chrome -p "<task>"`. This spawns a subprocess with:
- Access to the user's current Chrome profile
- All active sessions and cookies
- No need to re-authenticate for any site the user is already logged into

Cost is higher (~7.7% context overhead for tool definitions) but it is the only
tier that can operate on authenticated workflows without credential handling.

---

## 4. Target Architecture

OpenClaw's browser stack port consists of:

1. **`browser_skill.md`** — Tier 2 skill prompt (playwright-cli orchestration)
2. **`chrome_skill.md`** — Tier 4 skill prompt (claude --chrome subprocess)
3. **`browser_router.md`** — Tier selection decision logic (replaces manual choice)
4. **`web_adapter_skill.md`** — EXTEND (add tier routing call at the top)
5. **`tools/playwright_runner.py`** — Thin Python wrapper for playwright-cli commands
   that normalizes output and handles retries
6. **Config additions** — supervisor_config.json, agent_profiles.json

The key adaptation: because OpenClaw cannot spawn native sub-agents with the
`Agent` tool, the browser agent is implemented as a dedicated OpenClaw session
(same mechanism as the forger). The orchestrator dispatches it via a task file and
monitors for completion.

For auth escalation, instead of `claude --chrome -p`, OpenClaw spawns a separate
`chrome_skill` session and passes the task via a task file.

### 4.1 Architecture Diagram

```
User intent: "scrape all job postings from jobs.example.com"
       │
       ▼
browser_router.md
  Evaluates: needs navigation + scraping + multiple pages
  Decision: Tier 2 (playwright-cli)
  No auth needed (public site)
       │
       ▼
.openclaw/tasks/browse-{ts}.json  {tier: 2, task: "..."}
       │
       ▼
browser_skill.md session (browser agent profile)
  ─ playwright-cli open https://jobs.example.com --snapshot
  ─ Read snapshot, find pagination
  ─ playwright-cli click "a[aria-label='Next page']" → snapshot
  ─ Extract data from each page
  ─ Write results to .openclaw/tasks/browse-{ts}-result.json
       │
       ▼ (if login wall encountered)
       │
       ▼
.openclaw/tasks/chrome-{ts}.json  {task: "...with auth context"}
       │
       ▼
chrome_skill.md session (chrome agent profile)
  ─ Uses chrome devtools MCP or claude --chrome subprocess
  ─ Writes result back
```

---

## 5. File Layout

```
openclaw/
├── browser_skill.md               # NEW — Tier 2 playwright-cli orchestration
├── chrome_skill.md                # NEW — Tier 4 authenticated browsing
├── browser_router.md              # NEW — tier selection logic
├── web_adapter_skill.md           # MODIFY — add router call at top
├── tools/
│   └── playwright_runner.py       # NEW — playwright-cli command wrapper
├── supervisor_config.json         # MODIFY
└── agent_profiles.json            # MODIFY — browser + chrome profiles

.openclaw/tasks/
├── browse-{ts}.json               # RUNTIME — task dispatch
├── browse-{ts}-result.json        # RUNTIME — task result
└── chrome-{ts}.json               # RUNTIME — auth-escalated task
```

---

## 6. Adaptation Strategy

### 6.1 Playwright-CLI vs Native Browser Tools

Claude Code's browser agent runs playwright-cli directly via `Bash`. OpenClaw
agents also have `Bash` access, so this is a direct port.

**Key difference**: Claude Code's browser agent is spawned as a sub-agent with its
own isolated context window. In OpenClaw, the browser session is a standalone
session running `browser_skill.md`. It reads the task from a file rather than
receiving it as a prompt argument.

### 6.2 Auth Escalation Without `claude --chrome`

Claude Code escalates by running `claude --chrome --max-budget-usd 0.50 -p "task"`.

OpenClaw adaptation: when `browser_skill.md` detects a login wall, it writes a
`chrome-{ts}.json` task file and sets its own task status to `"escalated_to_chrome"`.
The orchestrator detects this and dispatches a `chrome_skill` session. The chrome
skill uses Chrome DevTools MCP (`mcp__chrome-devtools__*` tools) which connects to
the user's existing Chrome instance.

If Chrome DevTools MCP is not available (no running Chrome instance), the chrome
skill falls back to prompting the user to log in manually and resuming with a
saved playwright state file.

### 6.3 Context Cost Control

Claude Code protects the main context by running the browser agent in a sub-agent.
OpenClaw does the same via session isolation — all playwright snapshots accumulate
in the browser session's context, not the main orchestrator context.

The orchestrator only receives the final structured result from
`.openclaw/tasks/browse-{ts}-result.json`, not the intermediate snapshots.

### 6.4 The 3-Command Rule

Claude Code embeds this rule in the browser agent:

> Any task requiring 3+ browser commands should go through a sub-agent.

OpenClaw adaptation: the browser_router evaluates the task complexity before
dispatching. If the task needs only 1-2 commands (e.g., "get the title of
https://example.com"), the router returns a direct WebFetch recommendation and the
orchestrator handles it inline without spawning a session.

---

## 7. Implementation Plan

### Step 1: Create `playwright_runner.py`

```python
# openclaw/tools/playwright_runner.py
"""
Thin wrapper for playwright-cli commands.
Normalizes output, handles retries, and provides a structured result format.
"""

import subprocess
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

@dataclass
class PlaywrightResult:
    success: bool
    output: str       # snapshot text or command output
    error: str = ""
    screenshot_path: Optional[str] = None

def _run(args: list[str], timeout: int = 30) -> PlaywrightResult:
    """Run a playwright-cli command and return structured result."""
    if not shutil.which("playwright") and not shutil.which("npx"):
        return PlaywrightResult(False, "", "playwright-cli not found. Install with: npm install -g playwright")

    cmd = ["npx", "playwright-cli"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode != 0:
            return PlaywrightResult(False, result.stdout, result.stderr)
        return PlaywrightResult(True, result.stdout)
    except subprocess.TimeoutExpired:
        return PlaywrightResult(False, "", f"Timeout after {timeout}s")
    except Exception as e:
        return PlaywrightResult(False, "", str(e))

def navigate(url: str, storage_state: Optional[str] = None) -> PlaywrightResult:
    """Open a URL and return an accessibility tree snapshot."""
    args = ["open", url, "--snapshot"]
    if storage_state and os.path.exists(storage_state):
        args += ["--load-storage", storage_state]
    return _run(args, timeout=45)

def click(selector: str) -> PlaywrightResult:
    """Click an element by CSS selector or accessible text."""
    return _run(["click", selector])

def fill(selector: str, value: str) -> PlaywrightResult:
    """Fill an input element."""
    return _run(["fill", selector, value])

def press_key(key: str) -> PlaywrightResult:
    """Press a keyboard key."""
    return _run(["press", key])

def wait_for(selector: str, timeout_ms: int = 5000) -> PlaywrightResult:
    """Wait for an element to appear."""
    return _run(["wait-for", selector, "--timeout", str(timeout_ms)])

def take_screenshot(output_path: str) -> PlaywrightResult:
    """Take a screenshot to a file."""
    result = _run(["screenshot", output_path], timeout=20)
    if result.success:
        result.screenshot_path = output_path
    return result

def save_auth_state(output_path: str) -> PlaywrightResult:
    """Save current browser authentication state."""
    return _run(["save-storage", output_path])

def evaluate(js_expression: str) -> PlaywrightResult:
    """Evaluate JavaScript in the current page context."""
    return _run(["evaluate", js_expression])

def check_login_wall(snapshot: str) -> bool:
    """
    Heuristic: does the snapshot look like a login page?
    Returns True if a login wall is detected.
    """
    login_signals = [
        "sign in", "log in", "login", "sign up",
        "email address", "password", "forgot password",
        "create account", "authentication required",
        "you must be logged in", "please log in"
    ]
    snapshot_lower = snapshot.lower()
    matches = sum(1 for signal in login_signals if signal in snapshot_lower)
    return matches >= 2
```

### Step 2: Create `browser_skill.md`

Full content in Section 8.

### Step 3: Create `chrome_skill.md`

Full content in Section 8.

### Step 4: Create `browser_router.md`

Full content in Section 8.

### Step 5: Modify `web_adapter_skill.md`

Add tier routing header at the top of the existing skill.

### Step 6: Add config entries

See Section 8.

---

## 8. Configuration

### `browser_skill.md` (complete file)

```markdown
# Browser Skill (Tier 2 — playwright-cli)

You are the OpenClaw Browser Agent. You perform multi-step web interaction using
playwright-cli: navigation, clicking, form filling, scraping, and paginated data
extraction on PUBLIC (non-authenticated) websites.

## Task Input

Read your task from `.openclaw/tasks/browse-{TASK_ID}.json`:
```json
{
  "task_id": "browse-1741824000",
  "tier": 2,
  "goal": "Scrape all job titles from jobs.example.com",
  "start_url": "https://jobs.example.com",
  "max_pages": 10,
  "output_format": "json_array"
}
```

## Core Loop

1. **Navigate** to `start_url` using playwright-cli open with --snapshot flag.
2. **Read snapshot** — the accessibility tree. DO NOT paste it verbatim into your
   reasoning. Summarize what you see.
3. **Check for login wall** — if the page looks like a login/signup page, STOP
   and escalate (see Escalation section below).
4. **Plan next action** — based on the goal, decide: click, fill, extract, paginate,
   or declare done.
5. **Execute action** via Bash using playwright-cli commands.
6. **Repeat** until goal is achieved or max_steps (default: 20) is reached.

## Key Commands

```bash
# Navigate and snapshot
npx playwright-cli open https://example.com --snapshot

# Click by selector or text
npx playwright-cli click "button:has-text('Next')"
npx playwright-cli click "a[aria-label='Next page']"

# Fill form fields
npx playwright-cli fill "input[name='search']" "python developer"

# Wait for page change
npx playwright-cli wait-for "text=Results"

# Take screenshot for debugging
npx playwright-cli screenshot /tmp/debug.png

# Save/load auth state
npx playwright-cli open https://site.com --save-storage=.auth/{site}.json
npx playwright-cli open https://site.com --load-storage=.auth/{site}.json
```

## Snapshot Hygiene

- NEVER paste a full accessibility tree snapshot into your response.
- Extract only the elements relevant to your goal.
- Summarize page state in 2-3 sentences before deciding next action.
- If a snapshot is longer than 500 lines, focus on the region near your target element.

## Escalation to Chrome (Tier 4)

When you detect a login wall (login/signin/password fields present):
1. Write to `.openclaw/tasks/chrome-{task_id}.json`:
   ```json
   {
     "task_id": "chrome-{original_task_id}",
     "parent_task_id": "{original_task_id}",
     "goal": "{original goal}",
     "start_url": "{url where login wall was detected}",
     "auth_site": "{domain name}",
     "context": "Login wall detected at {url}. Need authenticated session."
   }
   ```
2. Update your own task status to `"escalated_to_chrome"`.
3. Stop — the orchestrator will dispatch chrome_skill and merge results.

## Output

Write structured result to `.openclaw/tasks/browse-{task_id}-result.json`:
```json
{
  "task_id": "browse-{task_id}",
  "status": "complete",
  "goal": "{original goal}",
  "steps_taken": N,
  "result": { ... },  // structured data or text, goal-dependent
  "screenshots": [],  // paths to any debug screenshots
  "errors": []
}
```

## Rules

- Maximum 20 steps per task. If goal is not achieved in 20 steps, set status
  `"partial"` and include what was collected so far.
- NEVER attempt to bypass authentication by guessing credentials.
- NEVER submit forms that could have side effects (purchases, deletes, sends)
  without explicit confirmation in the task file (`"allow_mutations": true`).
- Prefer CSS attribute selectors over XPath.
- If a selector fails, try alternatives: text content, aria-label, role + name.
```

### `chrome_skill.md` (complete file)

```markdown
# Chrome Skill (Tier 4 — Authenticated Browsing)

You are the OpenClaw Chrome Agent. You perform authenticated web interactions
using Chrome DevTools MCP tools, which connect to the user's running Chrome
browser. You have access to the user's active sessions and cookies.

## Task Input

Read your task from `.openclaw/tasks/chrome-{TASK_ID}.json`:
```json
{
  "task_id": "chrome-1741824100",
  "parent_task_id": "browse-1741824000",
  "goal": "Complete the task that requires auth",
  "start_url": "https://github.com/settings/tokens",
  "auth_site": "github.com",
  "context": "Need to read GitHub personal access tokens list"
}
```

## Available Tools

You have access to Chrome DevTools MCP tools:
- `mcp__chrome-devtools__navigate_page` — navigate to URL
- `mcp__chrome-devtools__take_screenshot` — visual snapshot
- `mcp__chrome-devtools__click` — click element
- `mcp__chrome-devtools__fill` — fill input
- `mcp__chrome-devtools__evaluate_script` — run JS
- `mcp__chrome-devtools__list_network_requests` — inspect HTTP traffic
- `mcp__chrome-devtools__list_console_messages` — read JS errors
- `mcp__chrome-devtools__wait_for` — wait for element/condition

## Core Loop

1. Navigate to `start_url` with `mcp__chrome-devtools__navigate_page`.
2. Take a screenshot with `mcp__chrome-devtools__take_screenshot` to confirm
   the page loaded and authentication succeeded.
3. If the screenshot shows a login page, the user's Chrome session for this
   site may not be active. Write to result file with status `"auth_required"`
   and include instructions for the user to log in to `{auth_site}` in their
   Chrome browser, then retry.
4. Execute the goal using DevTools tools.
5. Write result to `.openclaw/tasks/chrome-{task_id}-result.json`.

## Session Check

After navigating, use `mcp__chrome-devtools__evaluate_script` with:
```javascript
document.querySelector('[data-login], [data-user-login], .avatar-user, .user-menu') !== null
```
If this returns `false` or throws, you are not logged in — set status `"auth_required"`.

## Output

Write to `.openclaw/tasks/chrome-{task_id}-result.json`:
```json
{
  "task_id": "chrome-{task_id}",
  "parent_task_id": "{parent_task_id}",
  "status": "complete",
  "result": { ... },
  "screenshots": [],
  "errors": []
}
```

For `"auth_required"` status:
```json
{
  "status": "auth_required",
  "auth_site": "{domain}",
  "message": "Please log in to {domain} in Chrome and retry."
}
```

## Rules

- NEVER fill password fields programmatically.
- NEVER store or log cookie values.
- Maximum 15 steps per task.
- ALWAYS take a screenshot after navigating to confirm auth state.
```

### `browser_router.md` (complete file)

```markdown
# Browser Router

You are the OpenClaw Browser Router. Your job is to analyze a browsing task
and recommend the cheapest tier that can solve it.

## Input

You receive a task description. Analyze it and output a routing decision.

## Tier Definitions

| Tier | Name | When to use |
|------|------|-------------|
| 1 | WebFetch | Read a single page's text. No interaction needed. |
| 2 | playwright-cli (browser_skill) | Multi-step: click, fill, navigate, paginate, scrape. Public sites. |
| 3 | Chrome DevTools MCP | Debugging: perf profiling, network inspection, console errors, Core Web Vitals. |
| 4 | Claude in Chrome (chrome_skill) | Authenticated: requires the user to be logged in. |

## Decision Rules

1. If the task says "get the text/title/content of {url}" AND no interaction needed → Tier 1
2. If the task involves clicking, filling forms, navigating across pages, waiting for
   elements, or scraping multiple pages → Tier 2
3. If the task involves "why is this slow", "network errors", "console errors",
   "Core Web Vitals", "memory leak", "performance profile" → Tier 3
4. If the task involves a site where the user must be logged in
   (email, banking, GitHub private repos, Notion workspace, Slack) → Tier 4
5. If unsure between Tier 2 and Tier 4: check if the URL's domain is typically
   private (requires account). If yes → Tier 4. If public → Tier 2.

## 3-Command Rule

If the task can be solved in 1-2 browser commands (e.g., navigate + screenshot),
recommend handling it INLINE rather than spawning a session. Set `spawn_session: false`.

If the task needs 3+ commands, set `spawn_session: true`.

## Output Format

```json
{
  "tier": 1,
  "tool": "WebFetch",
  "spawn_session": false,
  "rationale": "Task only requires reading page text — no interaction needed.",
  "task_for_session": null
}
```

Or for Tier 2 with session:
```json
{
  "tier": 2,
  "tool": "playwright-cli",
  "spawn_session": true,
  "rationale": "Task requires navigating multiple pages and clicking pagination controls.",
  "task_for_session": {
    "goal": "Scrape all job titles from jobs.example.com",
    "start_url": "https://jobs.example.com",
    "max_pages": 10,
    "output_format": "json_array"
  }
}
```
```

### `supervisor_config.json` additions

```json
{
  "browser_routing": {
    "enabled": true,
    "router_skill": "browser_router",
    "tier_skills": {
      "1": "web_adapter_skill",
      "2": "browser_skill",
      "3": "chrome_devtools_direct",
      "4": "chrome_skill"
    },
    "default_tier": 1,
    "auth_escalation_enabled": true
  },
  "intent_gates": {
    "BrowseIntent": {
      "trigger_patterns": [
        "/browse ",
        "/chrome ",
        "scrape ",
        "navigate to ",
        "click on ",
        "fill out the form",
        "log in to ",
        "check the website"
      ],
      "dispatches_to": "browser_router",
      "pre_route": true
    }
  }
}
```

### `agent_profiles.json` additions

```json
{
  "browser": {
    "description": "Tier 2 multi-step browser automation using playwright-cli",
    "model": "claude-sonnet-4-5",
    "allowed_tools": [
      "Bash",
      "Read",
      "Write",
      "Glob"
    ],
    "bash_allowlist": [
      "npx playwright-cli",
      "playwright",
      "node",
      "cat",
      "ls",
      "mkdir"
    ],
    "max_steps": 20,
    "context_budget_tokens": 40000,
    "task_file_pattern": ".openclaw/tasks/browse-*.json"
  },
  "chrome": {
    "description": "Tier 4 authenticated browsing via Chrome DevTools MCP",
    "model": "claude-sonnet-4-5",
    "allowed_tools": [
      "mcp__chrome-devtools__navigate_page",
      "mcp__chrome-devtools__take_screenshot",
      "mcp__chrome-devtools__click",
      "mcp__chrome-devtools__fill",
      "mcp__chrome-devtools__evaluate_script",
      "mcp__chrome-devtools__list_network_requests",
      "mcp__chrome-devtools__list_console_messages",
      "mcp__chrome-devtools__wait_for",
      "Read",
      "Write"
    ],
    "max_steps": 15,
    "task_file_pattern": ".openclaw/tasks/chrome-*.json"
  },
  "browser_router": {
    "description": "Tier selection for browsing tasks — runs on haiku",
    "model": "claude-haiku-3-5",
    "allowed_tools": [],
    "max_tokens": 512,
    "output_format": "json"
  }
}
```

---

## 9. Integration Points

### Orchestrator Prompt Addition

Add to `orchestrator_prompt.md`:

```markdown
## BrowseIntent Handling

When the user asks for any web browsing, scraping, navigation, or site interaction:

1. Dispatch `browser_router` with the task description (haiku model, fast).
2. Read the router's JSON output.
3. If `tier == 1` and `spawn_session == false`:
   - Call WebFetch directly with the URL.
   - Return result to user.
4. If `tier == 2` and `spawn_session == true`:
   - Create `.openclaw/tasks/browse-{ts}.json` with `task_for_session`.
   - Dispatch `browser_skill` session with `browser` agent profile.
   - Monitor task file for completion.
   - Read result from `.openclaw/tasks/browse-{ts}-result.json`.
   - If result status is `"escalated_to_chrome"`:
     - Dispatch `chrome_skill` session with `chrome` profile.
     - Monitor `.openclaw/tasks/chrome-{ts}-result.json` for completion.
     - Merge chrome result into final response.
5. If `tier == 3`:
   - Call Chrome DevTools MCP tools directly (they are available in this session).
6. If `tier == 4`:
   - Create `.openclaw/tasks/chrome-{ts}.json`.
   - Dispatch `chrome_skill` session.
   - Return result to user.

## Auth Escalation Monitor

Every 5 seconds (or on file-change event), check browser task files for
`"status": "escalated_to_chrome"`. When detected, auto-dispatch chrome_skill
without waiting for user input.
```

### Task File Schema

All browser tasks use:

```json
{
  "task_id": "browse-{unix_timestamp}",
  "tier": 1 | 2 | 3 | 4,
  "goal": "Human-readable task description",
  "start_url": "https://...",
  "status": "pending | running | complete | partial | escalated_to_chrome | failed | auth_required",
  "created_at": "ISO8601",
  "completed_at": "ISO8601 or null"
}
```

---

## 10. Testing Plan

### Tier 1 Test

```bash
# Should use WebFetch, no playwright spawn
openclaw route-task "Get the title tag of https://httpbin.org"
# Expected: {"tier": 1, "spawn_session": false}

# Direct fetch
openclaw webfetch https://httpbin.org/html
# Expected: HTML content returned, no browser process spawned
```

### Tier 2 Test

```bash
# Should spawn browser session
echo '{
  "task_id": "browse-test-001",
  "tier": 2,
  "goal": "Go to https://quotes.toscrape.com and extract the first 5 quotes",
  "start_url": "https://quotes.toscrape.com",
  "max_pages": 1,
  "output_format": "json_array"
}' > .openclaw/tasks/browse-test-001.json

openclaw run --skill browser_skill --task browse-test-001 --profile browser

cat .openclaw/tasks/browse-test-001-result.json
# Expected: {"status": "complete", "result": [{"text": "...", "author": "..."}]}
```

### Auth Escalation Test

```bash
# Create a task that points to a login-walled page
echo '{
  "task_id": "browse-test-002",
  "tier": 2,
  "goal": "Get my GitHub notifications",
  "start_url": "https://github.com/notifications",
  "max_pages": 1
}' > .openclaw/tasks/browse-test-002.json

openclaw run --skill browser_skill --task browse-test-002 --profile browser

# Should detect login wall and escalate
cat .openclaw/tasks/browse-test-002.json | python -m json.tool | grep status
# Expected: "status": "escalated_to_chrome"

# Verify escalation task was created
ls .openclaw/tasks/chrome-*
# Expected: chrome-browse-test-002.json exists
```

### Router Test

```python
# tests/test_browser_router.py
# Each of these should route to the correct tier

TIER_1_TASKS = [
    "Get the text content of https://httpbin.org/html",
    "What is the title of https://example.com?",
    "Read the landing page copy from https://stripe.com",
]

TIER_2_TASKS = [
    "Scrape all job postings from https://jobs.example.com including pagination",
    "Fill out the contact form at https://example.com/contact with test data",
    "Navigate to https://books.toscrape.com and collect all book titles",
]

TIER_4_TASKS = [
    "Check my GitHub pull requests",
    "Read my Gmail inbox",
    "Post a message to my Slack workspace",
    "View my Notion workspace pages",
]
```

---

## 11. Example Usage

### Scenario: Scrape public data across multiple pages

**User**: `/browse scrape all Python job postings from remoteok.com, get title + salary + company`

**Router decision**:
```json
{
  "tier": 2,
  "tool": "playwright-cli",
  "spawn_session": true,
  "rationale": "Requires navigating a paginated list and extracting structured data.",
  "task_for_session": {
    "goal": "Scrape Python job postings: title, salary, company",
    "start_url": "https://remoteok.com/remote-python-jobs",
    "max_pages": 5,
    "output_format": "json_array"
  }
}
```

**Browser skill executes** (in its own session):
```
Step 1: npx playwright-cli open https://remoteok.com/remote-python-jobs --snapshot
Step 2: Extract job rows from snapshot (12 jobs visible)
Step 3: npx playwright-cli click "button:has-text('Load more')" → snapshot
Step 4: Extract additional 12 jobs
... (continues up to max_pages)
Step 8: Write result — 47 jobs collected
```

**Result written** to `.openclaw/tasks/browse-{ts}-result.json`:
```json
{
  "status": "complete",
  "steps_taken": 8,
  "result": [
    {"title": "Senior Python Developer", "company": "Acme Corp", "salary": "$120k-$150k"},
    ...
  ]
}
```

**Orchestrator** reads result and surfaces to user. No intermediate snapshots appear in the main context.

### Scenario: Auth escalation mid-workflow

**User**: `/browse get my starred repositories on GitHub`

**Router**: Tier 2 (starts as Tier 2 since it looks like a public page).

**Browser skill Step 1**: `npx playwright-cli open https://github.com/stars --snapshot`

**Browser skill detects**: snapshot contains "Sign in" form — login wall.

**Browser skill escalates**: writes `chrome-{ts}.json` task file, sets status `"escalated_to_chrome"`.

**Orchestrator auto-dispatches** `chrome_skill`.

**Chrome skill Step 1**: `mcp__chrome-devtools__navigate_page("https://github.com/stars")`.

**Chrome skill Step 2**: Screenshot confirms user is logged in (user was already authenticated in Chrome).

**Chrome skill Step 3**: `mcp__chrome-devtools__evaluate_script("Array.from(document.querySelectorAll('h3 a')).map(a => ({name: a.textContent, url: a.href}))")` → extracts starred repo list.

**Result merged** and returned to user. Total user interaction: zero.

# Global Orchestration (Harness-Grade)

## Commands
- `/go [task]` — Full autonomous pipeline: intake → wheel-scout gate → hydrate → build/forge/skill → test → checkpoint
- `/browse [task/url]` — Spawn autonomous browser agent for multi-step web interaction (see Browser Automation below)
- `/chrome [task]` — Authenticated browsing via Claude in Chrome subprocess (see Browser Automation below)
- `/prime` — Context-prime current project (repo map, activity, memory)
- `/intake` — Pre-swarm project scan: stack, conventions, tools, memory state → ai/supervisor/intake.json
- `/forge <tool> [url]` — Auto-generate MCP server from API docs (auto-vets generated package)
- `/skills [search]` — List/search installed skills and triggers
- `/checkpoint` — Save session state to ai/memory/ (WORKING_MEMORY.md + DECISIONS.md)
- `/vet <path>` — Security-scan a directory (MCP server, tool, or package) before approving for use
- `/audit [filters]` — Query and analyze the JSONL audit log (filter by agent, tool, action class, time)

## Agents
| Agent | Model | Role |
|-------|-------|------|
| supervisor | default | Deep-chaining orchestrator: gates, hydration, allowlists, budget, memory |
| wheel-scout | sonnet | Hard gate: landscape research (≥3 solutions) before building. Read-only. |
| researcher | sonnet | Deep research + deliberation: URL/topic → structured tool recommendations |
| context-hydrator | haiku | Pre-spawn: builds minimal context pack per-agent (20-40 lines) |
| skill-router | haiku | Fast skill selection from installed plugins (metadata only) |
| tool-broker | haiku | Per-agent allowlists, meta-tool pattern, gateway routing, security, **action classification** |
| implementer | sonnet | Ralph-loop builder: implement → test → fix → repeat (max N iterations). Never single-pass. |
| memory-scribe | default | Session checkpoints: WORKING_MEMORY.md + DECISIONS.md |
| forger | sonnet | Autonomous MCP server generator: API docs → installable package |
| browser | default | Autonomous browser agent: multi-step web interaction via playwright-cli |
| chrome | default | Authenticated browser via claude --chrome -p. Subprocess with user logged-in sessions. |
| vet-scanner | sonnet | **Security gate (Gate A)**: 7-scanner pipeline with graceful degradation, PASS/WARN/FAIL verdicts |
| test-writer | sonnet | **Parallel test sidecar**: detects framework, writes tests alongside implementation |
| log-monitor | sonnet | **Dev server anomaly detection**: watches logs for errors, regressions, resource spikes |

## Security Pipeline

### Tool Vetting (Gate A)
Before any new MCP server or tool is approved, `/vet` runs up to 7 scanners:

| Scanner | Type | Checks |
|---------|------|--------|
| Trivy | External | Vulnerabilities + SBOM (CycloneDX) |
| Gitleaks | External | Hardcoded secrets |
| ClamAV | External | Malware |
| npm audit | External | Node.js dependency vulnerabilities |
| pip-audit | External | Python dependency vulnerabilities |
| Semgrep | External | SAST (code patterns) |
| Prompt Injection | Built-in | 7 regex patterns for injection signals |

**Graceful degradation**: Missing scanners are skipped, not fatal. Prompt injection scanner always runs.

**Policy thresholds** (plugins/vetting-policy.json):
- max_critical: 0, max_high: 2, max_medium: 10, max_secrets: 0
- auto_reject_on_malware: true, auto_reject_on_critical: true

**Verdict flow**: FAIL (auto-reject) → WARN (user decides) → PASS (auto-approve)

### Audit Logging
Every tool call is logged to ~/.claude/audit/tool-calls.jsonl via the trace-post.sh hook:
- Fields: timestamp, session_id, project, cwd, tool, action_class, agent_role, args_hash (SHA256), error status
- Log rotation: probabilistic (1-in-50 chance per write), max 10MB, 5 rotated files
- Query via /audit: filter by agent, tool, action class, time range, errors

### Action Classification
The tool-broker classifies every tool call into one of 5 action classes:

| Class | Tools/Patterns | Gate |
|-------|---------------|------|
| **read** | Read, Glob, Grep, WebSearch, WebFetch | Open |
| **write** | Write, Edit, NotebookEdit | Role-checked |
| **exec** | Bash, Agent | Role-checked + keyword scan |
| **network** | WebFetch, WebSearch, mcp__* | Role-checked |
| **credential** | Detected via keyword scoring in args | Always flagged |

**Dangerous action keywords** (scored 0.0-1.0): rm -rf, git reset --hard, git push --force, drop table, curl | sh, etc.
Actions scoring >0.5 are dual-logged and may be denied per agent allowlist.

**Per-agent allowlists** (plugins/action-policy.json): 14 agent roles with specific tool permissions.

## Browser Automation

Four tools available — pick by task type:

| Tool | Best for | Context cost | Auth? | Headless/CI? |
|------|----------|-------------|-------|-------------|
| **WebFetch** | Read a single page text content | Minimal | No | Yes |
| **playwright-cli** (via /browse or browser agent) | Multi-step interaction: click, fill, navigate, scrape, test flows | Low (compact snapshots) | Via state-save/load | Yes |
| **Chrome DevTools MCP** (chrome-devtools) | Performance profiling, Core Web Vitals, deep network/console inspection, DOM debugging | ~9% for tool defs | No (separate Chrome) | Yes |
| **Claude in Chrome** (claude --chrome) | Authenticated workflows on user actual browser (logged-in sites, cookies, open tabs) | ~7.7% | Yes (user sessions) | No |

### Decision flow

1. **Just need page text?** → WebFetch. No browser needed.
2. **Need to click/fill/navigate/scrape (public)?** → playwright-cli via /browse (user-facing) or browser agent (internal).
3. **Debugging perf, network, console errors?** → Chrome DevTools MCP tools (mcp__chrome-devtools__*).
4. **Need logged-in access (Gmail, GitHub dashboard, Notion)?** → /chrome (spawns claude --chrome -p subprocess).
5. **Auth wall hit mid-workflow?** → Escalate: browser agent runs claude --chrome --max-budget-usd 0.50 -p "task".
6. **Cross-browser testing?** → playwright-cli with --browser=firefox / --browser=webkit.

### Entry points

| Entry point | Type | When to use |
|-------------|------|-------------|
| /browse [task] | User-facing skill | User asks to browse, scrape, test a web UI, or interact with a public website. Spawns a sub-agent with playwright-cli. |
| /chrome [task] | User-facing skill | User asks to interact with a logged-in site or needs their auth cookies. Spawns claude --chrome -p subprocess. |
| browser agent | Internal | Mid-workflow browsing by supervisor/researcher/other agents. Spawns via Agent tool with playwright-cli context. |
| chrome agent | Internal | Mid-workflow auth escalation. Agent runs claude --chrome --max-budget-usd 0.50 -p "task" via Bash when auth is required. |

### Auth escalation pattern

When a browser agent (playwright-cli) encounters a login wall:
1. Do NOT guess credentials or attempt to bypass auth
2. Escalate by running: claude --chrome --max-budget-usd 0.50 -p "task requiring auth"
3. Always include --max-budget-usd to cap costs (subprocess is a full Claude session)
4. Incorporate the subprocess result back into the workflow

### When NOT to spawn an agent

- Single quick playwright-cli command (one screenshot, one page open) → run directly via Bash
- Chrome DevTools profiling → call MCP tools directly (they return targeted data, not full page trees)
- WebFetch → always direct, never needs an agent

**Key principle:** Any task requiring 3+ browser commands should go through a sub-agent to protect main context from snapshot noise. Auth-required tasks always go through /chrome or the chrome agent pattern.

**Hard rule:** NEVER use Microsoft Edge (--browser=msedge). Always use Chrome, Firefox, or WebKit.

## Harness Patterns
- **Wheel-Scout Gate**: Build tasks require landscape report FIRST (≥3 existing solutions evaluated). Adopt > Extend > Build.
- **Context Hydration**: Every worker gets a 20-40 line context pack compiled by haiku agent BEFORE spawn.
- **Per-Agent Allowlists**: Research=read-only, Implementer=read-write, Tester=read+bash, Scanner=read-only.
- **Meta-Tool Pattern**: Agents get tool descriptions (~50 tokens), not full schemas (~5000). 80% savings.
- **Memory Checkpoints**: /go auto-checkpoints at end. Manual via /checkpoint. Captures state + decisions.
- **Budget Awareness**: Haiku for scanning, sonnet for coding, opus only when explicitly needed.
- **Ralph Loop**: Implementation agents iterate (implement → test → fix → retest) instead of single-pass. Max iterations: 2 (trivial), 5 (standard), 7 (complex). Failures are data. PARTIAL results can chain to a second implementer.
- **Deep Chaining**: Subagents spawn sub-subagents. Slash command logic embedded in agent prompts.
- **Wave Execution**: Multi-step requests decomposed into dependency graph → topologically sorted into waves. Tasks in the same wave run as parallel agents (worktree-isolated). Cross-wave data flows forward (wave N outputs → wave N+1 context).
- **Sidecar Agents**: Non-blocking background agents for supplementary work (docs, changelog, research). Spawned with run_in_background: true. Max 3 concurrent. Failures non-fatal. Results folded in at Phase 6.
- **Security Pipeline**: Every new tool/MCP server goes through Gate A (vet-scanner) before approval. Audit logging captures all tool calls. Action classification gates dangerous operations.

## Go Harness Binary (v2)
The harness Go binary replaces bash hooks and prompt-encoded runtime logic with a compiled MCP server:

```
harness serve              # MCP server mode (Claude Code connects via stdio)
harness vet <path>         # Run security vetting pipeline
harness audit [--tail]     # Query/stream audit log
harness classify <tool>    # Classify action by risk level
harness route <task>       # Route task to best skills
harness config validate    # Validate harness configuration
```

When installed, add to ~/.claude/settings.json mcpServers:
```json
{"harness": {"command": "harness", "args": ["serve"]}}
```

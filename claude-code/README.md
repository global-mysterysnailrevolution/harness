# Claude Code Harness

Claude Code-native orchestration system with subagent spawning, deep chaining, and browser automation.

## Installation

Copy the contents of this directory into `~/.claude/`:

```bash
cp -r claude-code/agents/* ~/.claude/agents/
cp -r claude-code/commands/* ~/.claude/commands/
cp -r claude-code/skills/* ~/.claude/skills/
cp -r claude-code/plugins/* ~/.claude/plugins/
cp -r claude-code/hooks/* ~/.claude/hooks/
cp claude-code/CLAUDE.md ~/.claude/CLAUDE.md
```

## Commands

| Command | Description |
|---------|-------------|
| `/go [task]` | Full autonomous pipeline: intake -> wheel-scout -> hydrate -> build -> test -> checkpoint |
| `/browse [task/url]` | Autonomous browser agent for multi-step web interaction |
| `/chrome [task]` | Authenticated browsing via Claude in Chrome subprocess |
| `/prime` | Context-prime current project (repo map, activity, memory) |
| `/intake` | Pre-swarm project scan: stack, conventions, tools, memory state |
| `/forge <tool> [url]` | Auto-generate MCP server from API docs |
| `/skills [search]` | List/search installed skills and triggers |
| `/checkpoint` | Save session state to durable memory |

## Agents

| Agent | Model | Role |
|-------|-------|------|
| supervisor | default | Deep-chaining orchestrator: gates, hydration, allowlists, budget, memory |
| wheel-scout | sonnet | Hard gate: landscape research (>=3 solutions) before building. Read-only. |
| researcher | sonnet | Deep research + deliberation: URL/topic -> structured tool recommendations |
| context-hydrator | haiku | Pre-spawn: builds minimal context pack per-agent (20-40 lines) |
| skill-router | haiku | Fast skill selection from installed plugins (metadata only) |
| tool-broker | haiku | Per-agent allowlists, meta-tool pattern, gateway routing, security |
| implementer | sonnet | Ralph-loop builder: implement -> test -> fix -> repeat (max N iterations) |
| memory-scribe | default | Session checkpoints: WORKING_MEMORY.md + DECISIONS.md |
| forger | sonnet | Autonomous MCP server generator: API docs -> installable package |

## Skills

| Skill | Description |
|-------|-------------|
| browse | Autonomous browser agent via playwright-cli (public sites) |
| chrome | Authenticated browser via `claude --chrome` (logged-in sites) |
| playwright-cli | Headless browser automation with session mgmt, tracing, etc. |

## Harness Patterns

- **Wheel-Scout Gate**: Build tasks require landscape report FIRST (>=3 existing solutions). Adopt > Extend > Build.
- **Context Hydration**: Every worker gets a 20-40 line context pack compiled by haiku BEFORE spawn.
- **Per-Agent Allowlists**: Research=read-only, Implementer=read-write, Tester=read+bash.
- **Meta-Tool Pattern**: Agents get tool descriptions (~50 tokens), not full schemas (~5000). 80% savings.
- **Ralph Loop**: Implementation iterates (implement -> test -> fix -> retest) instead of single-pass.
- **Deep Chaining**: Subagents spawn sub-subagents (3+ levels).
- **Wave Execution**: Dependency graph -> topo-sort -> parallel waves with worktree isolation.
- **Sidecar Agents**: Non-blocking background agents for supplementary work (max 3 concurrent).
- **Budget Awareness**: Haiku for scanning, sonnet for coding, opus only when explicitly needed.

## Browser Automation (4-tier)

1. **WebFetch** - Just need page text? No browser needed.
2. **playwright-cli** (`/browse`) - Click/fill/navigate/scrape public sites.
3. **Chrome DevTools MCP** - Performance profiling, network/console inspection.
4. **Claude in Chrome** (`/chrome`) - Authenticated workflows on user's actual browser.

Auth escalation: browser agent auto-escalates to `claude --chrome` when hitting login walls.

## Unique to Claude Code (vs OpenClaw)

- Native Agent tool with model selection, background execution, worktree isolation
- Deep chaining (3+ level subagent spawning)
- Wave execution (parallel worktree-isolated task execution)
- 4-tier browser automation with auth escalation
- Forger agent (complete MCP server generation from any API docs)
- Skill Router (haiku-based fast capability matching)
- Ralph Loop (iterative implement/test/fix, max 2/5/7 iterations by complexity)
- Plugin marketplace system (blocklist + known marketplaces)

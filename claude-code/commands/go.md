---
name: go
description: >
  Full autonomous orchestrator with harness-grade rigor. Enforces wheel-scout
  gate (landscape research before building), budget tracking, per-agent context
  hydration, memory checkpoints, and deep chaining. One command does everything.
---

# Orchestrated Workflow: /go

You are a fully autonomous orchestrator with harness-grade discipline.
The user invoked `/go` and expects you to handle EVERYTHING without babysitting.

## Phase 0: Project Intake (first time only)

If no `ai/supervisor/intake.json` exists in the current project, do a FAST intake:
1. What is this project? (detect from package.json/README/CLAUDE.md)
2. What stack? (detect from config files)
3. What test framework? (detect from package.json scripts or config)
4. Are there existing memory files? (check ai/memory/, .claude/projects/)

Write a minimal `ai/supervisor/intake.json`:
```json
{
  "project": "[name]",
  "stack": "[detected]",
  "test_cmd": "[detected]",
  "has_memory": true/false,
  "intake_time": "[ISO timestamp]"
}
```

Skip this if intake.json already exists. Skip this if not in a project directory.

## Phase 1: Task Assessment & Decomposition

Parse `$ARGUMENTS` (or most recent user message). Two steps:

### 1a: Classify the task

| Category | Signals | Pipeline | Wheel-Scout Required? |
|----------|---------|----------|----------------------|
| **discover** | URL, "research tools", "integrate" | Research → Deliberate → Forge/Skill → Integrate | NO |
| **build** | "implement", "create", "add feature" | **GATE** → Prime → Plan → Build → Test | **YES** |
| **fix** | "bug", "error", "broken", "debug" | Prime → Diagnose → Fix → Test | NO |
| **research** | "how", "explain", "compare" | Fan-out research → Synthesize | NO |
| **review** | "review", "audit", "check" | Parallel audit → Synthesize | NO |
| **refactor** | "clean up", "optimize" | Prime → Plan → Refactor → Test | NO |

**Trivial task shortcut**: If the task is a one-file fix or obvious change,
skip ALL orchestration and just do it directly. Don't over-engineer.

### 1b: Parallel Decomposition (multi-step requests)

If the user request contains MULTIPLE distinct sub-tasks, decompose them:

1. **Extract sub-tasks**: Break the request into discrete units of work
2. **Build dependency graph**: For each pair of sub-tasks, ask:
   - Does sub-task B need OUTPUT from sub-task A? → B depends on A (sequential)
   - Are they independent? → Can run in parallel
3. **Group into waves**: Topologically sort the dependency graph into execution waves.
   Tasks in the same wave run as parallel agents. Waves execute sequentially.

```
Example: "Add a sensor API endpoint, write tests for it, and update the dashboard to show sensor data"

Sub-tasks:
  A: Add sensor API endpoint
  B: Write tests for the endpoint  (depends on A — needs the endpoint to exist)
  C: Update dashboard to show data (depends on A — needs the API contract)

Dependency graph:
  A → B
  A → C

Execution waves:
  Wave 1: [A]           ← single agent
  Wave 2: [B, C]        ← two parallel agents (both need A's output, not each other's)
```

```
Example: "Fix the login bug, add dark mode toggle, and update the README"

Sub-tasks:
  A: Fix login bug
  B: Add dark mode toggle
  C: Update README

Dependency graph: (none — all independent)

Execution waves:
  Wave 1: [A, B, C]     ← three parallel agents
```

**Output of Phase 1**: A decomposition plan:
```
TASK_PLAN:
  - wave_1: [sub-task descriptions...]    ← spawn as parallel agents
  - wave_2: [sub-task descriptions...]    ← spawn after wave_1 completes
  - sidecars: [any async side-tasks]      ← spawn as background agents
```

If there's only ONE sub-task, skip decomposition and proceed normally.

## Phase 2: Wheel-Scout Gate (BUILD tasks only)

**This is a HARD GATE. Do not skip it for build tasks.**

Before any implementation, spawn a research agent to produce a landscape report.
The agent must find and evaluate existing solutions BEFORE we build anything.

Spawn Agent(general-purpose, model: sonnet):
```
You are a wheel-scout. Before we build anything, research what already exists.

Task: [the user's build request]

Do this:
1. WebSearch for existing solutions (at least 3 different queries)
2. WebSearch for "[topic] library", "[topic] npm package", "[topic] github"
3. For each solution found, evaluate:
   - Does it solve the problem? (fully / partially / no)
   - Is it maintained? (last commit, stars, issues)
   - Can we adopt it directly?
   - Can we extend it?
   - Or must we build from scratch?

Return a landscape report in EXACTLY this format:

## Landscape Report: [topic]

### Existing Solutions Found

| # | Solution | Solves Problem? | Maintained? | Recommendation |
|---|----------|----------------|-------------|----------------|
| 1 | [name + URL] | Fully/Partially/No | Yes/No | Adopt/Extend/Skip |
| 2 | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... |

### Recommended Path
- [ ] ADOPT: [solution] — it already does what we need
- [ ] EXTEND: [solution] — it's close, we add [what's missing]
- [ ] BUILD: [justification why nothing existing works]

### Build Justification (required if recommending BUILD)
[Why can't we use or extend existing solutions?]
```

**Gate enforcement:**
- If the report recommends ADOPT → tell the user, install/integrate the existing solution
- If EXTEND → tell the user, fork/extend the existing solution
- If BUILD → proceed with building, but reference the landscape report in the plan
- If fewer than 3 solutions researched → send the scout back to find more

Save the report to `ai/research/landscape-[topic-slug].md`.

## Phase 3: Parallel Bootstrap (spawn ALL simultaneously)

```
Agent A (skill-router, haiku): Full capability scan
  → Scans ALL sources: plugin SKILL.md files, global commands, project commands,
    built-in skills (loop, simplify, claude-api, checkpoint, etc.),
    cron/scheduling tools, and MCP servers
  → Returns structured output:
    SKILLS: [skill-1], [skill-2]
    TOOLS: [CronCreate], [etc.]
    COMMANDS: [/forge]
    INVOKE_VIA: skill:name | tool:CronCreate | command:/name
    REASON: one line

Agent B (haiku, Explore): Context prime (skip if not in a project)
  → git log, git diff, CLAUDE.md, README, memory files
  → Return 10-line context summary

Agent C (sonnet, general-purpose): Context hydration (only for build/fix/refactor)
  → Analyze what the task needs (language, framework, patterns)
  → Search for relevant docs/examples in the codebase
  → Read the most relevant 3-5 files
  → Return: key files, patterns to follow, constraints discovered

Agent D (sonnet, general-purpose): Deep research (only for discover/research)
  → If URL: WebFetch + extract tools/APIs/services
  → If topic: WebSearch with multiple queries
  → Return structured findings
```

**Per-wave hydration**: If Phase 1b produced multiple waves, hydrate context
for ALL sub-tasks in wave 1 during bootstrap. Hydration for later waves happens
just before that wave executes (since earlier wave outputs inform context).

## Phase 4: Activate Selected Capabilities

The skill-router returned WHAT to use and HOW to invoke each one. Now activate them:

### Invoke via Skill tool (for built-in + plugin skills)
If the router selected skills like `loop`, `simplify`, `claude-api`, `checkpoint`:
- Use the **Skill** tool to invoke them: `Skill(skill: "loop", args: "5m ...")`
- These run in the MAIN context and enrich it with domain knowledge
- Example: if task is "build a Claude-powered agent", invoke `Skill(skill: "claude-api")`
  to load Anthropic SDK best practices before writing code

### Invoke via CronCreate (for scheduling/monitoring needs)
If the router selected `CronCreate`:
- Set up cron jobs for recurring aspects of the task
- Example: after deploying, `CronCreate("*/5 * * * *", "check deploy health")`
- Example: `CronCreate("7 * * * *", "run test suite and report regressions")`

### Invoke via command logic (for /forge, /intake, etc.)
If the router selected a command like `/forge`:
- Embed that command's logic into the appropriate subagent's prompt
- Subagents can't call slash commands, but they can do the same work

### Deliberation for "discover" tasks
For EACH tool/API/service found by Agent D:
```
Has REST API endpoints?       → Forge MCP server (embed forge logic in subagent)
Is a workflow/convention?     → Create skill (write ~/.claude/commands/{name}.md)
Is a CLI tool?                → Document in CLAUDE.md
Is a library/SDK?             → Install as dependency
Already have a plugin for it? → Skip
Not integratable?             → Note and skip
```

### Deliberation for "build" tasks (post wheel-scout)
- If ADOPT: install the existing solution
- If EXTEND: clone/fork + modify
- If BUILD: design implementation plan using hydrated context

### Tool broker check
Before spawning any worker, check what tools it needs:
- What MCP servers are available? (check .mcp.json + settings)
- What plugins/skills are relevant? (from skill-router results)
- Build a per-agent tool allowlist: only give each agent the tools it needs

## Phase 5: Autonomous Execution

### 5a: MCP Server Forging
Spawn Agent(general-purpose, sonnet) with embedded forge logic:
- Fetch API docs → extract endpoints → design MCP tools
- Create mcp-servers/{tool}-mcp/ package (FastMCP + httpx + pydantic)
- Validate syntax → generate .mcp.json config entry
- Return files + config

### 5b: Skill Creation
Spawn Agent(general-purpose, sonnet) with embedded skill-creator logic:
- Research what the skill should do
- Check for duplicates (Glob existing skills)
- Write ~/.claude/commands/{name}.md with frontmatter + instructions
- Return skill name + triggers

### 5c: Build/Fix/Refactor (Ralph Loop + Wave Execution)

Implementation agents work in **iterative loops**, not single passes.
They implement, test, read failures, fix, and retest — repeating until green.

#### Single sub-task (no decomposition)
```
Agent(Plan): Design implementation using hydrated context + landscape report
  → Define: files to change, test command, success criteria
  → Returns: PLAN with fields: files_to_create, files_to_modify, test_command

Agent(implementer): Ralph loop execution              -+  spawn SIMULTANEOUSLY
Agent(test-writer, background): write tests           -+  (run_in_background: true)

Implementer:
  → MAX_ITERATIONS: 2 (trivial) / 5 (standard) / 7 (complex)
  → TEST_COMMAND: from intake.json or plan
  → SUCCESS_CRITERIA: specific measurable condition
  → Loop: implement → test → analyze → fix → retest
  → Returns: implementation report (DONE/PARTIAL/BLOCKED)
  → NOTE: a test-writer sidecar is running in parallel.
     Do NOT write test files unless the sidecar is reported BLOCKED at Phase 6.
     Focus on implementing source code and making existing tests pass.

Test-writer sidecar (run_in_background: true):
  → Context pack includes: FRAMEWORK, SOURCE_FILES (from plan),
     TEST_DIR, TEST_CMD, PROJECT_ROOT, path to one existing test file
  → Reads new/modified source files (waits up to 30s if not yet written)
  → Studies existing test patterns from the example file
  → Writes matching test files to the correct test directory
  → Runs tests, self-corrects authoring errors (up to 3 retries per file)
  → Marks as skip (not deletes) any test that reveals a source bug
  → Writes ai/tests/TEST_PLAN.md and ai/tests/COVERAGE_NOTES.md
  → Returns: test writer report (DONE/PARTIAL/BLOCKED)
  → If sidecar fails or BLOCKED: non-fatal, noted in Phase 6

If implementer returns PARTIAL/BLOCKED:
  → BLOCKED on external dep → AskUserQuestion to escalate
  → PARTIAL with failures → spawn second implementer with failure context (chained Ralph)
  → PARTIAL but close → fix remaining directly
```
#### Multi sub-task (wave execution from Phase 1b)

Execute the decomposition plan wave by wave:

```
For each wave in TASK_PLAN:

  1. PRE-WAVE: Hydrate context for all sub-tasks in this wave
     → If wave > 1, include outputs/reports from previous waves in the context
     → Spawn parallel context-hydrators (one per sub-task) if they need different context

  2. EXECUTE WAVE: Spawn all sub-tasks in this wave as PARALLEL agents
     → Each build sub-task gets its own implementer (Ralph loop)
     → Each build sub-task also gets a test-writer sidecar (background)
     → Each runs in isolation (worktree for build tasks to avoid conflicts)
     → All launched in a SINGLE message (parallel Agent calls)

     Agent(implementer, worktree): sub-task A               -+
     Agent(test-writer, background): tests for sub-task A   |   parallel (same wave)
     Agent(implementer, worktree): sub-task B               |
     Agent(test-writer, background): tests for sub-task B   -+

     Budget note: 2 test-writer sidecars per wave is within the 3-sidecar budget.
     If a wave has 2+ implementers AND Phase 5e sidecars are also running,
     defer non-critical Phase 5e sidecars to after the wave completes.
  3. POST-WAVE: Collect all reports
     → Merge worktrees if applicable
     → Compile outputs needed by the next wave
     → If any agent returned PARTIAL/BLOCKED, handle before next wave:
       - BLOCKED → escalate or skip dependent sub-tasks
       - PARTIAL → chain second implementer with failure context
```

**Cross-wave data flow**: When wave N+1 depends on wave N outputs, the
orchestrator extracts the relevant artifacts (file paths, API contracts,
type definitions, test results) and injects them into wave N+1's context packs.

```
Example execution:
  Wave 1: Agent(implementer, worktree): "Add sensor API endpoint"
    → Returns: DONE, created /api/sensors/* routes, types in sensor.ts

  Wave 2 (parallel, both receive wave 1 context):
    Agent(implementer, worktree): "Write tests for sensor API"
      → Context includes: route paths, type definitions from wave 1
    Agent(implementer, worktree): "Add sensor dashboard page"
      → Context includes: API contract, response shapes from wave 1
```

**Embed this in every implementer agent's prompt:**
```
You work in Ralph loop mode. After implementing, you MUST run tests.
If tests fail, analyze the output, make targeted fixes, and retest.
Repeat up to MAX_ITERATIONS times. Never claim success without green tests.
Failures are data — each iteration gets you closer.
```

### 5e: Sidecar Agents (async side-tasks)

Sidecars are background agents spawned for work that is **useful but not blocking**.
They run asynchronously alongside the main pipeline and report back when done.

**When to spawn a sidecar:**
- The user says "also", "btw", "while you're at it", "and separately"
- A sub-task is clearly independent AND non-critical to the main flow
- You discover something worth investigating but don't want to block the pipeline
- Documentation, changelog, or memory updates that can happen in parallel

**How sidecars work:**
```
1. Spawn with run_in_background: true
   Agent(general-purpose, background): "Update changelog with sensor API changes"

2. Main pipeline continues WITHOUT waiting for the sidecar

3. When the sidecar completes, you receive a notification with its output

4. Fold sidecar results into the final summary (Phase 6)
   → If the sidecar produced code changes, review them before integrating
   → If it produced research, incorporate findings into the report
```

**Sidecar rules:**
- Sidecars MUST NOT modify files that the main pipeline is actively editing
  (use worktree isolation if there's any risk of conflict)
- Sidecars inherit the same context hydration as their wave
- If a sidecar fails, it does NOT block the main pipeline
- Budget: sidecars should be lightweight (haiku/sonnet, not opus)
- Max 3 concurrent sidecars to avoid budget blowout
- A build task is executing -- test-writer sidecars are auto-spawned in Phase 5c alongside
  every implementer. You do not spawn them manually here; they are part of the build pattern.

### 5e-ii: Log Monitor Sidecar (Automatic Dev Server Watcher)

**Trigger condition**: Spawn automatically when ALL of the following are true:
1. Task type is `build` or `fix` (not research/review/discover)
2. Any of these signals:
   - `intake.json` has a non-empty `stack.dev_cmd`
   - Task touches server entrypoints (app.py, server.ts, main.go, index.ts)
   - Task touches framework config (vite.config.*, next.config.*, webpack.config.*)
   - Task description contains runtime/server/crash/browser/frontend/deploy keywords

**Spawn**:
```
Agent(log-monitor, sonnet, run_in_background: true):
  context:
    PROJECT_ROOT: [cwd]
    DEV_CMD: [from intake.json or "auto-detect"]
    DURATION_SECONDS: [30 for vite/next, 60 for django/rails, 120 for java, 45 default]
    PLATFORM: [detected platform]
  tools: [Bash, Read, Write, Glob, Grep]
```

**Important**: The log-monitor does NOT need to complete before the implementer
finishes. It runs independently. Its output (ai/context/LOG_FINDINGS.md) is
consumed at Phase 6 during integration.

**At Phase 6**: If LOG_FINDINGS.md has `Status: CRITICAL_FINDINGS`, spawn a
targeted fix pass (implementer, MAX_ITERATIONS: 3) with the findings as input.
This is the "runtime fix loop" -- separate from the test-fix loop.
## Phase 6: Integration & Memory

1. **Collect sidecar results:** If any background sidecars are still running, wait
   for them (or note they're pending). Fold completed sidecar outputs into the report.
2. **If MCP servers forged:** Update .mcp.json, note env vars needed
3. **If skills created:** Verify files, list new commands
4. **If code written:** Run tests, summarize changes. Fold in test-writer sidecar report:
   → List test files written and test pass counts
   → If test-writer DONE: include "Tests: N/N passing -- {test file(s)}" in summary
   → If test-writer PARTIAL: note gaps and any skipped (source-bug) tests explicitly
   → If test-writer surfaced bugs: flag them: "Test-writer surfaced N potential source bugs:
      {description} in {source file}. Review before merging."
   → If test-writer failed or did not run: note "Test coverage: not generated (sidecar failed)"
      and suggest: "Run /go 'write tests for {file}' as a follow-up"
   → Check ai/context/LOG_FINDINGS.md if log-monitor sidecar ran:
      - Status CRITICAL_FINDINGS: spawn targeted fix pass (implementer, MAX_ITERATIONS: 3)
        with findings as context: "The log-monitor found critical runtime errors.
        Read ai/context/LOG_FINDINGS.md and fix the critical runtime errors."
      - Status WARNINGS_ONLY: include warnings in summary, do NOT re-run implementer
      - Status CLEAN or SKIPPED: note "Runtime log: clean" or "Runtime log: not monitored" 
5. **If multi-wave execution:** Compile per-wave reports into a single summary.
   Note which sub-tasks ran in parallel and which were sequential.
6. **Memory checkpoint:** Write what was done to `ai/memory/WORKING_MEMORY.md`:
   ```
   ## Session: [ISO timestamp]
   Task: [what was requested]
   Decomposition: [N sub-tasks across M waves, P sidecars] (if applicable)
   Actions: [what was done]
   Decisions: [key choices made and why]
   State: [what's left to do, if anything]
   ```

7. **Budget log:** Note approximate token usage for the workflow

8. **Present a single summary** (concise, not a wall of text):
   ```
   Done. Here's what happened:
   - Landscape: Found 3 existing solutions, recommending BUILD because [reason]
   - Built: [what was implemented]
   - Parallel: [N sub-tasks across M waves] (if applicable)
   - Sidecars: [completed/pending] (if applicable)
   - Tests: [pass/fail] -- [test files written by test-writer, if applicable]
   - Runtime log: [CRITICAL_FINDINGS (N issues) | WARNINGS_ONLY | CLEAN | SKIPPED]
   - Memory: Checkpointed to ai/memory/WORKING_MEMORY.md
   ```

## Chaining Rules

1. **Subagents CAN spawn sub-subagents.** Full tool access including Agent.
2. **Subagents CANNOT invoke slash commands.** Embed the logic in their prompts.
3. **Parallelize everything independent.** Check for real data dependencies first.
   Use Phase 1b decomposition for multi-step requests.
4. **Per-agent allowlists.** Don't give a research agent Write access. Don't give
   a scanner agent WebFetch. Match tools to the agent's role.
5. **Escalate only on genuine blockers.** Missing API key, ambiguous requirement,
   conflicting instructions. Everything else: decide and execute.
6. **Budget awareness:** Haiku for scanning (~$0.0001), sonnet for coding, opus only
   if the task explicitly requires deep reasoning.
7. **No ceremony.** Don't explain the pipeline. Report results.
8. **Wave execution is the default for multi-step tasks.** Always decompose, always
   parallelize independent work. Don't serialize what can be concurrent.
9. **Sidecars for non-blocking work.** Use `run_in_background: true` for tasks that
   are useful but shouldn't gate the main pipeline.
10. **Cross-wave context flows forward.** Each wave's outputs become the next wave's
    inputs. The orchestrator is responsible for extracting and injecting relevant
    artifacts between waves.

## Anti-Patterns

- Don't skip the wheel-scout gate for build tasks. It exists to prevent reinventing wheels.
- Don't orchestrate trivial tasks. One-file fix = just do it.
- Don't load all skills. Skill-router picks 1-3.
- Don't send full codebase to subagents. Send file paths + 2-3 line descriptions.
- Don't duplicate research. If a subagent already searched, use their results.
- Don't create both MCP + skill for the same thing. Pick one.
- Don't forget to checkpoint memory. Future sessions depend on it.

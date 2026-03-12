# Deep Chaining — OpenClaw Port

## 1. Overview

Deep Chaining is Claude Code's multi-level agent spawning model. Unlike flat
orchestration (one conductor, several workers), deep chaining allows any agent at
any level of the hierarchy to spawn further sub-agents, which can themselves spawn
agents, and so on.

Claude Code supports at least 4 levels of practical depth:

```
Level 0: Supervisor (user-facing)
Level 1: Wheel-scout, researcher, implementer, forger (spawned by supervisor)
Level 2: Test-runner, bug-fixer, sub-researcher (spawned by level-1 agents)
Level 3: Targeted fixers, micro-validators (spawned by level-2 agents)
```

Concrete examples:

```
supervisor → wheel-scout → WebSearch (3 levels)
supervisor → implementer → test-runner → bug-fixer (4 levels)
supervisor → researcher → WebFetch + sub-researcher → synthesizer (4 levels)
```

The key properties:

- **Each level has full tool access** including the `Agent` tool (which spawns the
  next level)
- **Slash command logic is embedded** in agent prompts so sub-agents can invoke
  the equivalent of slash commands without needing the user to type them
- **Context is scoped** — each agent sees only what it needs (its task, its tools,
  its context pack from the parent). It does not see the full conversation history.
- **Results bubble up** — each agent writes its results to a structured output, and
  the parent reads and integrates those results

The depth is bounded by cost and task complexity, not by architectural limits. In
practice, most tasks use 2-3 levels. 4+ levels occur only for research-heavy or
multi-phase implementation tasks.

---

## 2. Problem Statement

OpenClaw uses a flat orchestration model:

```
orchestrator_prompt.md (level 0)
  ├── Dispatches to skill-1 session (level 1)
  ├── Dispatches to skill-2 session (level 1)
  └── Dispatches to skill-3 session (level 1)
```

Level-1 sessions cannot spawn further sessions. They can call tools (Bash, Read,
Write) but cannot recursively delegate to sub-agents. This means:

1. **Complex tasks cannot be recursively decomposed.** If an implementer discovers
   mid-task that it needs specialized research, it must either do the research
   itself (context pollution) or give up (incomplete result).

2. **Research tasks are flat.** A researcher cannot delegate sub-topics to
   parallel sub-researchers. All synthesis happens in one context window.

3. **Bug-fixing is in-band.** When an implementer's code fails tests, the test
   analysis and fix happen in the same context as the original implementation.
   This accumulates noise and can cause the implementer to lose track of the
   original requirements.

4. **No slash command equivalents for sub-agents.** An implementer cannot trigger
   the equivalent of `/forge github` mid-task — it would have to implement the
   GitHub integration manually, even if a forger agent could do it better.

| Characteristic | Claude Code Deep Chaining | OpenClaw current |
|---|---|---|
| Max agent depth | 4+ levels | 1 level |
| Sub-agent spawning | Any agent can spawn sub-agents | Orchestrator only |
| Slash commands in sub-agents | Yes (embedded logic) | No |
| Context isolation per level | Yes (scoped context packs) | N/A (flat) |
| Recursive decomposition | Yes | No |

---

## 3. Source Analysis

### 3.1 The Agent Tool

Claude Code's deep chaining is powered by the `Agent` tool, which any agent can
call:

```
Agent({
  "task": "Search for the top 3 rate limiting libraries for Python FastAPI",
  "context": "We are building a production API. Need: pip-installable, maintained, docs.",
  "tools": ["WebSearch", "WebFetch", "Read"],
  "model": "claude-haiku-3-5",
  "isolation": "none"  // "worktree" for file-modifying tasks
})
```

This spawns a sub-agent with its own context window, runs it to completion, and
returns its output to the parent agent. The parent receives a structured result
and continues.

The sub-agent's context window starts fresh — it does not inherit the parent's
conversation history. It only gets what the parent explicitly passes in the `task`
and `context` fields.

### 3.2 Embedded Slash Command Logic

Sub-agents cannot type `/forge github` because they are not users — they are
agents. Instead, Claude Code embeds the logic of slash commands directly in agent
prompts. For example, the supervisor's prompt contains:

```
When you need a new MCP tool for an API, do the following:
1. Check if a relevant MCP server is already installed in .mcp.json
2. If not: spawn a forger sub-agent with the API name and docs URL
3. Wait for the forger to complete and read its config output
4. Update .mcp.json with the new server
5. Continue with the task using the new MCP tool
```

This is the `/forge` command's logic, embedded as prose instructions. The agent
follows these steps without the user having to invoke the command.

Similarly for `/browse`:
```
When you need to fetch data from a website that requires interaction:
1. Classify the task using the browser_router
2. If Tier 2 or above: spawn a browser sub-agent with the goal and start URL
3. Read the browser agent's result file when complete
4. Continue with the extracted data
```

### 3.3 Context Pack Discipline

Each agent is responsible for constructing a minimal context pack for its
sub-agents. The rule in Claude Code is: pass only what the sub-agent needs to
complete its specific task. Do not pass:
- The full conversation history
- Large file contents that the sub-agent won't use
- Other agents' outputs unless directly relevant

This discipline is what makes deep chaining practical — without it, each level
would accumulate context from all parent levels and context costs would grow
exponentially.

### 3.4 Result Bubbling

Each agent writes its results to a structured output (a file or a return value
from the `Agent` tool call). The parent reads this output and integrates it.

The integration step is explicitly part of each agent's prompt:

```
After spawning a sub-agent, read its output and:
1. Extract the specific data you needed
2. Discard the rest
3. Continue with your task
```

This keeps each level's context focused on its own work.

---

## 4. Target Architecture

OpenClaw's deep chaining port requires:

1. **`deep_chain_skill.md`** — the meta-skill that any agent can load to gain
   sub-agent spawning capability
2. **`tools/chain_dispatcher.py`** — Python tool that creates and launches a
   sub-agent session, waits for completion, and returns the result
3. **Embedded slash command logic** — prose instructions in each skill that
   describe how to trigger key sub-tasks (forge, browse, research) without the
   user's involvement
4. **Context pack builder** — part of `chain_dispatcher.py`, constructs minimal
   context for each spawned sub-agent
5. **Result reader** — the parent session reads the sub-agent's output file

### 4.1 Architecture Diagram

```
orchestrator (Level 0)
  ─ Dispatches to implementer_skill (Level 1 session)
         │
         ▼
implementer_skill (Level 1 session)
  ─ Discovers: "need GitHub API access"
  ─ Calls chain_dispatcher.py with skill=forger, task="forge github"
         │
         ▼
  chain_dispatcher.py
  ─ Creates .openclaw/tasks/chain-{parent_id}-forger-{ts}.json
  ─ Spawns forger_skill session (Level 2) with minimal context pack
  ─ Blocks (polls) for completion
  ─ Returns forger result to Level 1 session
         │
         ▼
forger_skill (Level 2 session)
  ─ Fetches GitHub API docs
  ─ Generates github-mcp package
  ─ Writes result to task file
  ─ Session exits
         │
         ▼
  chain_dispatcher.py returns result to Level 1 session
         │
         ▼
implementer_skill (Level 1 session) continues
  ─ Reads forger result
  ─ github-mcp tools now available
  ─ Continues implementation with GitHub API access
```

### 4.2 Maximum Depth

OpenClaw's deep chaining implementation caps at depth 3 (Level 0 + 2 sub-levels)
by default. This is configurable in `supervisor_config.json`. Deeper chains are
possible but increase cost and latency significantly.

Each `chain_dispatcher.py` invocation records the current chain depth. If the
depth limit is reached, the sub-agent spawn is rejected and the parent agent must
handle the task inline.

---

## 5. File Layout

```
openclaw/
├── deep_chain_skill.md            # NEW — meta-skill for sub-agent spawning
├── tools/
│   └── chain_dispatcher.py        # NEW — session spawner + result collector
├── implementer_skill.md           # MODIFY — embed deep chain instructions
├── researcher_skill.md            # MODIFY — embed deep chain instructions
├── supervisor_config.json         # MODIFY — max depth, chain settings
└── agent_profiles.json            # MODIFY — add chain_depth to profiles

.openclaw/tasks/
└── chain-{parent_id}-{skill}-{ts}.json   # RUNTIME — chained task files
```

---

## 6. Adaptation Strategy

### 6.1 No Native Agent Tool

Claude Code's `Agent` tool is a first-class primitive. OpenClaw has no equivalent.

**Adaptation**: `chain_dispatcher.py` is the `Agent` tool equivalent. It:
- Writes a task file for the sub-agent
- Spawns the sub-agent as a subprocess or via OpenClaw's session runner
- Blocks until the sub-agent's output file exists
- Returns the output to the calling session

The calling session invokes this via Bash:
```bash
python openclaw/tools/chain_dispatcher.py \
  --skill forger_skill \
  --task "Generate GitHub MCP server from API docs" \
  --context '{"api_name": "github", "docs_url": "https://docs.github.com/rest"}' \
  --parent-id {current_task_id} \
  --output /tmp/chain-result.json
```

### 6.2 Context Isolation

Claude Code uses the `Agent` tool's `context` parameter to pass only relevant
information. OpenClaw's `chain_dispatcher.py` builds a minimal context pack from
the `--context` JSON argument. The sub-agent session receives only this context
(plus its own skill prompt) — not the parent's full conversation.

### 6.3 Slash Command Embedding

Slash commands cannot be typed by sub-agents. The embedding strategy:

Each skill file includes a section called `## Delegation Patterns` that describes
when and how to spawn specific sub-skills. This section replaces the `/forge`,
`/browse`, `/research` commands with prose instructions that produce the same
effect via `chain_dispatcher.py`.

This section is included in each skill prompt that benefits from it:
- `implementer_skill.md` — can delegate to forger, researcher, browser
- `researcher_skill.md` — can delegate to sub-researcher, browser
- `orchestrator_prompt.md` — can delegate to any skill

### 6.4 Depth Tracking

Each chain_dispatcher.py call receives the current chain depth from the parent
session's task file (the parent reads its own task file which includes the depth
at which it was spawned). If the current depth is at the maximum, the dispatcher
returns an error instead of spawning.

---

## 7. Implementation Plan

### Step 1: Create `chain_dispatcher.py`

```python
# openclaw/tools/chain_dispatcher.py
"""
Spawns a sub-agent session and waits for its result.
The Agent tool equivalent for OpenClaw.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

MAX_POLL_SECONDS = 300
POLL_INTERVAL_SECONDS = 2

def spawn_and_wait(
    skill: str,
    task: str,
    context: dict,
    parent_id: str,
    openclaw_dir: str = "openclaw",
    chain_depth: int = 0,
    max_depth: int = 3,
    output_file: str | None = None
) -> dict:
    """
    Spawn a sub-agent session and wait for its result.

    Returns: {"status": "complete|failed|timeout|depth_limit", "result": {...}, "error": str}
    """
    if chain_depth >= max_depth:
        return {
            "status": "depth_limit",
            "result": None,
            "error": f"Chain depth limit ({max_depth}) reached. Cannot spawn {skill}."
        }

    ts = int(datetime.now().timestamp())
    task_id = f"chain-{parent_id}-{skill.replace('_skill','')}-{ts}"
    task_file = Path(".openclaw/tasks") / f"{task_id}.json"
    result_file = Path(".openclaw/tasks") / f"{task_id}-result.json"

    task_file.parent.mkdir(parents=True, exist_ok=True)

    # Write task file for sub-agent
    task_data = {
        "task_id": task_id,
        "skill": skill,
        "goal": task,
        "context": context,
        "parent_id": parent_id,
        "chain_depth": chain_depth + 1,
        "max_chain_depth": max_depth,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    task_file.write_text(json.dumps(task_data, indent=2))

    # Build the command to run the sub-agent session
    runner_cmd = _find_runner_cmd(openclaw_dir)
    if not runner_cmd:
        return {
            "status": "failed",
            "result": None,
            "error": "OpenClaw session runner not found. Check installation."
        }

    cmd = runner_cmd + [
        "--skill", skill,
        "--task", str(task_file),
        "--output", str(result_file),
        "--chain-depth", str(chain_depth + 1)
    ]

    # Start sub-agent as subprocess (non-blocking)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Poll for result file
    start = time.time()
    while time.time() - start < MAX_POLL_SECONDS:
        if result_file.exists():
            try:
                result_data = json.loads(result_file.read_text())
                status = result_data.get("status", "complete")
                return {"status": status, "result": result_data, "error": ""}
            except json.JSONDecodeError:
                pass  # File not fully written yet, keep polling

        if proc.poll() is not None:
            # Process exited — check if result file was written
            if result_file.exists():
                result_data = json.loads(result_file.read_text())
                return {"status": result_data.get("status", "complete"), "result": result_data, "error": ""}
            else:
                stderr = proc.stderr.read() if proc.stderr else ""
                return {
                    "status": "failed",
                    "result": None,
                    "error": f"Sub-agent exited without result. stderr: {stderr[:500]}"
                }

        time.sleep(POLL_INTERVAL_SECONDS)

    # Timeout
    proc.kill()
    return {
        "status": "timeout",
        "result": None,
        "error": f"Sub-agent {skill} timed out after {MAX_POLL_SECONDS}s"
    }

def _find_runner_cmd(openclaw_dir: str) -> list[str] | None:
    """Find the OpenClaw session runner command."""
    # Try common locations
    candidates = [
        ["openclaw", "run"],
        ["python", "-m", "openclaw.runner"],
        [os.path.join(openclaw_dir, "runner.py")],
    ]
    import shutil
    for cmd in candidates:
        if shutil.which(cmd[0]):
            return cmd
    return None

def main():
    parser = argparse.ArgumentParser(description="Spawn and wait for a sub-agent session")
    parser.add_argument("--skill", required=True, help="Skill name to invoke")
    parser.add_argument("--task", required=True, help="Task description")
    parser.add_argument("--context", default="{}", help="JSON context to pass to sub-agent")
    parser.add_argument("--parent-id", required=True, help="Parent task ID (for lineage tracking)")
    parser.add_argument("--chain-depth", type=int, default=0, help="Current chain depth")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum chain depth")
    parser.add_argument("--openclaw-dir", default="openclaw")
    parser.add_argument("--output", help="Write result to file instead of stdout")
    args = parser.parse_args()

    context = json.loads(args.context)
    result = spawn_and_wait(
        skill=args.skill,
        task=args.task,
        context=context,
        parent_id=args.parent_id,
        openclaw_dir=args.openclaw_dir,
        chain_depth=args.chain_depth,
        max_depth=args.max_depth
    )

    result_json = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).write_text(result_json)
    else:
        print(result_json)

    sys.exit(0 if result["status"] in ("complete", "partial") else 1)

if __name__ == "__main__":
    main()
```

### Step 2: Create `deep_chain_skill.md`

Full content in Section 8.

### Step 3: Add Delegation Patterns to existing skills

Modify `implementer_skill.md`, `researcher_skill.md` to include the
`## Delegation Patterns` section. See Section 9.

---

## 8. Configuration

### `deep_chain_skill.md` (complete file — embed in other skills)

```markdown
# Deep Chain Protocol

This section defines when and how to spawn sub-agent sessions. Load this section
when your task would benefit from recursive delegation.

## When to Spawn a Sub-Agent

Spawn a sub-agent when:
- The sub-task is well-defined and independent (has a clear input and output)
- Doing it inline would pollute your context with unrelated work
- A specialized skill would do it better (forger for MCP generation, browser for web scraping, researcher for deep research)
- The sub-task could run faster in isolation (no context overhead)

Do NOT spawn a sub-agent when:
- The task takes fewer than 10 steps
- You are already at chain depth 3 (check your task file's `chain_depth`)
- The sub-task directly modifies files you are also modifying (conflicts)
- The sub-task result would be too large to integrate cleanly

## How to Spawn a Sub-Agent

Use `chain_dispatcher.py` via Bash:

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill {skill_name} \
  --task "{one sentence task description}" \
  --context '{JSON with relevant facts the sub-agent needs}' \
  --parent-id {your_task_id} \
  --chain-depth {your chain_depth from task file} \
  --output /tmp/chain-result-{skill_name}.json
```

Then read the result:
```bash
cat /tmp/chain-result-{skill_name}.json
```

## Delegation Patterns

### Pattern: Need a new API integration

When you need to call an API and there is no MCP tool installed for it:

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill forger_skill \
  --task "Generate MCP server for the {API_NAME} API" \
  --context '{"api_name": "{API_NAME}", "docs_url": "{DOCS_URL_OR_NULL}"}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-forge-result.json
```

After this completes:
- Read `/tmp/chain-forge-result.json` to get the `config_snippet`
- The MCP server is now installed and available in the current session

### Pattern: Need to scrape or interact with a website

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill browser_skill \
  --task "{describe what you need from the website}" \
  --context '{"start_url": "{URL}", "goal": "{goal}", "max_pages": 5}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-browser-result.json
```

### Pattern: Need deep research before implementing

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill researcher_skill \
  --task "Research: {topic or question}" \
  --context '{"focus": "{what aspect to focus on}", "depth": "standard"}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-research-result.json
```

### Pattern: Need to run and analyze tests independently

```bash
python openclaw/tools/chain_dispatcher.py \
  --skill implementer_skill \
  --task "Run tests and fix failures in {file_or_module}" \
  --context '{"workspace_path": ".", "test_target": "{target}", "fix_failures": true}' \
  --parent-id {TASK_ID} \
  --chain-depth {DEPTH} \
  --output /tmp/chain-test-fix-result.json
```

## Result Integration

After a sub-agent completes, read its result and extract ONLY what you need.
Do not paste the full result into your context. Extract the key facts:

Good:
```
Sub-agent result: forger created github-mcp with 12 tools.
Config added to .mcp.json. Now I can use github.createIssue, github.listPullRequests.
```

Bad:
```
Sub-agent result: {"status": "complete", "path": "mcp-servers/github-mcp",
"config_snippet": {"mcpServers": {"github": {"command": "python", "args": ["-m",
"github_mcp.server"], "env": {"GITHUB_TOKEN": ""}}}}, "endpoint_count": 12, ...
[full 200-line JSON paste]...}
```

## Depth Limit

If `chain_dispatcher.py` returns `{"status": "depth_limit"}`, do NOT retry.
Instead, perform the sub-task inline as best you can, note the limitation in your
result, and continue.

## Timeout Handling

If `chain_dispatcher.py` returns `{"status": "timeout"}`, record the failure and
continue with partial information. Do not block indefinitely waiting for a slow
sub-agent.
```

### `supervisor_config.json` additions

```json
{
  "deep_chaining": {
    "enabled": true,
    "max_chain_depth": 3,
    "sub_agent_timeout_seconds": 300,
    "poll_interval_seconds": 2,
    "chain_task_file_pattern": ".openclaw/tasks/chain-{parent_id}-{skill}-{ts}.json",
    "allowed_sub_skills": [
      "forger_skill",
      "browser_skill",
      "chrome_skill",
      "researcher_skill",
      "implementer_skill",
      "wave_planner_skill"
    ],
    "denied_sub_skills": [
      "harness_skill",
      "orchestrator"
    ]
  }
}
```

### `agent_profiles.json` additions

Add `chain_depth` tracking to all profiles that support deep chaining:

```json
{
  "implementer": {
    "deep_chaining": {
      "enabled": true,
      "max_depth": 3,
      "allowed_to_spawn": ["forger_skill", "browser_skill", "researcher_skill", "implementer_skill"]
    }
  },
  "researcher": {
    "deep_chaining": {
      "enabled": true,
      "max_depth": 2,
      "allowed_to_spawn": ["browser_skill", "researcher_skill"]
    }
  },
  "forger": {
    "deep_chaining": {
      "enabled": false
    }
  },
  "browser": {
    "deep_chaining": {
      "enabled": true,
      "max_depth": 1,
      "allowed_to_spawn": ["chrome_skill"]
    }
  }
}
```

---

## 9. Integration Points

### `implementer_skill.md` Modification

Add the following `## Delegation Patterns` section to `implementer_skill.md`
immediately before the Ralph Loop section:

```markdown
## Delegation Patterns

You can spawn sub-agent sessions for specialized tasks using chain_dispatcher.py.
Read the Deep Chain Protocol (deep_chain_skill.md) for the full reference.

Quick reference for common delegation needs:

**Need an API integration that is not installed as MCP?**
→ Spawn forger_skill with the API name.

**Need to scrape a website or interact with a web UI?**
→ Spawn browser_skill with the goal and URL.

**Need to research a technology choice before implementing?**
→ Spawn researcher_skill with the research question.

**Code failing tests and you cannot diagnose the issue?**
→ Spawn a fresh implementer_skill session with the handoff context.
  (This is a level-2 chain — only do this if you are at depth 0 or 1.)

Always check your task file's `chain_depth` before spawning. If chain_depth >= 3,
do not spawn — handle inline.
```

### `researcher_skill.md` Modification

Add `## Delegation Patterns` section:

```markdown
## Delegation Patterns

**Need current pricing, documentation, or live data from a website?**
→ Spawn browser_skill with the specific URL and extraction goal.

**Need to cover multiple independent sub-topics in parallel?**
→ Spawn multiple researcher_skill instances via chain_dispatcher.py, one per topic.
  Wait for all, then synthesize.
  (Only do this if you are at depth 0 or 1.)

Example: researching "best Python async databases" could spawn:
  - researcher for "asyncpg vs psycopg3 comparison"
  - researcher for "SQLAlchemy async support status"
  - researcher for "Tortoise ORM production readiness"
  Then synthesize the three results in your own context.
```

### Orchestrator Prompt Addition

Add to `orchestrator_prompt.md`:

```markdown
## Deep Chaining Awareness

When dispatching level-1 skills, always include these fields in the task file:
```json
{
  "chain_depth": 1,
  "max_chain_depth": 3,
  "parent_id": "orchestrator-{ts}"
}
```

When a level-1 task completes:
- Read its result file
- Check for any `chained_tasks` field (list of sub-agent task IDs that were spawned)
- Those tasks' result files are already complete (sub-agents wait for their children)
- You do not need to re-run them — their results are embedded in the level-1 result

## Detecting and Handling Chain Failures

If a result file contains `"chained_failures": [...]`:
- Surface the chain failure names and errors in your response
- Assess whether the parent task was still completed adequately
- If the parent task was completed despite chain failures: mark as partial
- If the chain failure was critical: surface to user with the full error chain

## Chain Depth Reporting

When synthesizing results for the user, include a brief chain summary if the
depth exceeded 1:

```
[Chain depth: 3]
  orchestrator → implementer → forger (generated github-mcp)
  orchestrator → implementer → researcher (researched rate limiting patterns)
```

This helps the user understand what happened and how to reproduce or modify the
behavior.
```

### Task File Schema Extension

All task files dispatched by the orchestrator must now include chain tracking:

```json
{
  "task_id": "{skill}-{ts}",
  "skill": "{skill_name}",
  "goal": "...",
  "chain_depth": 1,
  "max_chain_depth": 3,
  "parent_id": "orchestrator-{ts}",
  "chained_tasks": [],
  "chained_failures": [],
  "status": "pending"
}
```

Each level-N agent appends to `chained_tasks` when it spawns a level-(N+1) agent.
This creates a complete lineage trace in the level-1 result file.

---

## 10. Testing Plan

### Unit Test: chain_dispatcher

```python
# tests/test_chain_dispatcher.py

import json
import pytest
from pathlib import Path
from openclaw.tools.chain_dispatcher import spawn_and_wait

def test_depth_limit_respected():
    result = spawn_and_wait(
        skill="forger_skill",
        task="test task",
        context={},
        parent_id="test-parent",
        chain_depth=3,  # AT the limit
        max_depth=3
    )
    assert result["status"] == "depth_limit"
    assert "depth limit" in result["error"].lower()

def test_task_file_written(tmp_path, monkeypatch):
    # Mock the runner to immediately write a result file
    def mock_runner(skill, task, context, parent_id, openclaw_dir, chain_depth, max_depth, output_file):
        Path(".openclaw/tasks").mkdir(parents=True, exist_ok=True)
        # Simulate sub-agent writing result
        task_id = f"chain-{parent_id}-{skill}-12345"
        result_file = Path(".openclaw/tasks") / f"{task_id}-result.json"
        result_file.write_text(json.dumps({"status": "complete", "result": "test output"}))
        return {"status": "complete", "result": {"result": "test output"}}

    monkeypatch.setattr("openclaw.tools.chain_dispatcher.spawn_and_wait", mock_runner)
    # Test that task file is created before mock is called
```

### Integration Test: 2-Level Chain

```bash
# Create a task that requires a sub-agent (implementer that needs research)
cat > .openclaw/tasks/chain-test-001.json << 'EOF'
{
  "task_id": "chain-test-001",
  "skill": "implementer_skill",
  "goal": "Implement a Python function that uses the best available async HTTP library. First research which library to use, then implement.",
  "chain_depth": 1,
  "max_chain_depth": 3,
  "parent_id": "orchestrator-test",
  "chained_tasks": [],
  "status": "pending"
}
EOF

openclaw run --skill implementer_skill --task chain-test-001 --profile implementer

# Verify chain was used
cat .openclaw/tasks/chain-test-001-result.json | python -m json.tool | grep chained_tasks
# Expected: array with at least one entry (researcher sub-agent task ID)

# Verify sub-agent result exists
cat .openclaw/tasks/chain-test-001-result.json | python -c "
import json, sys
result = json.load(sys.stdin)
for task_id in result.get('chained_tasks', []):
    result_file = f'.openclaw/tasks/{task_id}-result.json'
    sub = json.loads(open(result_file).read())
    print(f'{task_id}: {sub[\"status\"]}')
"
```

### 3-Level Chain Test

```bash
# Task: implement + research sub-topic + browse for current data
# orchestrator → implementer → researcher → browser (depth 3)

# After running, verify:
# 1. depth 3 was reached
# 2. depth 4 attempt was blocked (depth_limit in result)
# 3. Final result was still usable (partial completion)
```

### Depth Limit Test

```bash
# Set max_depth to 1 and try to spawn a sub-sub-agent
# Verify: depth_limit status returned, no subprocess spawned
```

---

## 11. Example Usage

### Scenario: Implementing a Slack notification system with no Slack MCP installed

**User**: `/go Add Slack notifications to the job completion workflow. Notify the channel when a job finishes or fails.`

**Orchestrator (Level 0)** dispatches `implementer_skill` (Level 1) with:
```json
{"goal": "Add Slack notifications to the job completion workflow", "chain_depth": 1}
```

**Implementer (Level 1)** reads the codebase. Finds `src/jobs/runner.ts`. Needs to call
Slack API. Checks `.mcp.json` — no Slack MCP installed.

**Implementer delegates** (Level 1 → Level 2):
```bash
python openclaw/tools/chain_dispatcher.py \
  --skill forger_skill \
  --task "Generate Slack API MCP server from Slack Web API docs" \
  --context '{"api_name": "slack", "docs_url": "https://api.slack.com/methods"}' \
  --parent-id "implementer-chain-test-001" \
  --chain-depth 1 \
  --output /tmp/chain-forge-slack.json
```

**Forger (Level 2)** executes:
- Fetches `https://api.slack.com/methods`
- Parses endpoints: `chat.postMessage`, `conversations.list`, `users.info`, etc.
- Generates `mcp-servers/slack-mcp/` with 18 tools
- Writes result to task file

**Forger result** returned to Implementer (Level 1):
```json
{"status": "complete", "endpoint_count": 18, "auth_type": "bearer"}
```

**Implementer continues** (Level 1):
- Now has access to `slack.postMessage` MCP tool
- Writes `src/jobs/notifications.ts` using `slack.postMessage`
- Modifies `src/jobs/runner.ts` to call `notifyJobComplete(jobId, result)`
- Runs Ralph Loop: tests pass on iteration 2

**Implementer result** returned to Orchestrator (Level 0):
```json
{
  "status": "complete",
  "chained_tasks": ["chain-implementer-forger-1741824500"],
  "files_modified": ["src/jobs/notifications.ts", "src/jobs/runner.ts"],
  "summary": "Slack notifications added. Uses slack.postMessage. SLACK_TOKEN env var required."
}
```

**Chain summary** surfaced to user:
```
[Chain depth: 2]
  orchestrator → implementer (modified runner.ts, notifications.ts)
    ↳ implementer → forger (generated slack-mcp with 18 tools)

Result: Slack notifications implemented. Set SLACK_TOKEN in your environment.
```

Total user interaction: one `/go` command. Zero decisions required mid-task.
The deep chain handled tool discovery, MCP generation, and implementation
end-to-end.
